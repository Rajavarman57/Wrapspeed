"""
app/routers/dispatch.py – Dispatch & Invoicing Routes.
WHAT IT DOES:
  Displays unshipped passed rolls, creates truck dispatches, and renders invoices.
WHY IT EXISTS:
  Thin router validating shipment manifests and calling dispatch services.
"""

from typing import List
from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import require_role
from app.core.config import settings
from app.models.user import Buyer
from app.models.dispatch import Dispatch, Invoice
from app.services.dispatch import get_available_rolls_for_dispatch, create_dispatch

router = APIRouter(prefix="/dispatch", tags=["dispatch"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def dispatch_page(
    request: Request,
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """Renders the dispatch management screen."""
    available_rolls = get_available_rolls_for_dispatch(db)
    buyers = db.query(Buyer).order_by(Buyer.name).all()
    dispatches = db.query(Dispatch).order_by(Dispatch.id.desc()).limit(15).all()

    return templates.TemplateResponse(
        "dispatch/index.html",
        {
            "request": request,
            "user": user,
            "available_rolls": available_rolls,
            "buyers": buyers,
            "dispatches": dispatches,
            "error": None,
        },
    )


@router.post("/create")
def create_dispatch_route(
    request: Request,
    buyer_id: int = Form(...),
    truck_no: str = Form(...),
    roll_ids: List[int] = Form(...),
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """Creates a dispatch manifest and automatic invoice."""
    try:
        create_dispatch(
            db,
            buyer_id=buyer_id,
            truck_no=truck_no.strip(),
            roll_ids=roll_ids,
            user_id=user["id"],
        )
    except ValueError as e:
        available_rolls = get_available_rolls_for_dispatch(db)
        buyers = db.query(Buyer).all()
        dispatches = db.query(Dispatch).all()
        return templates.TemplateResponse(
            "dispatch/index.html",
            {
                "request": request,
                "user": user,
                "available_rolls": available_rolls,
                "buyers": buyers,
                "dispatches": dispatches,
                "error": str(e),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(url="/dispatch", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/invoice/{invoice_id}", response_class=HTMLResponse)
def view_invoice_page(
    invoice_id: int,
    request: Request,
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_BUYER)),
    db: Session = Depends(get_db),
):
    """Renders a printable invoice document."""
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # If user is BUYER, ensure they own this invoice
    if user["role"] == settings.ROLE_BUYER and user["buyer_id"] != invoice.buyer_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return templates.TemplateResponse(
        "dispatch/invoice.html",
        {"request": request, "user": user, "invoice": invoice},
    )
