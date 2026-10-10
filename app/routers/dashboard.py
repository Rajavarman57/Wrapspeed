"""
app/routers/dashboard.py – Executive & Floor Dashboard.
WHAT IT DOES:
  Renders the main mill overview and provides live HTMX polling endpoints.
WHY IT EXISTS:
  Implements the live feel requirement with 5-second polling for machine board and stats.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import require_role
from app.core.config import settings
from app.models.order import Order
from app.models.production import Machine, WorkOrder
from app.models.quality import FabricRoll
from app.models.yarn import Material
from app.services.inventory import get_all_stock_summary

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """Renders the primary mill dashboard."""
    machines = db.query(Machine).order_by(Machine.name).all()
    orders = db.query(Order).order_by(Order.id.desc()).limit(8).all()
    stock_summary = get_all_stock_summary(db)
    low_stock_count = sum(1 for m in stock_summary if m["is_low"])

    total_orders = db.query(Order).count()
    active_machines = db.query(Machine).filter(Machine.status == "RUNNING").count()
    pending_qc = len([r for r in db.query(FabricRoll).all() if r.current_qc_status == "PENDING"])

    return templates.TemplateResponse(
        "dashboard/index.html",
        {
            "request": request,
            "user": user,
            "machines": machines,
            "orders": orders,
            "total_orders": total_orders,
            "active_machines": active_machines,
            "pending_qc": pending_qc,
            "low_stock_count": low_stock_count,
        },
    )


@router.get("/dashboard/machine-board", response_class=HTMLResponse)
def machine_board_partial(
    request: Request,
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """
    WHAT: HTMX partial polled every 5s.
    WHY: Keeps the machine board live without refreshing the entire page.
    """
    machines = db.query(Machine).order_by(Machine.name).all()
    return templates.TemplateResponse(
        "dashboard/machine_board.html",
        {"request": request, "machines": machines, "user": user},
    )
