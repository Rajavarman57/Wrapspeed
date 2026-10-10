"""
services/dispatch.py – Dispatch and invoicing business logic.
Handles shipping rolls to buyers and generating invoices.
"""

import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from models import db, FabricRoll, Dispatch, Invoice, Order, User


# ── available_rolls ────────────────────────────────────────
def available_rolls(buyer_id):
    """
    Get all rolls that belong to a buyer's orders, passed QC, and not yet dispatched.
    These are ready to ship.
    """
    return (
        FabricRoll.query
        .join(Order)
        .filter(
            Order.buyer_id == buyer_id,
            FabricRoll.qc_status == "PASS",
            FabricRoll.dispatch_id.is_(None),
        )
        .order_by(FabricRoll.code)
        .all()
    )


# ── finished_stock ─────────────────────────────────────────
def finished_stock():
    """
    All rolls that have passed QC but haven't been dispatched yet.
    Used for the dispatch index page.
    """
    return (
        FabricRoll.query
        .filter_by(qc_status="PASS", dispatch_id=None)
        .order_by(FabricRoll.code)
        .all()
    )


# ── create_dispatch ────────────────────────────────────────
def create_dispatch(buyer_id, truck_no, roll_ids, commit=True):
    """
    Create a dispatch (shipment) and an invoice for the given rolls.
    Links rolls to the dispatch and calculates the invoice total.
    Also updates order status to DISPATCHED if all its rolls are shipped.
    """
    if not roll_ids:
        raise ValueError("No rolls selected for dispatch.")

    buyer = db.session.get(User, buyer_id)
    if not buyer:
        raise ValueError(f"Buyer {buyer_id} not found.")

    if not truck_no or not truck_no.strip():
        raise ValueError("Truck number is required.")

    # Create the dispatch
    dispatch = Dispatch(
        buyer_id=buyer_id,
        truck_no=truck_no.strip(),
    )
    db.session.add(dispatch)
    db.session.flush()  # Get the dispatch.id

    # Link rolls to dispatch and calculate total
    total_amount = 0.0
    order_ids = set()

    for roll_id in roll_ids:
        roll = db.session.get(FabricRoll, roll_id)
        if not roll:
            raise ValueError(f"Roll {roll_id} not found.")
        if roll.qc_status != "PASS":
            raise ValueError(f"Roll {roll.code} has not passed QC (status: {roll.qc_status}).")
        if roll.dispatch_id is not None:
            raise ValueError(f"Roll {roll.code} has already been dispatched.")

        # Verify this roll belongs to the buyer
        order = roll.order
        if order.buyer_id != buyer_id:
            raise ValueError(f"Roll {roll.code} does not belong to this buyer.")

        roll.dispatch_id = dispatch.id
        total_amount += roll.length_m * order.price_per_meter
        order_ids.add(order.id)

    # Create the invoice
    invoice = Invoice(
        dispatch_id=dispatch.id,
        buyer_id=buyer_id,
        total_amount=round(total_amount, 2),
    )
    db.session.add(invoice)

    # Check if any orders are now fully dispatched
    for oid in order_ids:
        order = db.session.get(Order, oid)
        undispatched = FabricRoll.query.filter_by(
            order_id=oid, dispatch_id=None
        ).filter(FabricRoll.qc_status != "REJECT").count()
        if undispatched == 0 and order.status == "READY":
            order.status = "DISPATCHED"

    if commit:
        db.session.commit()

    return dispatch


# ── invoice_pdf ────────────────────────────────────────────
def invoice_pdf(invoice_id):
    """
    Generate a PDF invoice for a dispatch.
    Returns raw PDF bytes.
    """
    invoice = db.session.get(Invoice, invoice_id)
    if not invoice:
        raise ValueError(f"Invoice {invoice_id} not found.")

    dispatch = invoice.dispatch
    buyer = invoice.buyer
    rolls = FabricRoll.query.filter_by(dispatch_id=dispatch.id).all()

    buf = io.BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # ── Header ─────────────────────────────────────────
    c.setFont("Helvetica-Bold", 20)
    c.drawString(30 * mm, height - 30 * mm, "INVOICE")
    c.setFont("Helvetica", 10)
    c.drawString(30 * mm, height - 38 * mm, "Everest Textile Mills – Warpspeed ERP")

    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(width - 30 * mm, height - 30 * mm, f"Invoice #{invoice.id}")
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 30 * mm, height - 38 * mm,
                      f"Date: {invoice.created_at.strftime('%Y-%m-%d')}")

    # ── Buyer info ─────────────────────────────────────
    y = height - 55 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(30 * mm, y, "Bill To:")
    c.setFont("Helvetica", 10)
    c.drawString(30 * mm, y - 5 * mm, buyer.name)
    c.drawString(30 * mm, y - 10 * mm, f"Truck No: {dispatch.truck_no}")

    # ── Table header ───────────────────────────────────
    y -= 25 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(30 * mm, y, "Roll Code")
    c.drawString(70 * mm, y, "Order #")
    c.drawString(95 * mm, y, "Fabric Type")
    c.drawString(130 * mm, y, "Length (m)")
    c.drawRightString(width - 30 * mm, y, "Amount (₹)")
    c.line(30 * mm, y - 2 * mm, width - 30 * mm, y - 2 * mm)

    # ── Table rows ─────────────────────────────────────
    c.setFont("Helvetica", 9)
    y -= 7 * mm
    for roll in rolls:
        order = roll.order
        amount = roll.length_m * order.price_per_meter
        c.drawString(30 * mm, y, roll.code)
        c.drawString(70 * mm, y, f"#{order.id}")
        c.drawString(95 * mm, y, order.fabric_type)
        c.drawString(130 * mm, y, f"{roll.length_m}")
        c.drawRightString(width - 30 * mm, y, f"₹{amount:,.2f}")
        y -= 5 * mm

        if y < 40 * mm:
            c.showPage()
            y = height - 30 * mm

    # ── Total ──────────────────────────────────────────
    y -= 5 * mm
    c.line(30 * mm, y, width - 30 * mm, y)
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(width - 30 * mm, y, f"Total: ₹{invoice.total_amount:,.2f}")

    # ── Footer ─────────────────────────────────────────
    c.setFont("Helvetica", 8)
    c.drawString(30 * mm, 20 * mm, "Generated by Warpspeed ERP | Everest Textile Mills")

    c.save()
    buf.seek(0)
    return buf.getvalue()
