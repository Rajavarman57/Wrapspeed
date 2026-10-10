"""
app/models/user.py – User, Supplier, and Buyer typed models.
WHAT IT DOES:
  Defines users (with OWNER, FLOOR, BUYER roles), suppliers, and buyers.
WHY IT EXISTS:
  Supports authentication, role permissions, and relationship anchors.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class User(Base):
    """
    WHAT: Mill employee or client account.
    WHY: Handles authentication and role-based permissions (OWNER, FLOOR, BUYER).
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # OWNER, FLOOR, BUYER
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    buyer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("buyers.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    buyer: Mapped[Optional["Buyer"]] = relationship("Buyer", back_populates="users")


class Supplier(Base):
    """
    WHAT: Raw yarn and material vendor.
    WHY: Tracks yarn provenance for quality audits and lot tracing.
    """
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    contact: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    yarn_lots: Mapped[List["YarnLot"]] = relationship("YarnLot", back_populates="supplier")


class Buyer(Base):
    """
    WHAT: Fabric customer placing orders.
    WHY: Connects orders, dispatches, and invoices to client portals.
    """
    __tablename__ = "buyers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    contact: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    users: Mapped[List["User"]] = relationship("User", back_populates="buyer")
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="buyer")
    dispatches: Mapped[List["Dispatch"]] = relationship("Dispatch", back_populates="buyer")
