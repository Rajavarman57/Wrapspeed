"""
routes/production.py – Production management routes.
Start work orders, log output, manage breakdowns, and the live machine board.
Includes simulation endpoints for demo purposes.
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for
from routes.auth import role_required
from models import Order, Machine, WorkOrder
from services import production as prod_svc
from config import STAGES

bp = Blueprint("production", __name__, url_prefix="/production")


# ── Production index ───────────────────────────────────────
@bp.route("/")
@role_required("owner", "supervisor")
def index():
    """Show production overview: active work orders, machines, and forms."""
    orders_in_production = Order.query.filter(
        Order.status.in_(["WEAVING", "DYEING"])
    ).order_by(Order.id).all()

    machines = Machine.query.order_by(Machine.type, Machine.name).all()
    work_orders = WorkOrder.query.filter(
        WorkOrder.status.in_(["PENDING", "RUNNING"])
    ).order_by(WorkOrder.started_at.desc()).all()

    return render_template("production/index.html",
        orders=orders_in_production,
        machines=machines,
        work_orders=work_orders,
        stages=STAGES,
    )


# ── Machine board (HTMX partial) ──────────────────────────
@bp.route("/board")
@role_required("owner", "supervisor")
def board():
    """Return the machine board as an HTML partial for HTMX polling."""
    board_data = prod_svc.machine_board()
    return render_template("production/_board.html", board=board_data)


# ── Start work order ──────────────────────────────────────
@bp.route("/start", methods=["POST"])
@role_required("owner", "supervisor")
def start():
    """Start a new work order for an order on a machine."""
    try:
        order_id = int(request.form.get("order_id", 0))
        machine_id = int(request.form.get("machine_id", 0))
        stage = request.form.get("stage", "")

        wo = prod_svc.start_work_order(order_id, machine_id, stage)
        flash(f"Work order #{wo.id} started on {wo.machine.name}!", "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("production.index"))


# ── Log output ─────────────────────────────────────────────
@bp.route("/log", methods=["POST"])
@role_required("owner", "supervisor")
def log():
    """Record meters of output on a running work order."""
    try:
        work_order_id = int(request.form.get("work_order_id", 0))
        meters = float(request.form.get("meters", 0))

        wo = prod_svc.log_output(work_order_id, meters)
        flash(f"Logged {meters}m on work order #{wo.id}. "
              f"Total: {wo.produced_meters:.1f}/{wo.target_meters:.1f}m", "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("production.index"))


# ── Report breakdown ───────────────────────────────────────
@bp.route("/breakdown", methods=["POST"])
@role_required("owner", "supervisor")
def breakdown():
    """Mark a machine as broken down."""
    try:
        machine_id = int(request.form.get("machine_id", 0))
        prod_svc.report_breakdown(machine_id)
        flash("Machine marked as BREAKDOWN.", "warning")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("production.index"))


# ── Repair machine ────────────────────────────────────────
@bp.route("/repair", methods=["POST"])
@role_required("owner", "supervisor")
def repair():
    """Mark a broken machine as repaired."""
    try:
        machine_id = int(request.form.get("machine_id", 0))
        prod_svc.repair_machine(machine_id)
        flash("Machine repaired and back online!", "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("production.index"))


# ── Simulation endpoints (for hackathon demo) ─────────────

# Simple in-memory flag to track simulation state
_simulation_running = False
_simulation_work_order_id = None


@bp.route("/simulate_start", methods=["POST"])
@role_required("owner", "supervisor")
def simulate_start():
    """Start automatic production simulation on a work order."""
    global _simulation_running, _simulation_work_order_id
    try:
        work_order_id = int(request.form.get("work_order_id", 0))
        wo = WorkOrder.query.get_or_404(work_order_id)
        if wo.status != "RUNNING":
            raise ValueError("Work order must be RUNNING to simulate.")
        _simulation_running = True
        _simulation_work_order_id = work_order_id
        flash(f"Simulation started for work order #{work_order_id}.", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("production.index"))


@bp.route("/simulate_stop", methods=["POST"])
@role_required("owner", "supervisor")
def simulate_stop():
    """Stop the production simulation."""
    global _simulation_running, _simulation_work_order_id
    _simulation_running = False
    _simulation_work_order_id = None
    flash("Simulation stopped.", "info")
    return redirect(url_for("production.index"))


@bp.route("/simulate_tick", methods=["POST"])
@role_required("owner", "supervisor")
def simulate_tick():
    """
    One tick of the simulation: log 10 meters of output.
    Called by HTMX polling on the production page.
    """
    global _simulation_running, _simulation_work_order_id
    if _simulation_running and _simulation_work_order_id:
        try:
            wo = prod_svc.log_output(_simulation_work_order_id, 10)
            if wo.status == "DONE":
                _simulation_running = False
                _simulation_work_order_id = None
        except ValueError:
            _simulation_running = False
            _simulation_work_order_id = None

    board_data = prod_svc.machine_board()
    return render_template("production/_board.html", board=board_data)
