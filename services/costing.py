"""
services/costing.py – Financial analysis: cost breakdown, wages, P&L.
Reads settings from the Setting table for wage_rate and overhead_rate.
"""

from models import db, Order, WageEntry, FabricRoll, Invoice, StockMovement, Setting, WorkOrder
from config import WASTAGE


def _get_setting(key, default=0):
    """Helper: fetch a numeric setting from the database."""
    s = Setting.query.filter_by(key=key).first()
    return float(s.value) if s else float(default)


# ── order_cost ─────────────────────────────────────────────
def order_cost(order_id):
    """
    Full cost breakdown for an order.
    Returns {yarn, wages, overhead, total, passed_meters,
             cost_per_meter, margin_per_meter, yield_variance, formula}.
    """
    order = db.session.get(Order, order_id)
    if not order:
        raise ValueError(f"Order {order_id} not found.")

    wage_rate = _get_setting("wage_rate", 120)
    overhead_rate = _get_setting("overhead_rate", 50)

    # Yarn cost = sum of (qty × unit_cost) for CONSUME movements on this order
    yarn_cost = (
        db.session.query(
            db.func.coalesce(
                db.func.sum(StockMovement.qty * StockMovement.unit_cost), 0
            )
        )
        .filter_by(order_id=order_id, movement_type="CONSUME")
        .scalar()
    )
    # If no consume movements have unit_cost, estimate from RECEIPT avg cost
    if yarn_cost == 0:
        # Estimate from receipt averages for materials used
        consume_movs = StockMovement.query.filter_by(
            order_id=order_id, movement_type="CONSUME"
        ).all()
        for mov in consume_movs:
            avg_cost = (
                db.session.query(
                    db.func.coalesce(db.func.avg(StockMovement.unit_cost), 0)
                )
                .filter_by(material_id=mov.material_id, movement_type="RECEIPT")
                .filter(StockMovement.unit_cost > 0)
                .scalar()
            )
            yarn_cost += mov.qty * float(avg_cost)

    yarn_cost = float(yarn_cost)

    # Passed meters = total length of rolls that passed QC
    passed_meters = (
        db.session.query(db.func.coalesce(db.func.sum(FabricRoll.length_m), 0))
        .filter_by(order_id=order_id, qc_status="PASS")
        .scalar()
    )
    passed_meters = float(passed_meters)

    # Wages = passed_meters × wage_rate
    wages = passed_meters * wage_rate

    # Overhead = passed_meters × overhead_rate
    overhead = passed_meters * overhead_rate

    # Total cost
    total = yarn_cost + wages + overhead

    # Cost and margin per meter
    cost_per_meter = total / passed_meters if passed_meters > 0 else 0
    margin_per_meter = order.price_per_meter - cost_per_meter

    # Yield variance: how much wastage differed from expected
    expected_wastage = order.meters * WASTAGE
    actual_wastage = order.meters - passed_meters if passed_meters > 0 else 0
    yield_variance = round(actual_wastage - expected_wastage, 2)

    return {
        "yarn": round(yarn_cost, 2),
        "wages": round(wages, 2),
        "overhead": round(overhead, 2),
        "total": round(total, 2),
        "passed_meters": round(passed_meters, 2),
        "cost_per_meter": round(cost_per_meter, 2),
        "margin_per_meter": round(margin_per_meter, 2),
        "yield_variance": yield_variance,
        "formula": (
            f"Yarn(₹{yarn_cost:.0f}) + "
            f"Wages({passed_meters:.0f}m × ₹{wage_rate}) + "
            f"Overhead({passed_meters:.0f}m × ₹{overhead_rate}) = ₹{total:.0f}"
        ),
    }


# ── wages_total ────────────────────────────────────────────
def wages_total(year, month):
    """Total wages paid in a given month."""
    total = (
        db.session.query(db.func.coalesce(db.func.sum(WageEntry.amount), 0))
        .filter_by(year=year, month=month)
        .scalar()
    )
    return float(total)


# ── monthly_pnl ────────────────────────────────────────────
def monthly_pnl(year, month):
    """
    Profit & Loss for a month.
    Returns {revenue, material_cost, wages, overhead, profit}.
    """
    # Revenue = sum of invoices created in this month
    from sqlalchemy import extract
    revenue = (
        db.session.query(db.func.coalesce(db.func.sum(Invoice.total_amount), 0))
        .filter(
            extract("year", Invoice.created_at) == year,
            extract("month", Invoice.created_at) == month,
        )
        .scalar()
    )

    # Material cost = sum of (qty × unit_cost) for RECEIPT in this month
    material_cost = (
        db.session.query(
            db.func.coalesce(
                db.func.sum(StockMovement.qty * StockMovement.unit_cost), 0
            )
        )
        .filter(
            StockMovement.movement_type == "CONSUME",
            extract("year", StockMovement.created_at) == year,
            extract("month", StockMovement.created_at) == month,
        )
        .scalar()
    )

    wages = wages_total(year, month)

    # Overhead = total meters produced this month × overhead_rate
    overhead_rate = _get_setting("overhead_rate", 50)
    meters_produced = (
        db.session.query(db.func.coalesce(db.func.sum(FabricRoll.length_m), 0))
        .filter(
            extract("year", FabricRoll.created_at) == year,
            extract("month", FabricRoll.created_at) == month,
        )
        .scalar()
    )
    overhead = float(meters_produced) * overhead_rate

    profit = float(revenue) - float(material_cost) - wages - overhead

    return {
        "revenue": round(float(revenue), 2),
        "material_cost": round(float(material_cost), 2),
        "wages": round(wages, 2),
        "overhead": round(overhead, 2),
        "profit": round(profit, 2),
    }


# ── machine_output ─────────────────────────────────────────
def machine_output(year, month):
    """
    Meters produced per machine in a given month.
    Returns [{machine, meters}].
    """
    from sqlalchemy import extract
    from models import Machine

    machines = Machine.query.order_by(Machine.name).all()
    result = []

    for m in machines:
        # Sum produced_meters from work orders that were active this month
        meters = (
            db.session.query(
                db.func.coalesce(db.func.sum(WorkOrder.produced_meters), 0)
            )
            .filter(
                WorkOrder.machine_id == m.id,
                extract("year", WorkOrder.started_at) == year,
                extract("month", WorkOrder.started_at) == month,
            )
            .scalar()
        )
        result.append({
            "machine": m.name,
            "meters": round(float(meters), 1),
        })

    return result
