"""
app/routers/inventory.py – Raw Material Inventory Routes.
WHAT IT DOES:
  Displays the raw material ledger status and handles stock receipts.
WHY IT EXISTS:
  Thin router validating inputs and calling inventory services.
"""

from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import require_role
from app.core.config import settings
from app.models.user import Supplier
from app.models.yarn import Material
from app.services.inventory import get_all_stock_summary, receive_stock

router = APIRouter(prefix="/inventory", tags=["inventory"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def inventory_page(
    request: Request,
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """Renders the inventory overview page."""
    stock_summary = get_all_stock_summary(db)
    suppliers = db.query(Supplier).order_by(Supplier.name).all()
    materials = db.query(Material).order_by(Material.name).all()

    return templates.TemplateResponse(
        "inventory/index.html",
        {
            "request": request,
            "user": user,
            "stock_summary": stock_summary,
            "suppliers": suppliers,
            "materials": materials,
            "message": None,
            "error": None,
        },
    )


@router.post("/receive")
def receive_stock_route(
    request: Request,
    material_id: int = Form(...),
    lot_no: str = Form(...),
    qty: float = Form(...),
    unit_cost: float = Form(...),
    supplier_id: int = Form(None),
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """Processes incoming raw material stock receipts."""
    try:
        receive_stock(
            db,
            material_id=material_id,
            lot_no=lot_no.strip(),
            qty=qty,
            unit_cost=unit_cost,
            supplier_id=supplier_id,
            user_id=user["id"],
        )
    except ValueError as e:
        stock_summary = get_all_stock_summary(db)
        suppliers = db.query(Supplier).all()
        materials = db.query(Material).all()
        return templates.TemplateResponse(
            "inventory/index.html",
            {
                "request": request,
                "user": user,
                "stock_summary": stock_summary,
                "suppliers": suppliers,
                "materials": materials,
                "message": None,
                "error": str(e),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(url="/inventory", status_code=status.HTTP_303_SEE_OTHER)
