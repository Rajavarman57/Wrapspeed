"""
app/core/db.py – SQLAlchemy 2.0 Database Engine & Session Management.
WHAT IT DOES:
  Creates the database engine, session factory, base model class, and FastAPI
  database dependency (`get_db`).
WHY IT EXISTS:
  Manages database connection pooling, transactions, and session lifecycle
  cleanly across requests.
"""

from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from app.core.config import settings

# Determine if we are running against SQLite or PostgreSQL
is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# Engine configuration
connect_args = {"check_same_thread": False} if is_sqlite else {}
engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

# Enable WAL mode and foreign keys on SQLite for safe concurrent reads/writes
if is_sqlite:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# Session factory for transactions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """
    WHAT: Base class for all typed SQLAlchemy 2.0 models.
    WHY: Inherits mapped column metadata and registry.
    """
    pass


def get_db() -> Generator[Session, None, None]:
    """
    WHAT: FastAPI dependency that provides a database session per request.
    WHY: Automatically closes the session after the request finishes to prevent leaks.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
