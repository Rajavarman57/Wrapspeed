"""
app/routers/__init__.py – Re-export all FastAPI router instances.
"""
from app.routers.auth import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.inventory import router as inventory_router
from app.routers.orders import router as orders_router
from app.routers.production import router as production_router
from app.routers.quality import router as quality_router
from app.routers.dispatch import router as dispatch_router
from app.routers.buyer import router as buyer_router

__all__ = [
    "auth_router",
    "dashboard_router",
    "inventory_router",
    "orders_router",
    "production_router",
    "quality_router",
    "dispatch_router",
    "buyer_router",
]
