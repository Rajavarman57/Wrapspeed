"""
app/routers/buyer.py – Buyer Client Portal Routes.
WHAT IT DOES:
  Provides a read-only portal for buyers to track their own orders and invoices.
WHY IT EXISTS:
  Implements the BUYER role security requirement:
  Buyers can only view their own records with live 5s HTMX order tracking.
"""

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import require_role
from app.core.config import settings
from app.models.order import Order
from app.models.dispatch import Invoice

router = APIRouter(prefix="/buyer", tags=["buyer"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/portal", response_class=HTMLResponse)
def buyer_portal_page(
    request: Request,
    user: dict = Depends(require_role(settings.ROLE_BUYER, settings.ROLE_OWNER)),
    db: Session = Depends(get_db),
):
    """Displays buyer's orders and invoices."""
    buyer_id = user.get("buyer_id")
    if user["role"] == settings.ROLE_OWNER and not buyer_id:
        # Owner can view all or first buyer
        orders = db.query(Order).order_by(Order.id.desc()).all()
        invoices = db.query(Invoice).order_by(Invoice.id.desc()).all()
    else:
        orders = db.query(Order).filter(Order.buyer_id == buyer_id).order_by(Order.id.desc()).all()
        invoices = db.query(Invoice).filter(Invoice.buyer_id == buyer_id).order_by(Invoice.id.desc()).all()

    return templates.TemplateResponse(
        "buyer/index.html",
        {
            "request": request,
            "user": user,
            "orders": orders,
            "invoices": invoices,
        },
    )


@router.get("/orders/{order_id}/tracker", response_class=HTMLResponse)
def buyer_order_tracker_partial(
    order_id: int,
    request: Request,
    user: dict = Depends(require_role(settings.ROLE_BUYER, settings.ROLE_OWNER)),
    db: Session = Depends(get_db),
):
    """
    WHAT: HTMX partial polled every 5s.
    WHY: Gives buyers live visual feedback of their order progressing across stages.
    """
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if user["role"] == settings.ROLE_BUYER and user.get("buyer_id") != order.buyer_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return templates.TemplateResponse(
        "buyer/_order_tracker.html",
        {"request": request, "order": order},
    )
