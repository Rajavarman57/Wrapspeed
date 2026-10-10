"""
app/routers/auth.py – Authentication Routes.
WHAT IT DOES:
  Provides login and logout flows using signed session cookies.
WHY IT EXISTS:
  Authenticates users and stores their session in tamper-proof cookies.
"""

from fastapi import APIRouter, Request, Response, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.config import settings
from app.core.security import verify_password, sign_session_data
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """Renders the login form."""
    return templates.TemplateResponse("auth/login.html", {"request": request, "error": None})


@router.post("/login")
def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Validates user credentials and sets a signed session cookie.
    """
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Sign session payload
    token = sign_session_data({"user_id": user.id, "role": user.role, "username": user.username})

    # Redirect based on role
    redirect_url = "/buyer/portal" if user.role == settings.ROLE_BUYER else "/dashboard"
    resp = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
    )
    return resp


@router.get("/logout")
def logout():
    """Clears the session cookie and redirects to login."""
    resp = RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie(settings.SESSION_COOKIE_NAME)
    return resp
