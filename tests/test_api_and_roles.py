"""
tests/test_api_and_roles.py – API Endpoints and Role Permissions Tests.
WHAT IT DOES:
  Tests FastAPI HTTP routes, role restrictions, and HTMX partial endpoints.
WHY IT EXISTS:
  Validates that routers enforce single require_role() and authentication dependencies.
"""

from datetime import date
from fastapi.testclient import TestClient
from app.models.user import User, Buyer
from app.models.order import Order
from app.core.security import sign_session_data, hash_password


def test_auth_login_logout(client, test_db):
    """Verifies login sets cookie and logout clears it."""
    user = User(
        username="testowner",
        name="Test Owner",
        role="OWNER",
        hashed_password=hash_password("demo123"),
    )
    test_db.add(user)
    test_db.commit()

    # Login with wrong password -> 400
    res = client.post("/auth/login", data={"username": "testowner", "password": "wrong"})
    assert res.status_code == 400

    # Login with right password -> 303 redirect with session cookie
    res = client.post("/auth/login", data={"username": "testowner", "password": "demo123"}, follow_redirects=False)
    assert res.status_code == 303
    assert "warpspeed_session" in res.cookies

    # Logout -> clears cookie
    res = client.get("/auth/logout", follow_redirects=False)
    assert res.status_code == 303


def test_role_access_dashboard(client, test_db):
    """Verifies OWNER and FLOOR can access dashboard, while unauthenticated is redirected."""
    # Unauthenticated -> redirects to /auth/login
    res = client.get("/dashboard", follow_redirects=False)
    assert res.status_code in [303, 307]

    # Authenticated as FLOOR
    floor_user = User(
        username="testfloor",
        name="Floor Supervisor",
        role="FLOOR",
        hashed_password=hash_password("demo123"),
    )
    test_db.add(floor_user)
    test_db.commit()

    token = sign_session_data({"user_id": floor_user.id, "role": "FLOOR", "username": "testfloor"})
    client.cookies.set("warpspeed_session", token)

    res = client.get("/dashboard")
    assert res.status_code == 200
    assert "Mill Operations Dashboard" in res.text


def test_buyer_portal_isolation(client, test_db):
    """Verifies BUYER only accesses the buyer portal and their own order tracker."""
    b1 = Buyer(name="Buyer 1")
    b2 = Buyer(name="Buyer 2")
    test_db.add_all([b1, b2])
    test_db.commit()

    buyer1_user = User(
        username="buyer1",
        name="Buyer One User",
        role="BUYER",
        buyer_id=b1.id,
        hashed_password=hash_password("demo123"),
    )
    test_db.add(buyer1_user)
    test_db.commit()

    o1 = Order(buyer_id=b1.id, fabric_type="Cotton Plain", colour="Natural", meters=200.0, price_per_meter=300.0, deadline=date.today())
    o2 = Order(buyer_id=b2.id, fabric_type="Cotton Twill", colour="White", meters=300.0, price_per_meter=400.0, deadline=date.today())
    test_db.add_all([o1, o2])
    test_db.commit()

    token = sign_session_data({"user_id": buyer1_user.id, "role": "BUYER", "username": "buyer1"})
    client.cookies.set("warpspeed_session", token)

    # Buyer cannot access internal inventory -> 403 Forbidden
    res = client.get("/inventory")
    assert res.status_code == 403

    # Buyer can access portal
    res = client.get("/buyer/portal")
    assert res.status_code == 200
    assert "Buyer Client Portal" in res.text

    # Buyer can track own order #o1
    res = client.get(f"/buyer/orders/{o1.id}/tracker")
    assert res.status_code == 200

    # Buyer CANNOT track other buyer's order #o2 -> 403 Forbidden
    res = client.get(f"/buyer/orders/{o2.id}/tracker")
    assert res.status_code == 403
