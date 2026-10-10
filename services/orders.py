"""
services/orders.py – Order management business logic.
Handles BOM calculation, order creation, availability checks, and confirmation.
"""

from datetime import date
from models import db, Order, Material, User, StockMovement, Setting
from config import FABRIC_RECIPES, WASTAGE, ORDER_STATUS
from services import inventory as inv_svc


# ── calculate_bom ──────────────────────────────────────────
def calculate_bom(fabric_type, meters):
    """
    Bill of Materials: given a fabric type and meters, return the raw
    materials needed as [(material_id, kg), ...].
    Includes the 8% wastage factor.
    """
    recipe = FABRIC_RECIPES.get(fabric_type)
    if not recipe:
        raise ValueError(f"Unknown fabric type '{fabric_type}'.")

    effective_meters = meters * (1 + WASTAGE)
    bom = []

    for material_name, kg_per_meter in recipe:
        material = Material.query.filter_by(name=material_name).first()
        if not material:
            raise ValueError(f"Material '{material_name}' not in database.")
        kg_needed = round(effective_meters * kg_per_meter, 2)
        bom.append((material.id, kg_needed))

    return bom


# ── create_order ───────────────────────────────────────────
def create_order(buyer_id, fabric_type, colour, meters, price_per_meter, deadline):
    """
    Create a new order with status=NEW.
    Validates all inputs before saving.
    """
    # Validate buyer exists and is a buyer role
    buyer = db.session.get(User, buyer_id)
    if not buyer:
        raise ValueError("Buyer not found.")
    if buyer.role != "buyer":
        raise ValueError("Selected user is not a buyer.")

    # Validate fabric type
    if fabric_type not in FABRIC_RECIPES:
        raise ValueError(f"Unknown fabric type '{fabric_type}'.")

    # Validate numeric fields
    if meters <= 0:
        raise ValueError("Meters must be greater than zero.")
    if price_per_meter <= 0:
        raise ValueError("Price per meter must be greater than zero.")

    # Validate deadline
    if isinstance(deadline, str):
        try:
            deadline = date.fromisoformat(deadline)
        except ValueError:
            raise ValueError("Invalid deadline date format. Use YYYY-MM-DD.")
    if deadline <= date.today():
        raise ValueError("Deadline must be in the future.")

    order = Order(
        buyer_id=buyer_id,
        fabric_type=fabric_type,
        colour=colour.strip() if colour else "Natural",
        meters=meters,
        price_per_meter=price_per_meter,
        deadline=deadline,
        status="NEW",
    )
    db.session.add(order)
    db.session.commit()
    return order


# ── check_availability ─────────────────────────────────────
def check_availability(order_id):
    """
    Check whether we have enough stock to start production.
    Returns {can_start: bool, shortages: [{material_id, name, short_by_kg}]}.
    """
    order = db.session.get(Order, order_id)
    if not order:
        raise ValueError(f"Order {order_id} not found.")

    bom = calculate_bom(order.fabric_type, order.meters)
    shortages = []

    for material_id, kg_needed in bom:
        avail = inv_svc.available(material_id)
        if avail < kg_needed:
            material = db.session.get(Material, material_id)
            shortages.append({
                "material_id": material_id,
                "name": material.name,
                "short_by_kg": round(kg_needed - avail, 2),
            })

    return {
        "can_start": len(shortages) == 0,
        "shortages": shortages,
    }


# ── confirm_order ──────────────────────────────────────────
def confirm_order(order_id, commit=True):
    """
    Confirm an order: reserve inventory and advance status to WEAVING.
    This is a compound transaction – calls consume_for_order with commit=False.
    """
    order = db.session.get(Order, order_id)
    if not order:
        raise ValueError(f"Order {order_id} not found.")
    if order.status != "NEW":
        raise ValueError(f"Order can only be confirmed from NEW status (currently {order.status}).")

    # Check availability first
    avail = check_availability(order_id)
    if not avail["can_start"]:
        names = ", ".join(s["name"] for s in avail["shortages"])
        raise ValueError(f"Cannot confirm: shortage of {names}.")

    # Reserve materials (create RESERVE movements)
    bom = calculate_bom(order.fabric_type, order.meters)
    for material_id, kg_needed in bom:
        db.session.add(StockMovement(
            material_id=material_id,
            movement_type="RESERVE",
            qty=kg_needed,
            order_id=order_id,
        ))

    # Advance order status
    order.status = "WEAVING"

    if commit:
        db.session.commit()

    return order


# ── order_status ───────────────────────────────────────────
def order_status(order_id):
    """Return the current status string of an order."""
    order = db.session.get(Order, order_id)
    if not order:
        raise ValueError(f"Order {order_id} not found.")
    return order.status
