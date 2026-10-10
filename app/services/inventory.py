"""
app/services/inventory.py – Raw Material & Inventory Ledger Services.
WHAT IT DOES:
  - Records stock receipts.
  - Dynamically computes on-hand, reserved, and available stock from the ledger.
  - Implements FIFO (oldest-lot-first) consumption of yarn batches.
WHY IT EXISTS:
  Implements the core business rules:
  1. Stock is NEVER a stored number; always derived from StockMovement ledger.
  2. Consumption is oldest-lot-first (FIFO).
  3. Every write is audited and executed in a single atomic transaction.
"""

from typing import Dict, List, Optional
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models.yarn import Material, YarnLot, StockMovement
from app.services.audit import log_write


def receive_stock(
    db: Session,
    material_id: int,
    lot_no: str,
    qty: float,
    unit_cost: float,
    supplier_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> YarnLot:
    """
    WHAT: Records a new yarn shipment receipt from a vendor.
    WHY: Creates both the YarnLot batch and the corresponding RECEIPT ledger entry.
    """
    if qty <= 0:
        raise ValueError("Received quantity must be greater than zero")

    material = db.get(Material, material_id)
    if not material:
        raise ValueError(f"Material #{material_id} not found")

    # Check for duplicate lot_no
    existing_lot = db.query(YarnLot).filter(YarnLot.lot_no == lot_no).first()
    if existing_lot:
        raise ValueError(f"Yarn Lot '{lot_no}' already exists")

    # 1. Create YarnLot
    lot = YarnLot(
        lot_no=lot_no,
        material_id=material_id,
        supplier_id=supplier_id,
        initial_qty=qty,
        unit_cost=unit_cost,
    )
    db.add(lot)
    db.flush()  # Generates lot.id

    # 2. Create RECEIPT ledger entry
    movement = StockMovement(
        material_id=material_id,
        lot_id=lot.id,
        movement_type="RECEIPT",
        qty=qty,
        unit_cost=unit_cost,
        notes=f"Receipt for lot {lot_no}",
    )
    db.add(movement)

    # 3. Audit Log
    log_write(
        db,
        action="RECEIVE_STOCK",
        entity_type="YarnLot",
        entity_id=lot.id,
        user_id=user_id,
        details={"material_id": material_id, "lot_no": lot_no, "qty": qty, "unit_cost": unit_cost},
    )

    db.commit()
    db.refresh(lot)
    return lot


def get_material_stock(db: Session, material_id: int) -> Dict[str, float]:
    """
    WHAT: Computes physical on-hand, reserved, and available stock for a material.
    WHY: Implements rule: Stock is NEVER a stored number. Computed dynamically:
         On Hand = SUM(RECEIPT) - SUM(CONSUME)
         Reserved = SUM(RESERVE) - SUM(RELEASE)
         Available = On Hand - Reserved
    """
    movements = db.query(StockMovement).filter(StockMovement.material_id == material_id).all()

    receipts = sum(m.qty for m in movements if m.movement_type == "RECEIPT")
    consumed = sum(m.qty for m in movements if m.movement_type == "CONSUME")
    on_hand = max(0.0, receipts - consumed)

    reserved_sum = sum(m.qty for m in movements if m.movement_type == "RESERVE")
    released_sum = sum(m.qty for m in movements if m.movement_type == "RELEASE")
    reserved = max(0.0, reserved_sum - released_sum)

    available = max(0.0, on_hand - reserved)

    return {
        "on_hand": round(on_hand, 2),
        "reserved": round(reserved, 2),
        "available": round(available, 2),
    }


def get_all_stock_summary(db: Session) -> List[Dict]:
    """
    WHAT: Generates full inventory overview across all raw materials.
    WHY: Powers the store manager inventory table and reorder alerts.
    """
    materials = db.query(Material).order_by(Material.name).all()
    summary = []
    for m in materials:
        stk = get_material_stock(db, m.id)
        summary.append({
            "material_id": m.id,
            "name": m.name,
            "colour": m.colour,
            "unit": m.unit,
            "on_hand": stk["on_hand"],
            "reserved": stk["reserved"],
            "available": stk["available"],
            "reorder_level": m.reorder_level,
            "is_low": stk["available"] < m.reorder_level,
        })
    return summary


def consume_yarn_fifo(
    db: Session,
    material_id: int,
    qty_needed: float,
    order_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> List[Dict]:
    """
    WHAT: Physically consumes yarn for an order, drawing from the oldest lots first.
    WHY: Implements rule: Consumption oldest-lot-first (FIFO) to prevent yarn degradation.
    """
    if qty_needed <= 0:
        return []

    # Get lots ordered by receipt date ascending (oldest first)
    lots = (
        db.query(YarnLot)
        .filter(YarnLot.material_id == material_id)
        .order_by(YarnLot.received_date.asc())
        .all()
    )

    remaining_to_consume = qty_needed
    consumed_records = []

    for lot in lots:
        # Calculate current remaining stock in this specific lot
        lot_movements = db.query(StockMovement).filter(StockMovement.lot_id == lot.id).all()
        lot_receipts = sum(m.qty for m in lot_movements if m.movement_type == "RECEIPT")
        lot_consumed = sum(m.qty for m in lot_movements if m.movement_type == "CONSUME")
        lot_available = max(0.0, lot_receipts - lot_consumed)

        if lot_available <= 0:
            continue

        take_qty = min(remaining_to_consume, lot_available)

        # Create CONSUME ledger entry
        consume_movement = StockMovement(
            material_id=material_id,
            lot_id=lot.id,
            order_id=order_id,
            movement_type="CONSUME",
            qty=take_qty,
            unit_cost=lot.unit_cost,
            notes=f"FIFO consumption for order #{order_id}",
        )
        db.add(consume_movement)

        consumed_records.append({
            "lot_id": lot.id,
            "lot_no": lot.lot_no,
            "qty": take_qty,
            "unit_cost": lot.unit_cost,
        })

        remaining_to_consume -= take_qty
        if remaining_to_consume <= 0:
            break

    if remaining_to_consume > 0:
        raise ValueError(
            f"Insufficient physical stock to consume. Short by {round(remaining_to_consume, 2)} kg"
        )

    # Also record RELEASE of the reserved stock for this order
    release_movement = StockMovement(
        material_id=material_id,
        order_id=order_id,
        movement_type="RELEASE",
        qty=qty_needed,
        notes=f"Release reservation upon consumption for order #{order_id}",
    )
    db.add(release_movement)

    log_write(
        db,
        action="CONSUME_YARN_FIFO",
        entity_type="Order",
        entity_id=order_id,
        user_id=user_id,
        details={"material_id": material_id, "qty_needed": qty_needed, "consumed": consumed_records},
    )

    return consumed_records
