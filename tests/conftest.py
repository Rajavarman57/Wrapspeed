"""
tests/conftest.py – Pytest Fixtures for FastAPI & In-Memory Database.
WHAT IT DOES:
  Provides an isolated, in-memory SQLite database session and FastAPI TestClient
  for each test function.
WHY IT EXISTS:
  Ensures every test runs against a clean, isolated database state.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.core.db import Base, get_db
from app.main import app


@pytest.fixture(scope="function")
def test_db():
    """
    Creates a fresh in-memory SQLite database for each test.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db):
    """
    FastAPI TestClient with overridden get_db dependency.
    """
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
