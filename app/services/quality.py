"""
app/services/quality.py – Quality Control & In-Memory QR Services.
WHAT IT DOES:
  - Records append-only QC decisions (PASS, REWORK, REJECT).
  - Generates roll QR codes in-memory as base64/PNG without touching disk.
  - Traces full roll provenance from yarn lot to dispatch.
WHY IT EXISTS:
  Implements the core business rules:
  1. QC decisions are strictly append-only.
  2. No local disk writes at runtime (in-memory streaming only).
"""

import io
import base64
import qrcode
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from app.models.quality import FabricRoll, QCRecord
from app.services.audit import log_write


def record_qc_decision(
    db: Session,
    roll_id: int,
    status: str,
    defect_type: Optional[str] = None,
    notes: Optional[str] = None,
    inspector_id: Optional[int] = None,
) -> QCRecord:
    """
    WHAT: Logs a quality control decision for a fabric roll.
    WHY: Implements rule: QC decisions are strictly append-only.
         Every decision creates an immutable new QCRecord row.
    """
    if status not in ["PASS", "REWORK", "REJECT"]:
        raise ValueError(f"Invalid QC status '{status}'. Must be PASS, REWORK, or REJECT")

    roll = db.get(FabricRoll, roll_id)
    if not roll:
        raise ValueError(f"FabricRoll #{roll_id} not found")

    record = QCRecord(
        roll_id=roll.id,
        status=status,
        defect_type=defect_type,
        notes=notes,
        inspector_id=inspector_id,
    )
    db.add(record)
    db.flush()

    log_write(
        db,
        action="RECORD_QC_DECISION",
        entity_type="FabricRoll",
        entity_id=roll.id,
        user_id=inspector_id,
        details={"status": status, "defect_type": defect_type, "notes": notes},
    )

    db.commit()
    db.refresh(record)
    return record


def get_qc_queue(db: Session) -> List[FabricRoll]:
    """
    WHAT: Returns all fabric rolls awaiting inspection (current status == PENDING).
    WHY: Feeds the QC inspector queue interface.
    """
    rolls = db.query(FabricRoll).order_by(FabricRoll.id.desc()).all()
    return [r for r in rolls if r.current_qc_status == "PENDING"]


def generate_roll_qr_base64(roll_code: str) -> str:
    """
    WHAT: Generates a QR code image as an in-memory base64 data URL.
    WHY: Implements rule: NO local disk writes at runtime. Generates entirely in RAM.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=6,
        border=2,
    )
    qr.add_data(roll_code)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def trace_roll(db: Session, roll_code: str) -> Dict:
    """
    WHAT: Reconstructs the complete manufacturing and dispatch chain for a fabric roll.
    WHY: Provides rapid root-cause defect analysis and buyer warranty verification.
    """
    roll = db.query(FabricRoll).filter(FabricRoll.roll_code == roll_code).first()
    if not roll:
        raise ValueError(f"FabricRoll code '{roll_code}' not found")

    qc_history = [
        {
            "status": q.status,
            "defect_type": q.defect_type,
            "notes": q.notes,
            "timestamp": q.created_at,
        }
        for q in roll.qc_records
    ]

    dispatch_info = None
    if roll.dispatch_item and roll.dispatch_item.dispatch:
        disp = roll.dispatch_item.dispatch
        dispatch_info = {
            "dispatch_id": disp.id,
            "truck_no": disp.truck_no,
            "date": disp.created_at,
            "buyer": disp.buyer.name if disp.buyer else None,
        }

    return {
        "roll_code": roll.roll_code,
        "length_m": roll.length_m,
        "current_qc": roll.current_qc_status,
        "order_id": roll.order_id,
        "fabric_type": roll.order.fabric_type if roll.order else None,
        "machine": roll.work_order.machine.name if (roll.work_order and roll.work_order.machine) else None,
        "yarn_lot": roll.yarn_lot_no,
        "qc_history": qc_history,
        "dispatch": dispatch_info,
        "qr_base64": generate_roll_qr_base64(roll.roll_code),
    }
