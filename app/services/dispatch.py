"""
app/services/dispatch.py – Dispatch Manifest & Invoicing Services.
WHAT IT DOES:
  - Validates and packs rolls for a specific buyer.
  - Generates commercial invoices.
WHY IT EXISTS:
  Implements the core business rules:
  1. Dispatch ONLY passed, same-buyer, unshipped rolls.
  2. Enforces database UNIQUE constraint on dispatch_items.roll_id.
  3. Single atomic database transaction per action.
"""

from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from app.models.user import Buyer
from app.models.quality import FabricRoll
from app.models.dispatch import Dispatch, DispatchItem, Invoice
from app.services.audit import log_write


def get_available_rolls_for_dispatch(db: Session, buyer_id: Optional[int] = None) -> List[FabricRoll]:
    """
    WHAT: Returns rolls eligible for shipment.
    WHY: Implements rule: Rolls must be (1) QC status PASS, (2) not already shipped,
         and (3) belonging to the specified buyer (if provided).
    """
    query = db.query(FabricRoll).filter(~FabricRoll.dispatch_item.has())
    if buyer_id:
        query = query.join(FabricRoll.order).filter(FabricRoll.order.has(buyer_id=buyer_id))

    rolls = query.all()
    # Filter for rolls whose current QC status is PASS
    return [r for r in rolls if r.current_qc_status == "PASS"]


def create_dispatch(
    db: Session,
    buyer_id: int,
    truck_no: str,
    roll_ids: List[int],
    user_id: Optional[int] = None,
) -> Dispatch:
    """
    WHAT: Creates a dispatch shipment and automatically generates its commercial invoice.
    WHY: Implements rules:
         - All rolls must be passed, unshipped, and belong to the same buyer.
         - DB UNIQUE constraint prevents duplicate dispatching.
    """
    if not roll_ids:
        raise ValueError("Cannot create dispatch with zero rolls")

    buyer = db.get(Buyer, buyer_id)
    if not buyer:
        raise ValueError(f"Buyer #{buyer_id} not found")

    rolls = db.query(FabricRoll).filter(FabricRoll.id.in_(roll_ids)).all()
    if len(rolls) != len(roll_ids):
        raise ValueError("One or more selected roll IDs do not exist")

    total_meters = 0.0
    subtotal = 0.0

    for r in rolls:
        # Rule check: QC must be PASS
        if r.current_qc_status != "PASS":
            raise ValueError(f"Roll '{r.roll_code}' cannot be dispatched (QC status: {r.current_qc_status})")
        # Rule check: Must not already be dispatched
        if r.is_dispatched:
            raise ValueError(f"Roll '{r.roll_code}' has already been dispatched")
        # Rule check: Must belong to this buyer
        if not r.order or r.order.buyer_id != buyer_id:
            raise ValueError(f"Roll '{r.roll_code}' belongs to a different buyer")

        total_meters += r.length_m
        price_per_m = r.order.price_per_meter if r.order else 350.0
        subtotal += r.length_m * price_per_m

    # 1. Create Dispatch
    dispatch = Dispatch(
        buyer_id=buyer_id,
        truck_no=truck_no,
        created_by_id=user_id,
    )
    db.add(dispatch)
    db.flush()

    # 2. Add DispatchItems (DB UNIQUE constraint guarantees uniqueness)
    for r in rolls:
        item = DispatchItem(
            dispatch_id=dispatch.id,
            roll_id=r.id,
        )
        db.add(item)

    # 3. Generate Invoice
    tax_amount = round(subtotal * 0.05, 2)  # 5% GST on textiles
    total_amount = round(subtotal + tax_amount, 2)
    invoice_no = f"INV-{datetime.utcnow().strftime('%Y%m')}-{dispatch.id:04d}"

    invoice = Invoice(
        dispatch_id=dispatch.id,
        buyer_id=buyer_id,
        invoice_number=invoice_no,
        total_meters=total_meters,
        subtotal=round(subtotal, 2),
        tax_amount=tax_amount,
        total_amount=total_amount,
    )
    db.add(invoice)

    # 4. Audit Log
    log_write(
        db,
        action="CREATE_DISPATCH",
        entity_type="Dispatch",
        entity_id=dispatch.id,
        user_id=user_id,
        details={
            "buyer_id": buyer_id,
            "truck_no": truck_no,
            "roll_count": len(rolls),
            "invoice_number": invoice_no,
            "total_amount": total_amount,
        },
    )

    db.commit()
    db.refresh(dispatch)
    return dispatch
