"""
routes/wages.py – Wage management routes.
Owner can view and mark wages for workers.
"""

from datetime import date
from flask import Blueprint, render_template, request, flash, redirect, url_for
from routes.auth import role_required
from models import db, WageEntry, WorkOrder, Setting
from services import costing as cost_svc

bp = Blueprint("wages", __name__, url_prefix="/wages")


# ── Wages index ────────────────────────────────────────────
@bp.route("/")
@role_required("owner")
def index():
    """Show wage entries and monthly totals."""
    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))

    # Get wage entries for the month
    entries = WageEntry.query.filter_by(year=year, month=month).order_by(
        WageEntry.marked_at.desc()
    ).all()

    total = cost_svc.wages_total(year, month)

    # Get completed work orders for wage marking
    completed_wos = WorkOrder.query.filter_by(status="DONE").order_by(
        WorkOrder.finished_at.desc()
    ).all()

    # Machine output for chart
    machine_data = cost_svc.machine_output(year, month)

    # Monthly P&L
    pnl = cost_svc.monthly_pnl(year, month)

    return render_template("wages/index.html",
        entries=entries, total=total,
        completed_wos=completed_wos,
        machine_data=machine_data,
        pnl=pnl,
        year=year, month=month,
    )


# ── Mark wages ─────────────────────────────────────────────
@bp.route("/mark", methods=["POST"])
@role_required("owner")
def mark():
    """Record a wage entry for a worker on a completed work order."""
    try:
        work_order_id = int(request.form.get("work_order_id", 0))
        worker_name = request.form.get("worker_name", "").strip()
        meters = float(request.form.get("meters", 0))

        if not worker_name:
            raise ValueError("Worker name is required.")
        if meters <= 0:
            raise ValueError("Meters must be greater than zero.")

        wo = WorkOrder.query.get(work_order_id)
        if not wo:
            raise ValueError(f"Work order {work_order_id} not found.")

        # Calculate wage amount using wage_rate from settings
        wage_rate = float(
            Setting.query.filter_by(key="wage_rate").first().value
        )
        amount = meters * wage_rate

        today = date.today()
        entry = WageEntry(
            work_order_id=work_order_id,
            worker_name=worker_name,
            meters=meters,
            amount=amount,
            year=today.year,
            month=today.month,
        )
        db.session.add(entry)
        db.session.commit()

        flash(f"Wage ₹{amount:,.0f} recorded for {worker_name}.", "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("wages.index"))
