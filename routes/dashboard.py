"""
routes/dashboard.py – Dashboard and system reset.
Shows overview stats for the owner; reset wipes and re-seeds the database.
"""

from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from routes.auth import role_required
from models import db, Order, Machine, FabricRoll, User
from services import inventory as inv_svc
from services import costing as cost_svc
from config import ORDER_STATUS
from datetime import date

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


# ── Dashboard index ────────────────────────────────────────
@bp.route("/")
@login_required
def index():
    """Show the main dashboard with stats, charts, and alerts."""
    # Counts
    total_orders = Order.query.count()
    active_orders = Order.query.filter(
        Order.status.in_(["WEAVING", "DYEING", "QC"])
    ).count()
    ready_orders = Order.query.filter_by(status="READY").count()
    dispatched_orders = Order.query.filter_by(status="DISPATCHED").count()

    # Machine stats
    machines = Machine.query.all()
    machines_running = sum(1 for m in machines if m.status == "RUNNING")
    machines_breakdown = sum(1 for m in machines if m.status == "BREAKDOWN")

    # Low stock alerts
    low_stock = inv_svc.low_stock_materials()

    # QC pending
    qc_pending = FabricRoll.query.filter_by(qc_status="PENDING").count()

    # Orders by status for chart
    status_counts = {}
    for s in ORDER_STATUS:
        status_counts[s] = Order.query.filter_by(status=s).count()

    # Monthly P&L
    today = date.today()
    pnl = cost_svc.monthly_pnl(today.year, today.month)

    return render_template("dashboard/index.html",
        total_orders=total_orders,
        active_orders=active_orders,
        ready_orders=ready_orders,
        dispatched_orders=dispatched_orders,
        machines_running=machines_running,
        machines_breakdown=machines_breakdown,
        machines_total=len(machines),
        low_stock=low_stock,
        qc_pending=qc_pending,
        status_counts=status_counts,
        pnl=pnl,
    )


# ── Reset (owner only) ────────────────────────────────────
@bp.route("/reset", methods=["POST"])
@role_required("owner")
def reset():
    """Drop all tables, recreate them, and re-seed demo data. Owner only."""
    from seed import seed as run_seed
    # Drop and recreate
    db.drop_all()
    db.create_all()
    # Re-seed (seed() creates its own app context, but we're already in one)
    from werkzeug.security import generate_password_hash
    from models import User, Material, Supplier, Machine, Setting
    from config import DEFAULT_SETTINGS

    users = [
        User(username="owner", name="Rajesh Kumar (Owner)",
             role="owner", password_hash=generate_password_hash("owner")),
        User(username="store", name="Anita Sharma (Store)",
             role="store", password_hash=generate_password_hash("store")),
        User(username="supervisor", name="Vikram Singh (Supervisor)",
             role="supervisor", password_hash=generate_password_hash("supervisor")),
        User(username="qc", name="Priya Patel (QC)",
             role="qc", password_hash=generate_password_hash("qc")),
        User(username="buyer1", name="Textile Traders Pvt Ltd",
             role="buyer", password_hash=generate_password_hash("buyer1")),
        User(username="buyer2", name="Fashion Hub Exports",
             role="buyer", password_hash=generate_password_hash("buyer2")),
    ]
    db.session.add_all(users)

    materials = [
        Material(name="Cotton Yarn", colour="Natural", unit="kg", reorder_level=200),
        Material(name="Polyester Yarn", colour="Natural", unit="kg", reorder_level=150),
        Material(name="Sizing Agent", colour="Clear", unit="kg", reorder_level=50),
        Material(name="Reactive Dye Red", colour="Red", unit="kg", reorder_level=30),
        Material(name="Reactive Dye Blue", colour="Blue", unit="kg", reorder_level=30),
        Material(name="Reactive Dye Black", colour="Black", unit="kg", reorder_level=30),
    ]
    db.session.add_all(materials)

    suppliers = [
        Supplier(name="Yarn World Ltd", contact="yarn@example.com, +91-9800000001"),
        Supplier(name="Chem Supplies India", contact="chem@example.com, +91-9800000002"),
        Supplier(name="Dye Masters Co", contact="dye@example.com, +91-9800000003"),
    ]
    db.session.add_all(suppliers)

    machines = [
        Machine(name="SPIN-01", type="SPINNING", status="IDLE"),
        Machine(name="SPIN-02", type="SPINNING", status="IDLE"),
        Machine(name="WEAVE-01", type="WEAVING", status="IDLE"),
        Machine(name="WEAVE-02", type="WEAVING", status="IDLE"),
        Machine(name="WEAVE-03", type="WEAVING", status="IDLE"),
        Machine(name="DYE-01", type="DYEING", status="IDLE"),
        Machine(name="DYE-02", type="DYEING", status="IDLE"),
    ]
    db.session.add_all(machines)

    for key, value in DEFAULT_SETTINGS.items():
        db.session.add(Setting(key=key, value=value))

    db.session.commit()

    flash("System has been reset with fresh demo data. Please log in again.", "info")
    return redirect(url_for("auth.login"))
