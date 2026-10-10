"""
routes/dispatch.py – Dispatch and invoicing routes.
Ship rolls to buyers, generate PDF invoices.
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, Response
from routes.auth import role_required
from models import User, Invoice, Dispatch
from services import dispatch as disp_svc

bp = Blueprint("dispatch", __name__, url_prefix="/dispatch")


# ── Dispatch index ─────────────────────────────────────────
@bp.route("/")
@role_required("owner", "store")
def index():
    """Show finished stock ready for dispatch and past dispatches."""
    finished = disp_svc.finished_stock()
    buyers = User.query.filter_by(role="buyer").order_by(User.name).all()
    dispatches = Dispatch.query.order_by(Dispatch.created_at.desc()).all()
    return render_template("dispatch/index.html",
        finished=finished, buyers=buyers, dispatches=dispatches,
    )


# ── Create dispatch ────────────────────────────────────────
@bp.route("/create", methods=["POST"])
@role_required("owner", "store")
def create():
    """Create a new dispatch (shipment) with selected rolls."""
    try:
        buyer_id = int(request.form.get("buyer_id", 0))
        truck_no = request.form.get("truck_no", "").strip()
        roll_ids = request.form.getlist("roll_ids", type=int)

        dispatch = disp_svc.create_dispatch(buyer_id, truck_no, roll_ids)
        flash(f"Dispatch #{dispatch.id} created with {len(roll_ids)} rolls!", "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("dispatch.index"))


# ── Invoice PDF ────────────────────────────────────────────
@bp.route("/invoice/<int:invoice_id>")
@role_required("owner", "store", "buyer")
def invoice_pdf(invoice_id):
    """Download a PDF invoice."""
    try:
        pdf_bytes = disp_svc.invoice_pdf(invoice_id)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"inline; filename=invoice_{invoice_id}.pdf"},
        )
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("dispatch.index"))
