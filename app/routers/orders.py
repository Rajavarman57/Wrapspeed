"""
app/routers/orders.py – Order Management Routes.
WHAT IT DOES:
  Displays order list, accepts new orders, shows detail with BOM/costing,
  and handles stock reservation confirmations.
WHY IT EXISTS:
  Thin router validating form submissions and calling order services.
"""

from datetime import date
from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import require_role
from app.core.config import settings
from app.core.security import sanitize_for_role
from app.models.user import Buyer
from app.models.order import Order
from app.models.production import Machine
from app.services.orders import create_order, confirm_order_and_reserve_stock, calculate_bom, FABRIC_RECIPES
from app.services.costing import get_order_cost_and_profit

router = APIRouter(prefix="/orders", tags=["orders"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def orders_page(
    request: Request,
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """Renders the orders table and new order form."""
    orders = db.query(Order).order_by(Order.id.desc()).all()
    buyers = db.query(Buyer).order_by(Buyer.name).all()
    fabric_types = list(FABRIC_RECIPES.keys())

    return templates.TemplateResponse(
        "orders/index.html",
        {
            "request": request,
            "user": user,
            "orders": orders,
            "buyers": buyers,
            "fabric_types": fabric_types,
            "error": None,
        },
    )


@router.post("")
@router.post("/")
def create_order_route(
    request: Request,
    buyer_id: int = Form(...),
    fabric_type: str = Form(...),
    colour: str = Form(...),
    meters: float = Form(...),
    price_per_meter: float = Form(...),
    deadline: date = Form(...),
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """Creates a new customer order."""
    try:
        create_order(
            db,
            buyer_id=buyer_id,
            fabric_type=fabric_type,
            colour=colour.strip(),
            meters=meters,
            price_per_meter=price_per_meter,
            deadline=deadline,
            user_id=user["id"],
        )
    except ValueError as e:
        orders = db.query(Order).order_by(Order.id.desc()).all()
        buyers = db.query(Buyer).all()
        return templates.TemplateResponse(
            "orders/index.html",
            {
                "request": request,
                "user": user,
                "orders": orders,
                "buyers": buyers,
                "fabric_types": list(FABRIC_RECIPES.keys()),
                "error": str(e),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(url="/orders", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{order_id}", response_class=HTMLResponse)
def order_detail_page(
    order_id: int,
    request: Request,
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """Displays order details, BOM, and financial analytics."""
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    bom = calculate_bom(order.fabric_type, order.meters)
    costing = get_order_cost_and_profit(db, order.id, user_role=user["role"])
    machines = db.query(Machine).filter(Machine.status != "BREAKDOWN").all()

    return templates.TemplateResponse(
        "orders/detail.html",
        {
            "request": request,
            "user": user,
            "order": order,
            "bom": bom,
            "costing": costing,
            "machines": machines,
            "error": None,
        },
    )


@router.post("/{order_id}/confirm")
def confirm_order_route(
    order_id: int,
    request: Request,
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """Confirms the order and reserves yarn with SELECT ... FOR UPDATE."""
    try:
        confirm_order_and_reserve_stock(db, order_id=order_id, user_id=user["id"])
    except ValueError as e:
        order = db.get(Order, order_id)
        bom = calculate_bom(order.fabric_type, order.meters)
        costing = get_order_cost_and_profit(db, order.id, user_role=user["role"])
        machines = db.query(Machine).all()
        return templates.TemplateResponse(
            "orders/detail.html",
            {
                "request": request,
                "user": user,
                "order": order,
                "bom": bom,
                "costing": costing,
                "machines": machines,
                "error": str(e),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(url=f"/orders/{order_id}", status_code=status.HTTP_303_SEE_OTHER)
