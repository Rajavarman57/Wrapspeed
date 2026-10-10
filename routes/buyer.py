"""
routes/buyer.py – Buyer portal routes.
Buyers can view their orders and download invoices.
"""

from flask import Blueprint, render_template
from flask_login import current_user
from routes.auth import role_required
from models import Order, Invoice, Dispatch, FabricRoll
from services import production as prod_svc

bp = Blueprint("buyer", __name__, url_prefix="/portal")


# ── Portal index ───────────────────────────────────────────
@bp.route("/")
@role_required("buyer")
def index():
    """Show the buyer's orders with status and dispatch info."""
    orders = Order.query.filter_by(buyer_id=current_user.id).order_by(
        Order.created_at.desc()
    ).all()

    # Get invoices for the buyer
    invoices = Invoice.query.filter_by(buyer_id=current_user.id).order_by(
        Invoice.created_at.desc()
    ).all()

    return render_template("buyer/index.html",
        orders=orders, invoices=invoices,
    )


# ── Order card (HTMX partial) ─────────────────────────────
@bp.route("/order/<int:order_id>")
@role_required("buyer")
def order_card(order_id):
    """Return an order detail card as an HTMX partial."""
    order = Order.query.filter_by(
        id=order_id, buyer_id=current_user.id
    ).first_or_404()

    # Get delay risk
    try:
        risk = prod_svc.delay_risk(order_id)
    except ValueError:
        risk = {"at_risk": False, "projected": None, "days_late": 0}

    # Get rolls for this order
    rolls = FabricRoll.query.filter_by(order_id=order_id).all()

    return render_template("buyer/_order_card.html",
        order=order, risk=risk, rolls=rolls,
    )
