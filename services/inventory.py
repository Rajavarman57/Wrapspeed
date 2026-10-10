"""
services/inventory.py – All inventory/stock business logic.
Tracks raw materials: receipts, reservations, consumption, and stock levels.
"""

from models import db, Material, StockMovement, Order, Setting
from config import MOVEMENT_TYPE, FABRIC_RECIPES, WASTAGE


# ── receive_stock ──────────────────────────────────────────
def receive_stock(material_id, qty, lot_no, supplier_id, unit_cost,
                  order_id=None, commit=True):
    """
    Record incoming raw material from a supplier.
    Creates a RECEIPT movement that increases on-hand stock.
    """
    if qty <= 0:
        raise ValueError("Quantity must be greater than zero.")

    material = db.session.get(Material, material_id)
    if not material:
        raise ValueError(f"Material with id {material_id} not found.")

    movement = StockMovement(
        material_id=material_id,
        movement_type="RECEIPT",
        qty=qty,
        lot_no=lot_no or "",
        supplier_id=supplier_id,
        unit_cost=unit_cost,
        order_id=order_id,
    )
    db.session.add(movement)

    if commit:
        db.session.commit()

    return movement


# ── on_hand ────────────────────────────────────────────────
def on_hand(material_id):
    """
    Total stock physically in the warehouse.
    = sum(RECEIPT) - sum(CONSUME)
    """
    receipts = (
        db.session.query(db.func.coalesce(db.func.sum(StockMovement.qty), 0))
        .filter_by(material_id=material_id, movement_type="RECEIPT")
        .scalar()
    )
    consumed = (
        db.session.query(db.func.coalesce(db.func.sum(StockMovement.qty), 0))
        .filter_by(material_id=material_id, movement_type="CONSUME")
        .scalar()
    )
    return float(receipts - consumed)


# ── reserved ───────────────────────────────────────────────
def reserved(material_id):
    """
    Stock that is earmarked for confirmed orders but not yet consumed.
    = sum(RESERVE) - sum(RELEASE) - sum(CONSUME)
    """
    reserves = (
        db.session.query(db.func.coalesce(db.func.sum(StockMovement.qty), 0))
        .filter_by(material_id=material_id, movement_type="RESERVE")
        .scalar()
    )
    releases = (
        db.session.query(db.func.coalesce(db.func.sum(StockMovement.qty), 0))
        .filter_by(material_id=material_id, movement_type="RELEASE")
        .scalar()
    )
    consumed = (
        db.session.query(db.func.coalesce(db.func.sum(StockMovement.qty), 0))
        .filter_by(material_id=material_id, movement_type="CONSUME")
        .scalar()
    )
    return float(max(reserves - releases - consumed, 0))


# ── available ──────────────────────────────────────────────
def available(material_id):
    """
    Stock that can be reserved for new orders.
    = on_hand - reserved
    """
    return on_hand(material_id) - reserved(material_id)


# ── low_stock_materials ────────────────────────────────────
def low_stock_materials():
    """
    Return all materials whose on_hand is below their reorder_level.
    Used for dashboard alerts.
    """
    materials = Material.query.all()
    return [m for m in materials if on_hand(m.id) < m.reorder_level]


# ── stock_summary ──────────────────────────────────────────
def stock_summary():
    """
    Build a summary list for the inventory index page.
    Each item has: material_id, name, colour, on_hand, reserved, available,
    reorder_level, and a 'low' flag.
    """
    materials = Material.query.order_by(Material.name).all()
    result = []
    for m in materials:
        oh = on_hand(m.id)
        res = reserved(m.id)
        avail = oh - res
        result.append({
            "material_id": m.id,
            "name": m.name,
            "colour": m.colour,
            "on_hand": round(oh, 2),
            "reserved": round(res, 2),
            "available": round(avail, 2),
            "reorder_level": m.reorder_level,
            "low": oh < m.reorder_level,
        })
    return result


# ── consume_for_order ──────────────────────────────────────
def consume_for_order(order_id, commit=True):
    """
    Consume raw materials for an order (change RESERVE → CONSUME).
    Uses the fabric recipe to know how much of each material to consume.
    Returns the lot_no of the first yarn consumed (for roll traceability).
    """
    order = db.session.get(Order, order_id)
    if not order:
        raise ValueError(f"Order {order_id} not found.")

    recipe = FABRIC_RECIPES.get(order.fabric_type)
    if not recipe:
        raise ValueError(f"No recipe for fabric type '{order.fabric_type}'.")

    # Add wastage to the required meters
    effective_meters = order.meters * (1 + WASTAGE)
    first_yarn_lot = ""

    for material_name, kg_per_meter in recipe:
        material = Material.query.filter_by(name=material_name).first()
        if not material:
            raise ValueError(f"Material '{material_name}' not found in database.")

        needed_kg = effective_meters * kg_per_meter

        # Check we have enough reserved
        if available(material.id) + reserved(material.id) < needed_kg:
            raise ValueError(
                f"Not enough '{material_name}' in stock. "
                f"Need {needed_kg:.2f} kg but only have "
                f"{on_hand(material.id):.2f} kg on hand."
            )

        # Find lot_no from the earliest RECEIPT for traceability
        if not first_yarn_lot and "Yarn" in material_name:
            earliest = (
                StockMovement.query
                .filter_by(material_id=material.id, movement_type="RECEIPT")
                .order_by(StockMovement.created_at)
                .first()
            )
            if earliest:
                first_yarn_lot = earliest.lot_no

        # Create CONSUME movement
        db.session.add(StockMovement(
            material_id=material.id,
            movement_type="CONSUME",
            qty=needed_kg,
            lot_no=first_yarn_lot if "Yarn" in material_name else "",
            order_id=order_id,
        ))

    if commit:
        db.session.commit()

    return first_yarn_lot
