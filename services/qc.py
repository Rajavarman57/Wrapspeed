"""
services/qc.py – Quality control business logic.
Handles roll inspection, traceability, lot recall, and QR code generation.
"""

import io
import qrcode
from models import db, FabricRoll, Order, WorkOrder, Machine, User, Dispatch
from config import QC_STATUS


# ── set_qc ─────────────────────────────────────────────────
def set_qc(roll_id, status, defect_type=None, commit=True):
    """
    Set the QC status of a fabric roll (PASS, REWORK, REJECT).
    After all rolls for an order are inspected, auto-advance to READY.
    """
    roll = db.session.get(FabricRoll, roll_id)
    if not roll:
        raise ValueError(f"Roll {roll_id} not found.")

    if status not in QC_STATUS:
        raise ValueError(f"Status must be one of {QC_STATUS}.")

    if status == "PENDING":
        raise ValueError("Cannot set status back to PENDING.")

    roll.qc_status = status
    roll.defect_type = defect_type if status in ("REWORK", "REJECT") else None

    # Check if ALL rolls for this order have been inspected
    order = roll.order
    pending_rolls = FabricRoll.query.filter_by(
        order_id=order.id, qc_status="PENDING"
    ).count()

    # If no more pending rolls and order is in QC, advance to READY
    if pending_rolls == 0 and order.status == "QC":
        order.status = "READY"

    if commit:
        db.session.commit()

    return roll


# ── qc_queue ───────────────────────────────────────────────
def qc_queue():
    """
    Return all fabric rolls that are waiting for QC inspection (status=PENDING).
    """
    return (
        FabricRoll.query
        .filter_by(qc_status="PENDING")
        .order_by(FabricRoll.created_at)
        .all()
    )


# ── trace_roll ─────────────────────────────────────────────
def trace_roll(code):
    """
    Full traceability for a roll: roll → order → buyer → machine → yarn lot → dispatch.
    Returns a dict with all related info.
    """
    roll = FabricRoll.query.filter_by(code=code).first()
    if not roll:
        raise ValueError(f"Roll with code '{code}' not found.")

    order = roll.order
    buyer = order.buyer if order else None

    # Find the machine used
    machine = db.session.get(Machine, roll.machine_id) if roll.machine_id else None

    # Find the dispatch (if shipped)
    dispatch = db.session.get(Dispatch, roll.dispatch_id) if roll.dispatch_id else None

    return {
        "roll": roll,
        "order": order,
        "buyer": buyer,
        "machine": machine,
        "yarn_lot": roll.yarn_lot_no,
        "dispatch": dispatch,
    }


# ── lot_recall ─────────────────────────────────────────────
def lot_recall(lot_no):
    """
    Find all rolls made from a specific yarn lot.
    Useful when a yarn batch is found to be defective.
    Returns {rolls, buyers, buyer_count}.
    """
    if not lot_no:
        raise ValueError("Lot number is required.")

    rolls = FabricRoll.query.filter_by(yarn_lot_no=lot_no).all()

    # Find unique buyers affected
    buyer_ids = set()
    buyers = []
    for roll in rolls:
        order = roll.order
        if order and order.buyer_id not in buyer_ids:
            buyer_ids.add(order.buyer_id)
            buyers.append(order.buyer)

    return {
        "rolls": rolls,
        "buyers": buyers,
        "buyer_count": len(buyers),
    }


# ── roll_qr_png ───────────────────────────────────────────
def roll_qr_png(code):
    """
    Generate a QR code PNG image for a roll code.
    Returns raw bytes that can be sent as an image response.
    """
    roll = FabricRoll.query.filter_by(code=code).first()
    if not roll:
        raise ValueError(f"Roll with code '{code}' not found.")

    # Build QR data with roll info
    qr_data = f"ROLL:{code}|ORDER:{roll.order_id}|LOT:{roll.yarn_lot_no}"

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()
