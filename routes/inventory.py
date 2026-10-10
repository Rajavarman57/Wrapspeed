"""
routes/inventory.py – Inventory management routes.
Shows stock levels and lets store clerks receive raw materials.
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for
from routes.auth import role_required
from models import Material, Supplier
from services import inventory as inv_svc

bp = Blueprint("inventory", __name__, url_prefix="/inventory")


# ── Inventory index ────────────────────────────────────────
@bp.route("/")
@role_required("owner", "store")
def index():
    """Show stock summary table with on-hand, reserved, available levels."""
    summary = inv_svc.stock_summary()
    materials = Material.query.order_by(Material.name).all()
    suppliers = Supplier.query.order_by(Supplier.name).all()
    return render_template("inventory/index.html",
        summary=summary, materials=materials, suppliers=suppliers,
    )


# ── Receive stock ──────────────────────────────────────────
@bp.route("/receive", methods=["POST"])
@role_required("owner", "store")
def receive():
    """Process a stock receipt form submission."""
    try:
        material_id = int(request.form.get("material_id", 0))
        qty = float(request.form.get("qty", 0))
        lot_no = request.form.get("lot_no", "").strip()
        supplier_id = int(request.form.get("supplier_id", 0))
        unit_cost = float(request.form.get("unit_cost", 0))

        if not lot_no:
            raise ValueError("Lot number is required.")
        if unit_cost <= 0:
            raise ValueError("Unit cost must be greater than zero.")

        inv_svc.receive_stock(material_id, qty, lot_no, supplier_id, unit_cost)
        flash(f"Received {qty} kg successfully!", "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("inventory.index"))
