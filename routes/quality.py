"""
routes/quality.py – Quality control routes.
QC queue, set status, trace rolls, recall lots, and QR code images.
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, Response
from routes.auth import role_required
from services import qc as qc_svc
from config import QC_STATUS

bp = Blueprint("quality", __name__, url_prefix="/quality")


# ── QC index ───────────────────────────────────────────────
@bp.route("/")
@role_required("owner", "qc")
def index():
    """Show the QC queue: all rolls waiting for inspection."""
    queue = qc_svc.qc_queue()
    return render_template("quality/index.html",
        queue=queue, qc_statuses=QC_STATUS,
    )


# ── Set QC status ──────────────────────────────────────────
@bp.route("/set_status", methods=["POST"])
@role_required("owner", "qc")
def set_status():
    """Set the QC result for a roll."""
    try:
        roll_id = int(request.form.get("roll_id", 0))
        status = request.form.get("status", "")
        defect_type = request.form.get("defect_type", "").strip() or None

        qc_svc.set_qc(roll_id, status, defect_type)
        flash(f"Roll marked as {status}.", "success")
    except ValueError as e:
        flash(str(e), "danger")

    return redirect(url_for("quality.index"))


# ── Trace roll ─────────────────────────────────────────────
@bp.route("/trace/<code>")
@role_required("owner", "qc")
def trace(code):
    """Show full traceability for a roll: order, buyer, machine, yarn lot, dispatch."""
    try:
        trace_data = qc_svc.trace_roll(code)
        return render_template("quality/trace.html", trace=trace_data, code=code)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("quality.index"))


# ── Lot recall ─────────────────────────────────────────────
@bp.route("/recall", methods=["GET", "POST"])
@role_required("owner", "qc")
def recall():
    """Find all rolls and buyers affected by a yarn lot number."""
    recall_data = None
    lot_no = ""

    if request.method == "POST":
        lot_no = request.form.get("lot_no", "").strip()
        try:
            recall_data = qc_svc.lot_recall(lot_no)
        except ValueError as e:
            flash(str(e), "danger")
    elif request.args.get("lot_no"):
        lot_no = request.args.get("lot_no", "").strip()
        try:
            recall_data = qc_svc.lot_recall(lot_no)
        except ValueError as e:
            flash(str(e), "danger")

    return render_template("quality/recall.html",
        recall=recall_data, lot_no=lot_no,
    )


# ── QR code image ──────────────────────────────────────────
@bp.route("/qr/<code>")
@role_required("owner", "qc")
def qr(code):
    """Return a QR code PNG image for a roll."""
    try:
        png_bytes = qc_svc.roll_qr_png(code)
        return Response(png_bytes, mimetype="image/png")
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("quality.index"))
