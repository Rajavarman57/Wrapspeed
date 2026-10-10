"""
app/routers/quality.py – Quality Control & Roll Tracing Routes.
WHAT IT DOES:
  Provides the QC inspection queue, records append-only decisions,
  and renders roll traceability with in-memory QR codes.
WHY IT EXISTS:
  Thin router validating inspection inputs and calling quality services.
"""

import io
import qrcode
from fastapi import APIRouter, Request, Response, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import require_role
from app.core.config import settings
from app.models.quality import FabricRoll, QCRecord
from app.services.quality import record_qc_decision, get_qc_queue, trace_roll, generate_roll_qr_base64

router = APIRouter(prefix="/quality", tags=["quality"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def quality_page(
    request: Request,
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """Renders the QC inspection queue and past inspection logs."""
    pending_rolls = get_qc_queue(db)
    recent_records = (
        db.query(QCRecord)
        .order_by(QCRecord.id.desc())
        .limit(20)
        .all()
    )

    return templates.TemplateResponse(
        "quality/index.html",
        {
            "request": request,
            "user": user,
            "pending_rolls": pending_rolls,
            "recent_records": recent_records,
            "error": None,
        },
    )


@router.post("/record")
def record_qc_route(
    roll_id: int = Form(...),
    status: str = Form(...),
    defect_type: str = Form(None),
    notes: str = Form(None),
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """Records an append-only quality control decision."""
    try:
        record_qc_decision(
            db,
            roll_id=roll_id,
            status=status,
            defect_type=defect_type.strip() if defect_type else None,
            notes=notes.strip() if notes else None,
            inspector_id=user["id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return RedirectResponse(url="/quality", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/trace/{roll_code}", response_class=HTMLResponse)
def trace_roll_route(
    roll_code: str,
    request: Request,
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR, settings.ROLE_BUYER)),
    db: Session = Depends(get_db),
):
    """Renders the end-to-end trace genealogy for a roll."""
    try:
        trace_data = trace_roll(db, roll_code=roll_code)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return templates.TemplateResponse(
        "quality/trace.html",
        {"request": request, "user": user, "trace": trace_data},
    )


@router.get("/qr/{roll_code}")
def roll_qr_image(roll_code: str):
    """
    WHAT: Generates a raw PNG QR code directly in RAM.
    WHY: Rule requirement: NO local disk writes at runtime.
    """
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(roll_code)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return Response(content=buf.getvalue(), media_type="image/png")
