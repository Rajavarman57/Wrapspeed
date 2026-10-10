"""
app/main.py – FastAPI Application Entry Point.
WHAT IT DOES:
  - Configures FastAPI, static file mounting, and router registration.
  - Automatically initializes tables and seeds data on first run.
WHY IT EXISTS:
  Coordinates the full unified mini-ERP application.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.config import settings
from app.core.db import engine, Base, SessionLocal
import app.models  # Ensures all models are registered in Base.metadata
from app.routers import (
    auth_router,
    dashboard_router,
    inventory_router,
    orders_router,
    production_router,
    quality_router,
    dispatch_router,
    buyer_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    WHAT: Application lifespan manager.
    WHY: Automatically ensures tables are created and seeds realistic data on first run.
    """
    # 1. Create database tables
    Base.metadata.create_all(bind=engine)

    # 2. Seed realistic data on first run
    from app.seed import seed_database_if_empty
    db = SessionLocal()
    try:
        seed_database_if_empty(db)
    finally:
        db.close()

    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="Unified Mini-ERP for Everest Textile Mills",
    lifespan=lifespan,
)

# Mount static assets
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Register all thin routers
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(inventory_router)
app.include_router(orders_router)
app.include_router(production_router)
app.include_router(quality_router)
app.include_router(dispatch_router)
app.include_router(buyer_router)


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    Redirects unauthenticated users to /auth/login for HTML requests.
    """
    if exc.status_code == 307 and "Location" in exc.headers:
        return RedirectResponse(url=exc.headers["Location"], status_code=303)
    if exc.status_code == 401 and "text/html" in request.headers.get("Accept", ""):
        return RedirectResponse(url="/auth/login", status_code=303)
    # Default behavior
    from fastapi.exception_handlers import http_exception_handler
    return await http_exception_handler(request, exc)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
