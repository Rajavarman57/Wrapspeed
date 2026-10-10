"""
app/core/deps.py – FastAPI Dependency Injection & Role-Based Access Control.
WHAT IT DOES:
  - Extracts and authenticates the current user from signed session cookies.
  - Implements the single `require_role(*roles)` dependency to protect endpoints.
WHY IT EXISTS:
  Enforces role-based security declaratively at the router level without
  cluttering business logic services.
"""

from typing import Callable, Optional
from fastapi import Request, HTTPException, Depends, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.config import settings
from app.core.security import unsign_session_data


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[dict]:
    """
    WHAT: Extracts the logged-in user dict from session cookie, if present.
    WHY: Allows pages that can be viewed with or without authentication.
    """
    from app.models.user import User

    cookie_val = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not cookie_val:
        return None

    session_data = unsign_session_data(cookie_val)
    if not session_data or "user_id" not in session_data:
        return None

    user = db.query(User).filter(User.id == session_data["user_id"]).first()
    if not user:
        return None

    return {
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "role": user.role,
        "buyer_id": user.buyer_id,
    }


def get_current_user(
    request: Request,
    user_dict: Optional[dict] = Depends(get_current_user_optional)
) -> dict:
    """
    WHAT: Enforces that a user is authenticated.
    WHY: Guards endpoints that require any logged-in user.
    """
    if not user_dict:
        # If HTMX or API request, return 401
        if request.headers.get("HX-Request") or request.headers.get("Accept") == "application/json":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        # Otherwise redirect to login page
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/auth/login"}
        )
    return user_dict


def require_role(*allowed_roles: str) -> Callable:
    """
    WHAT: Factory returning a FastAPI dependency that checks if the current user
          has one of the allowed roles (e.g. OWNER, FLOOR, BUYER).
    WHY: Implements the single unified role checker requested in the specification.
    """
    def role_checker(user: dict = Depends(get_current_user)) -> dict:
        if allowed_roles and user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(allowed_roles)}"
            )
        return user

    return role_checker
