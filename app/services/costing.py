"""
app/services/costing.py – Manufacturing Costing & Profit Analytics.
WHAT IT DOES:
  Calculates raw material cost, operator wages, overhead allocation,
  and profit margin for customer orders.
WHY IT EXISTS:
  Provides factory owners with unit economics while stripping financial
  data server-side for FLOOR role users.
"""

from typing import Dict, Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import sanitize_for_role
from app.models.order import Order
from app.models.yarn import StockMovement
from app.models.production import WorkOrder


def get_order_cost_and_profit(
    db: Session,
    order_id: int,
    user_role: str = "OWNER",
) -> Dict:
    """
    WHAT: Computes the complete P&L breakdown for an order.
    WHY: Implements wage rates and overheads per machine-hour, then
         strips money fields server-side if user is FLOOR.
    """
    order = db.get(Order, order_id)
    if not order:
        raise ValueError(f"Order #{order_id} not found")

    # 1. Material Cost from consumed stock movements
    movements = (
        db.query(StockMovement)
        .filter(StockMovement.order_id == order_id, StockMovement.movement_type == "CONSUME")
        .all()
    )
    material_cost = sum(m.qty * m.unit_cost for m in movements)

    # 2. Machine hours from work orders
    work_orders = db.query(WorkOrder).filter(WorkOrder.order_id == order_id).all()
    total_machine_hours = 0.0
    for wo in work_orders:
        if wo.start_time and wo.end_time:
            duration_secs = (wo.end_time - wo.start_time).total_seconds()
            total_machine_hours += max(0.5, duration_secs / 3600.0)
        else:
            # Estimation based on meters
            total_machine_hours += max(1.0, wo.completed_meters / 50.0)

    # Rates are per MACHINE-HOUR
    wages_cost = total_machine_hours * settings.WAGE_RATE_PER_HOUR
    overhead_cost = total_machine_hours * settings.OVERHEAD_RATE_PER_HOUR

    total_cost = material_cost + wages_cost + overhead_cost
    revenue = order.meters * order.price_per_meter
    profit = revenue - total_cost
    margin_pct = (profit / revenue * 100.0) if revenue > 0 else 0.0

    result = {
        "order_id": order.id,
        "fabric_type": order.fabric_type,
        "meters": order.meters,
        "price_per_meter": round(order.price_per_meter, 2),
        "machine_hours": round(total_machine_hours, 2),
        "material_cost": round(material_cost, 2),
        "wages_cost": round(wages_cost, 2),
        "overhead_cost": round(overhead_cost, 2),
        "total_cost": round(total_cost, 2),
        "revenue": round(revenue, 2),
        "profit": round(profit, 2),
        "margin_pct": round(margin_pct, 1),
    }

    # Enforce server-side money redaction for FLOOR workers
    return sanitize_for_role(result, user_role)
