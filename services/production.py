"""
services/production.py – Factory-floor business logic.
Manages work orders, machine status, output logging, and delay risk.
"""

from datetime import datetime, date, timedelta
import math
from models import db, Order, Machine, WorkOrder, FabricRoll
from config import STAGES, ROLL_LENGTH_M, MACHINE_STATUS, WORK_STATUS
from services import inventory as inv_svc


# ── start_work_order ───────────────────────────────────────
def start_work_order(order_id, machine_id, stage, commit=True):
    """
    Create a work order: assign a machine to process one stage of an order.
    The machine must be IDLE and match the stage type (WEAVING/DYEING).
    """
    order = db.session.get(Order, order_id)
    if not order:
        raise ValueError(f"Order {order_id} not found.")

    machine = db.session.get(Machine, machine_id)
    if not machine:
        raise ValueError(f"Machine {machine_id} not found.")

    # Validate stage
    if stage not in STAGES:
        raise ValueError(f"Stage must be one of {STAGES}.")

    # Machine type must match stage
    if machine.type != stage:
        raise ValueError(
            f"Machine {machine.name} is type {machine.type}, "
            f"but stage {stage} requires a {stage} machine."
        )

    # Machine must be IDLE
    if machine.status != "IDLE":
        raise ValueError(f"Machine {machine.name} is {machine.status}, not IDLE.")

    # Order must be in the right status for this stage
    if stage == "WEAVING" and order.status != "WEAVING":
        raise ValueError(f"Order status must be WEAVING to start weaving (currently {order.status}).")
    if stage == "DYEING" and order.status != "DYEING":
        raise ValueError(f"Order status must be DYEING to start dyeing (currently {order.status}).")

    # Check no active work order already exists for this order+stage
    existing = WorkOrder.query.filter_by(
        order_id=order_id, stage=stage
    ).filter(WorkOrder.status.in_(["PENDING", "RUNNING"])).first()
    if existing:
        raise ValueError(f"An active work order already exists for order {order_id} stage {stage}.")

    wo = WorkOrder(
        order_id=order_id,
        machine_id=machine_id,
        stage=stage,
        status="RUNNING",
        target_meters=order.meters,
        produced_meters=0,
        started_at=datetime.utcnow(),
    )
    db.session.add(wo)

    # Mark machine as RUNNING
    machine.status = "RUNNING"

    if commit:
        db.session.commit()

    return wo


# ── log_output ─────────────────────────────────────────────
def log_output(work_order_id, meters, commit=True):
    """
    Record meters of fabric produced on a work order.
    When DYEING stage reaches the target, auto-create rolls (50 m each)
    and advance the order to QC status.
    """
    wo = db.session.get(WorkOrder, work_order_id)
    if not wo:
        raise ValueError(f"Work order {work_order_id} not found.")
    if wo.status != "RUNNING":
        raise ValueError(f"Work order is {wo.status}, not RUNNING.")
    if meters <= 0:
        raise ValueError("Meters must be greater than zero.")

    wo.produced_meters += meters
    order = wo.order

    # Check if this stage is complete
    if wo.produced_meters >= wo.target_meters:
        wo.status = "DONE"
        wo.finished_at = datetime.utcnow()

        # Free the machine
        machine = wo.machine
        machine.status = "IDLE"

        if wo.stage == "WEAVING":
            # Advance order to DYEING stage
            order.status = "DYEING"

            # Consume raw materials now that weaving is done
            yarn_lot = inv_svc.consume_for_order(order.id, commit=False)

        elif wo.stage == "DYEING":
            # DYEING is the final production stage → create rolls and go to QC
            # Find the yarn lot from consume movements for traceability
            from models import StockMovement
            consume_mov = (
                StockMovement.query
                .filter_by(order_id=order.id, movement_type="CONSUME")
                .first()
            )
            yarn_lot = consume_mov.lot_no if consume_mov else ""

            # Create fabric rolls (each 50 m)
            num_rolls = math.floor(wo.produced_meters / ROLL_LENGTH_M)
            if num_rolls < 1:
                num_rolls = 1  # At least one roll

            for i in range(num_rolls):
                # Generate a unique roll code
                last_roll = FabricRoll.query.order_by(FabricRoll.id.desc()).first()
                next_num = (last_roll.id + 1) if last_roll else 1
                code = f"ROLL-{next_num + i:04d}"

                roll = FabricRoll(
                    code=code,
                    order_id=order.id,
                    work_order_id=wo.id,
                    machine_id=wo.machine_id,
                    length_m=ROLL_LENGTH_M,
                    qc_status="PENDING",
                    yarn_lot_no=yarn_lot,
                )
                db.session.add(roll)

            # Advance order to QC
            order.status = "QC"

    if commit:
        db.session.commit()

    return wo


# ── report_breakdown ───────────────────────────────────────
def report_breakdown(machine_id):
    """
    Mark a machine as BREAKDOWN.  Any RUNNING work orders on it stay
    as-is (the operator can resume after repair).
    """
    machine = db.session.get(Machine, machine_id)
    if not machine:
        raise ValueError(f"Machine {machine_id} not found.")
    if machine.status == "BREAKDOWN":
        raise ValueError(f"Machine {machine.name} is already in BREAKDOWN.")

    machine.status = "BREAKDOWN"
    db.session.commit()


# ── repair_machine ─────────────────────────────────────────
def repair_machine(machine_id):
    """
    Mark a broken-down machine as IDLE (repaired and ready to use).
    If it had a RUNNING work order, the machine stays IDLE until
    the supervisor manually restarts it.
    """
    machine = db.session.get(Machine, machine_id)
    if not machine:
        raise ValueError(f"Machine {machine_id} not found.")
    if machine.status != "BREAKDOWN":
        raise ValueError(f"Machine {machine.name} is not in BREAKDOWN (currently {machine.status}).")

    # Check if there's a running work order → set machine to RUNNING
    running_wo = WorkOrder.query.filter_by(
        machine_id=machine_id, status="RUNNING"
    ).first()

    if running_wo:
        machine.status = "RUNNING"
    else:
        machine.status = "IDLE"

    db.session.commit()


# ── delay_risk ─────────────────────────────────────────────
def delay_risk(order_id):
    """
    Estimate if the order will miss its deadline.
    Returns {at_risk: bool, projected: date, days_late: int}.
    Uses average daily output to project completion date.
    """
    order = db.session.get(Order, order_id)
    if not order:
        raise ValueError(f"Order {order_id} not found.")

    # If already done, no risk
    if order.status in ("READY", "DISPATCHED"):
        return {"at_risk": False, "projected": order.deadline, "days_late": 0}

    # Calculate total meters produced so far across all stages
    total_produced = 0
    total_days = 0
    for wo in order.work_orders:
        total_produced += wo.produced_meters
        if wo.started_at:
            days = max((datetime.utcnow() - wo.started_at).days, 1)
            total_days += days

    # Target: need to complete both stages (weaving + dyeing = 2× meters)
    total_target = order.meters * len(STAGES)
    remaining = total_target - total_produced

    if remaining <= 0:
        return {"at_risk": False, "projected": date.today(), "days_late": 0}

    # Average daily output
    if total_days > 0 and total_produced > 0:
        daily_rate = total_produced / total_days
        days_remaining = math.ceil(remaining / daily_rate)
    else:
        # No data yet, assume 50 meters/day
        days_remaining = math.ceil(remaining / 50)

    projected = date.today() + timedelta(days=days_remaining)
    days_late = max((projected - order.deadline).days, 0)

    return {
        "at_risk": projected > order.deadline,
        "projected": projected,
        "days_late": days_late,
    }


# ── machine_board ──────────────────────────────────────────
def machine_board():
    """
    Build the live machine dashboard data.
    Returns a list of dicts with machine info, current order, and progress.
    """
    machines = Machine.query.order_by(Machine.type, Machine.name).all()
    board = []

    for m in machines:
        # Find the current RUNNING work order, if any
        running_wo = WorkOrder.query.filter_by(
            machine_id=m.id, status="RUNNING"
        ).first()

        order_id = None
        stage = ""
        progress_pct = 0
        today_m = 0

        if running_wo:
            order_id = running_wo.order_id
            stage = running_wo.stage
            if running_wo.target_meters > 0:
                progress_pct = round(
                    running_wo.produced_meters / running_wo.target_meters * 100, 1
                )
            today_m = running_wo.produced_meters  # simplified: total as "today"

        board.append({
            "machine_id": m.id,
            "name": m.name,
            "type": m.type,
            "status": m.status,
            "order_id": order_id,
            "stage": stage,
            "progress_pct": min(progress_pct, 100),
            "today_m": round(today_m, 1),
        })

    return board
