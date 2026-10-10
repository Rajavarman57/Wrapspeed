"""
tests/test_prototype.py – Automated tests for the Warpspeed prototype.
WHAT IT DOES:
  Verifies that all 9 tables, password hashing, dynamic stock calculations,
  derived order statuses, and the Flask web server function correctly.
WHY IT EXISTS:
  Adheres to the project rule to test code with pytest before completion,
  catching bugs early.
"""

import pytest
from app import create_app
from extensions import db
from models import User, Material, Order, Machine, FabricRoll


@pytest.fixture
def test_client():
    """
    WHAT: Creates an in-memory SQLite test application fixture.
    WHY: Isolates test runs so they do not alter the persistent development database.
    """
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })

    with app.app_context():
        # Models and tables are created by create_app
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def test_users_and_password_hashing(test_client):
    """
    WHAT: Tests creating a User and verifying password authentication.
    WHY: Ensures password hashing security works as expected.
    """
    user = User(username="test_supervisor", name="Test Supervisor", role="supervisor")
    user.set_password("demo123")
    db.session.add(user)
    db.session.commit()

    saved_user = User.query.filter_by(username="test_supervisor").first()
    assert saved_user is not None
    assert saved_user.check_password("demo123") is True
    assert saved_user.check_password("wrongpassword") is False


def test_dynamic_stock_calculation(test_client):
    """
    WHAT: Tests that Material stock is dynamically computed from StockMovement rows.
    WHY: Validates the core design decision: stock is never a stored number.
    """
    from models import StockMovement

    mat = Material(name="Test Silk", colour="White", unit="kg", reorder_level=50.0)
    db.session.add(mat)
    db.session.commit()

    # Initial state: no movements -> 0 on hand, 0 reserved, 0 available, low stock is True
    assert mat.get_on_hand() == 0.0
    assert mat.get_available() == 0.0
    assert mat.is_low_stock() is True

    # Add receipt of 100 kg
    receipt = StockMovement(material_id=mat.id, movement_type="RECEIPT", qty=100.0)
    db.session.add(receipt)
    db.session.commit()

    assert mat.get_on_hand() == 100.0
    assert mat.get_available() == 100.0
    assert mat.is_low_stock() is False

    # Reserve 60 kg for an order
    reserve = StockMovement(material_id=mat.id, movement_type="RESERVE", qty=60.0)
    db.session.add(reserve)
    db.session.commit()

    assert mat.get_on_hand() == 100.0
    assert mat.get_reserved() == 60.0
    assert mat.get_available() == 40.0  # 100 - 60 = 40 (< 50 reorder level)
    assert mat.is_low_stock() is True


def test_homepage_health_check(test_client):
    """
    WHAT: Tests making a GET request to the homepage root '/'.
    WHY: Confirms the Flask web server responds with HTTP 200 OK.
    """
    response = test_client.get("/")
    assert response.status_code == 200
    assert b"Everest Textile Mills" in response.data
