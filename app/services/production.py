"""
app/services/production.py – Production Floor, Machine & Work Order Services.
WHAT IT DOES:
  - Dispatches work orders to machines.
  - Consumes yarn FIFO on the initial production run.
  - Logs meter production, cutting 50-meter FabricRolls at the final (DYEING) stage.
  - Handles machine breakdown and repair events.
WHY IT EXISTS:
  Coordinates manufacturing across spinning, weaving, and dyeing stages
  while ensuring atomic writes and full audit trails.
"""

from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.production import Machine, WorkOrder
from app.models.order import Order
from app.models.quality import FabricRoll
from app.models.yarn import Material
from app.services.inventory import consume_yarn_fifo
from app.services.orders import calculate_bom
from app.services.audit import log_write


def start_work_order(
    db: Session,
    order_id: int,
    machine_id: int,
    stage: str,
    user_id: Optional[int] = None,
) -> WorkOrder:
    """
    WHAT: Starts a production work order on a machine.
    WHY: If this is the initial manufacturing step, triggers FIFO consumption
         of the reserved yarn.
    """
    order = db.get(Order, order_id)
    if not order:
        raise ValueError(f"Order #{order_id} not found")
    if not order.confirmed:
        raise ValueError(f"Order #{order_id} must be confirmed before production can start")

    machine = db.get(Machine, machine_id)
    if not machine:
        raise ValueError(f"Machine #{machine_id} not found")
    if machine.status == "BREAKDOWN":
        raise ValueError(f"Machine '{machine.name}' is currently in BREAKDOWN state")
    if machine.type != stage:
        raise ValueError(f"Machine '{machine.name}' type ({machine.type}) does not match stage ({stage})")

    # If first work order for this order, consume reserved yarn FIFO
    existing_wos = db.query(WorkOrder).filter(WorkOrder.order_id == order_id).all()
    if not existing_wos:
        bom = calculate_bom(order.fabric_type, order.meters)
        for item in bom:
            mat = db.query(Material).filter(Material.name == item["material_name"]).first()
            if mat:
                consume_yarn_fifo(
                    db,
                    material_id=mat.id,
                    qty_needed=item["gross_kg"],
                    order_id=order.id,
                    user_id=user_id,
                )

    work_order = WorkOrder(
        order_id=order.id,
        machine_id=machine.id,
        stage=stage,
        status="RUNNING",
        target_meters=order.meters,
        completed_meters=0.0,
        start_time=datetime.utcnow(),
    )
    db.add(work_order)
    machine.status = "RUNNING"
    db.flush()

    log_write(
        db,
        action="START_WORK_ORDER",
        entity_type="WorkOrder",
        entity_id=work_order.id,
        user_id=user_id,
        details={"order_id": order_id, "machine_id": machine_id, "stage": stage},
    )

    db.commit()
    db.refresh(work_order)
    return work_order


def log_output(
    db: Session,
    work_order_id: int,
    meters: float,
    user_id: Optional[int] = None,
) -> WorkOrder:
    """
    WHAT: Records meters manufactured on a work order.
    WHY: When meters are recorded at the final stage (DYEING), automatically
         cuts standard 50-meter FabricRolls.
    """
    if meters <= 0:
        raise ValueError("Logged meters must be greater than zero")

    wo = db.get(WorkOrder, work_order_id)
    if not wo:
        raise ValueError(f"WorkOrder #{work_order_id} not found")
    if wo.status != "RUNNING":
        raise ValueError(f"WorkOrder #{work_order_id} is not in RUNNING status")

    prev_completed = wo.completed_meters
    new_completed = prev_completed + meters
    wo.completed_meters = new_completed

    # If DYEING (final stage), cut rolls for every completed 50 meters
    if wo.stage == "DYEING":
        prev_rolls = int(prev_completed // settings.ROLL_LENGTH_M)
        new_rolls = int(new_completed // settings.ROLL_LENGTH_M)
        rolls_to_create = new_rolls - prev_rolls

        for i in range(rolls_to_create):
            roll_idx = prev_rolls + i + 1
            roll_code = f"ROLL-{wo.order_id}-{wo.id}-{roll_idx:03d}"
            roll = FabricRoll(
                roll_code=roll_code,
                order_id=wo.order_id,
                work_order_id=wo.id,
                machine_id=wo.machine_id,
                length_m=settings.ROLL_LENGTH_M,
            )
            db.add(roll)

    # Check if target reached
    if wo.completed_meters >= wo.target_meters:
        wo.status = "DONE"
        wo.end_time = datetime.utcnow()
        if wo.machine:
            wo.machine.status = "IDLE"

    log_write(
        db,
        action="LOG_OUTPUT",
        entity_type="WorkOrder",
        entity_id=wo.id,
        user_id=user_id,
        details={"meters_added": meters, "total_completed": wo.completed_meters, "status": wo.status},
    )

    db.commit()
    db.refresh(wo)
    return wo


def report_breakdown(db: Session, machine_id: int, user_id: Optional[int] = None) -> Machine:
    """
    WHAT: Flags a machine as broken down on the shop floor.
    """
    machine = db.get(Machine, machine_id)
    if not machine:
        raise ValueError(f"Machine #{machine_id} not found")
    machine.status = "BREAKDOWN"

    log_write(db, action="MACHINE_BREAKDOWN", entity_type="Machine", entity_id=machine.id, user_id=user_id)
    db.commit()
    db.refresh(machine)
    return machine


def repair_machine(db: Session, machine_id: int, user_id: Optional[int] = None) -> Machine:
    """
    WHAT: Restores a broken-down machine to IDLE status.
    """
    machine = db.get(Machine, machine_id)
    if not machine:
        raise ValueError(f"Machine #{machine_id} not found")
    machine.status = "IDLE"

    log_write(db, action="MACHINE_REPAIRED", entity_type="Machine", entity_id=machine.id, user_id=user_id)
    db.commit()
    db.refresh(machine)
    return machine
