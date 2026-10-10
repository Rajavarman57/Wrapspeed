"""
app/services/orders.py – Order Management & Stock Reservation Services.
WHAT IT DOES:
  - Calculates BOM (Bill of Materials) including manufacturing wastage.
  - Creates new customer fabric orders.
  - Implements stock reservation with `SELECT ... FOR UPDATE` concurrency lock.
WHY IT EXISTS:
  Implements the core business rules:
  1. Wastage included in yarn requirement.
  2. Reservation locks the Material row using `SELECT ... FOR UPDATE` to prevent race conditions.
  3. Single atomic database transaction per action with full audit logging.
"""

from datetime import date
from typing import Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.db import is_sqlite
from app.models.user import Buyer
from app.models.yarn import Material, StockMovement
from app.models.order import Order
from app.services.inventory import get_material_stock
from app.services.audit import log_write

# Fabric recipes: fabric_type -> list of (material_name, kg_per_meter)
FABRIC_RECIPES = {
    "Cotton Plain": [("Cotton Yarn 30s", 0.15)],
    "Cotton Twill": [("Cotton Yarn 40s", 0.18)],
    "Polyester Satin": [("Polyester Yarn 150D", 0.14)],
    "Blended Drill": [("Blended Yarn 20s", 0.16)],
}


def calculate_bom(fabric_type: str, meters: float) -> List[Dict]:
    """
    WHAT: Computes required yarn materials for an order.
    WHY: Implements rule: Wastage (8%) is strictly included in yarn requirements:
         total_kg = meters * kg_per_meter * (1 + WASTAGE_RATE)
    """
    if fabric_type not in FABRIC_RECIPES:
        # Default recipe fallback
        recipe = [("Cotton Yarn 30s", 0.15)]
    else:
        recipe = FABRIC_RECIPES[fabric_type]

    bom = []
    for mat_name, kg_per_m in recipe:
        net_kg = meters * kg_per_m
        gross_kg = net_kg * (1.0 + settings.WASTAGE_RATE)
        bom.append({
            "material_name": mat_name,
            "net_kg": round(net_kg, 2),
            "gross_kg": round(gross_kg, 2),
            "wastage_rate": settings.WASTAGE_RATE,
        })
    return bom


def create_order(
    db: Session,
    buyer_id: int,
    fabric_type: str,
    colour: str,
    meters: float,
    price_per_meter: float,
    deadline: date,
    user_id: Optional[int] = None,
) -> Order:
    """
    WHAT: Creates a new pending fabric order.
    WHY: Commercial entry point before production begins.
    """
    if meters <= 0:
        raise ValueError("Order meters must be greater than zero")
    if price_per_meter <= 0:
        raise ValueError("Price per meter must be greater than zero")

    buyer = db.get(Buyer, buyer_id)
    if not buyer:
        raise ValueError(f"Buyer #{buyer_id} not found")

    order = Order(
        buyer_id=buyer_id,
        fabric_type=fabric_type,
        colour=colour,
        meters=meters,
        price_per_meter=price_per_meter,
        deadline=deadline,
        confirmed=False,
    )
    db.add(order)
    db.flush()

    log_write(
        db,
        action="CREATE_ORDER",
        entity_type="Order",
        entity_id=order.id,
        user_id=user_id,
        details={
            "buyer_id": buyer_id,
            "fabric_type": fabric_type,
            "meters": meters,
            "price_per_meter": price_per_meter,
        },
    )

    db.commit()
    db.refresh(order)
    return order


def confirm_order_and_reserve_stock(
    db: Session,
    order_id: int,
    user_id: Optional[int] = None,
) -> Order:
    """
    WHAT: Confirms an order and reserves required yarn in the StockMovement ledger.
    WHY: Implements rule: Reservation uses `SELECT ... FOR UPDATE` on the material row
         to prevent concurrent double-booking of raw materials.
    """
    order = db.get(Order, order_id)
    if not order:
        raise ValueError(f"Order #{order_id} not found")
    if order.confirmed:
        raise ValueError(f"Order #{order_id} is already confirmed")

    bom = calculate_bom(order.fabric_type, order.meters)
    shortages = []

    # 1. Lock each required material using SELECT ... FOR UPDATE
    locked_materials = []
    for item in bom:
        mat_name = item["material_name"]
        stmt = select(Material).where(Material.name == mat_name)
        if not is_sqlite:
            # PostgreSQL row-level lock
            stmt = stmt.with_for_update()

        material = db.execute(stmt).scalar_one_or_none()
        if not material:
            raise ValueError(f"Material '{mat_name}' does not exist in inventory catalog")

        stock = get_material_stock(db, material.id)
        required_kg = item["gross_kg"]

        if stock["available"] < required_kg:
            shortages.append(
                f"{material.name}: need {required_kg}kg, only {stock['available']}kg available"
            )

        locked_materials.append((material, required_kg))

    if shortages:
        raise ValueError("Cannot confirm order due to stock shortages: " + "; ".join(shortages))

    # 2. Record RESERVE movements for each material
    for material, required_kg in locked_materials:
        reserve_mv = StockMovement(
            material_id=material.id,
            order_id=order.id,
            movement_type="RESERVE",
            qty=required_kg,
            notes=f"Reserved for Order #{order.id} ({order.fabric_type})",
        )
        db.add(reserve_mv)

    order.confirmed = True

    log_write(
        db,
        action="CONFIRM_ORDER",
        entity_type="Order",
        entity_id=order.id,
        user_id=user_id,
        details={"order_id": order.id, "reserved_materials": [m[0].name for m in locked_materials]},
    )

    db.commit()
    db.refresh(order)
    return order
