"""
app/routers/production.py – Production Floor & Machine Routing.
WHAT IT DOES:
  Manages work orders on spinning, weaving, and dyeing machines.
WHY IT EXISTS:
  Thin router validating manufacturing requests and delegating to production services.
"""

from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import require_role
from app.core.config import settings
from app.models.production import Machine, WorkOrder
from app.models.order import Order
from app.services.production import start_work_order, log_output, report_breakdown, repair_machine

router = APIRouter(prefix="/production", tags=["production"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def production_page(
    request: Request,
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """Renders the factory floor management screen."""
    machines = db.query(Machine).order_by(Machine.name).all()
    active_work_orders = (
        db.query(WorkOrder)
        .filter(WorkOrder.status == "RUNNING")
        .order_by(WorkOrder.id.desc())
        .all()
    )
    confirmed_orders = (
        db.query(Order)
        .filter(Order.confirmed == True)
        .order_by(Order.id.desc())
        .all()
    )

    return templates.TemplateResponse(
        "production/index.html",
        {
            "request": request,
            "user": user,
            "machines": machines,
            "active_work_orders": active_work_orders,
            "confirmed_orders": confirmed_orders,
            "error": None,
        },
    )


@router.post("/start")
def start_work_order_route(
    request: Request,
    order_id: int = Form(...),
    machine_id: int = Form(...),
    stage: str = Form(...),
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """Starts a manufacturing work order."""
    try:
        start_work_order(db, order_id=order_id, machine_id=machine_id, stage=stage, user_id=user["id"])
    except ValueError as e:
        machines = db.query(Machine).all()
        active_wos = db.query(WorkOrder).filter(WorkOrder.status == "RUNNING").all()
        confirmed_orders = db.query(Order).filter(Order.confirmed == True).all()
        return templates.TemplateResponse(
            "production/index.html",
            {
                "request": request,
                "user": user,
                "machines": machines,
                "active_work_orders": active_wos,
                "confirmed_orders": confirmed_orders,
                "error": str(e),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(url="/production", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/log")
def log_output_route(
    request: Request,
    work_order_id: int = Form(...),
    meters: float = Form(...),
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """Logs production meters and cuts fabric rolls if dyeing."""
    try:
        log_output(db, work_order_id=work_order_id, meters=meters, user_id=user["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return RedirectResponse(url="/production", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/breakdown")
def report_breakdown_route(
    machine_id: int = Form(...),
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """Flags a machine in breakdown state."""
    report_breakdown(db, machine_id=machine_id, user_id=user["id"])
    return RedirectResponse(url="/production", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/repair")
def repair_machine_route(
    machine_id: int = Form(...),
    user: dict = Depends(require_role(settings.ROLE_OWNER, settings.ROLE_FLOOR)),
    db: Session = Depends(get_db),
):
    """Restores a machine from breakdown."""
    repair_machine(db, machine_id=machine_id, user_id=user["id"])
    return RedirectResponse(url="/production", status_code=status.HTTP_303_SEE_OTHER)
