"""
routes/orders.py – Order management routes.
Create new orders, view details, check availability, and confirm.
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for
from routes.auth import role_required
from models import Order, User
from services import orders as order_svc
from services import costing as cost_svc
from config import FABRIC_RECIPES

bp = Blueprint("orders", __name__, url_prefix="/orders")


# ── Orders index ───────────────────────────────────────────
@bp.route("/")
@role_required("owner", "store", "supervisor")
def index():
    """List all orders with their current status."""
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template("orders/index.html", orders=orders)


# ── New order form ─────────────────────────────────────────
@bp.route("/new", methods=["GET", "POST"])
@role_required("owner", "store")
def new():
    """Show the new order form and handle submission."""
    buyers = User.query.filter_by(role="buyer").order_by(User.name).all()
    fabric_types = list(FABRIC_RECIPES.keys())

    if request.method == "POST":
        try:
            buyer_id = int(request.form.get("buyer_id", 0))
            fabric_type = request.form.get("fabric_type", "")
            colour = request.form.get("colour", "Natural")
            meters = float(request.form.get("meters", 0))
            price_per_meter = float(request.form.get("price_per_meter", 0))
            deadline = request.form.get("deadline", "")

            order = order_svc.create_order(
                buyer_id, fabric_type, colour, meters, price_per_meter, deadline
            )
            flash(f"Order #{order.id} created successfully!", "success")
            return redirect(url_for("orders.detail", order_id=order.id))
        except ValueError as e:
            flash(str(e), "danger")

    return render_template("orders/new.html",
        buyers=buyers, fabric_types=fabric_types,
    )


# ── Order detail ───────────────────────────────────────────
@bp.route("/<int:order_id>")
@role_required("owner", "store", "supervisor")
def detail(order_id):
    """Show full details of an order: BOM, availability, cost, work orders."""
    order = Order.query.get_or_404(order_id)

    # Calculate BOM
    try:
        bom = order_svc.calculate_bom(order.fabric_type, order.meters)
        # Enrich with material names
        from models import Material
        bom_display = []
        for mat_id, kg in bom:
            mat = Material.query.get(mat_id)
            bom_display.append({"name": mat.name, "kg": kg})
    except ValueError:
        bom_display = []

    # Check availability
    try:
        availability = order_svc.check_availability(order_id)
    except ValueError:
        availability = {"can_start": False, "shortages": []}

    # Cost breakdown (only if production has started)
    cost = None
    if order.status not in ("NEW",):
        try:
            cost = cost_svc.order_cost(order_id)
        except ValueError:
            cost = None

    return render_template("orders/detail.html",
        order=order, bom=bom_display,
        availability=availability, cost=cost,
    )


# ── Confirm order ──────────────────────────────────────────
@bp.route("/<int:order_id>/confirm", methods=["POST"])
@role_required("owner", "store")
def confirm(order_id):
    """Confirm an order: reserve materials and advance to WEAVING."""
    try:
        order_svc.confirm_order(order_id)
        flash(f"Order #{order_id} confirmed! Status → WEAVING.", "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("orders.detail", order_id=order_id))
