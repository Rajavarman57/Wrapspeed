"""
app/core/security.py – Password Hashing, Session Serialization & Security Utilities.
WHAT IT DOES:
  - Cryptographically hashes and verifies user passwords with bcrypt.
  - Signs and verifies secure HTTP session cookies using itsdangerous.
  - Strips financial/monetary fields server-side for FLOOR role users.
WHY IT EXISTS:
  Centralizes authentication and data sanitization logic to enforce
  strict access controls and protect sensitive business financials.
"""

from typing import Any, Dict, List, Union
from passlib.context import CryptContext
from itsdangerous import URLSafeSerializer, BadSignature
from app.core.config import settings

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Session serializer for signing cookies
serializer = URLSafeSerializer(settings.SECRET_KEY, salt="warpspeed-session-salt")

# Sensitive monetary field names to strip server-side for FLOOR roles
MONEY_FIELD_KEYS = {
    "price_per_meter",
    "total_price",
    "unit_cost",
    "material_cost",
    "wages_cost",
    "overhead_cost",
    "total_cost",
    "margin",
    "margin_per_meter",
    "cost_per_meter",
    "revenue",
    "profit",
    "amount",
    "subtotal",
    "tax",
    "grand_total",
}


def hash_password(password: str) -> str:
    """
    WHAT: Hashes plaintext password into a salted bcrypt string.
    WHY: Protects user credentials against database breach leaks.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    WHAT: Checks if plaintext password matches the stored bcrypt hash.
    WHY: Authenticates user credentials on login.
    """
    return pwd_context.verify(plain_password, hashed_password)


def sign_session_data(data: dict) -> str:
    """
    WHAT: Cryptographically signs a dictionary into a tamper-proof cookie string.
    WHY: Prevents users from forging their user_id or role in session cookies.
    """
    return serializer.dumps(data)


def unsign_session_data(token: str) -> Union[dict, None]:
    """
    WHAT: Decodes and verifies a signed session cookie string.
    WHY: Restores user session information while rejecting forged or expired cookies.
    """
    try:
        return serializer.loads(token)
    except (BadSignature, Exception):
        return None


def sanitize_for_role(data: Any, role: str) -> Any:
    """
    WHAT: Recursively removes all monetary fields from dictionaries or objects
          if the user is in the 'FLOOR' role.
    WHY: Business rule requirement: FLOOR workers must NEVER see money fields,
         enforced strictly server-side before rendering or serialization.
    """
    if role != settings.ROLE_FLOOR:
        return data

    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if k.lower() in MONEY_FIELD_KEYS:
                sanitized[k] = None  # Redacted
            else:
                sanitized[k] = sanitize_for_role(v, role)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_for_role(item, role) for item in data]
    return data
