"""
app/models/dispatch.py – Shipment Dispatch & Invoicing Models.
WHAT IT DOES:
  Defines Dispatches, DispatchItems (with DB UNIQUE constraint on roll_id),
  and Invoices.
WHY IT EXISTS:
  Implements the core dispatch and commercial billing chain.
  Guarantees a fabric roll can NEVER be dispatched twice.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class Dispatch(Base):
    """
    WHAT: A physical shipment departing the mill for a buyer.
    WHY: Groups passed rolls for a single buyer into a truck manifest.
    """
    __tablename__ = "dispatches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("buyers.id"), nullable=False, index=True)
    truck_no: Mapped[str] = mapped_column(String(60), nullable=False)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    buyer: Mapped["Buyer"] = relationship("Buyer", back_populates="dispatches")
    items: Mapped[List["DispatchItem"]] = relationship("DispatchItem", back_populates="dispatch", cascade="all, delete-orphan")
    invoice: Mapped[Optional["Invoice"]] = relationship("Invoice", back_populates="dispatch", uselist=False)


class DispatchItem(Base):
    """
    WHAT: A specific fabric roll packed into a dispatch shipment.
    WHY: Rule requirement: DB UNIQUE constraint on roll_id ensures double-dispatching
         is physically impossible at the database level.
    """
    __tablename__ = "dispatch_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    dispatch_id: Mapped[int] = mapped_column(ForeignKey("dispatches.id"), nullable=False, index=True)
    roll_id: Mapped[int] = mapped_column(ForeignKey("fabric_rolls.id"), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    dispatch: Mapped["Dispatch"] = relationship("Dispatch", back_populates="items")
    roll: Mapped["FabricRoll"] = relationship("FabricRoll", back_populates="dispatch_item")


class Invoice(Base):
    """
    WHAT: Commercial invoice generated from a completed dispatch.
    WHY: Represents billing to the buyer with total meters, price, and grand total.
    """
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    dispatch_id: Mapped[int] = mapped_column(ForeignKey("dispatches.id"), nullable=False, unique=True, index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("buyers.id"), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    total_meters: Mapped[float] = mapped_column(Float, nullable=False)
    subtotal: Mapped[float] = mapped_column(Float, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    dispatch: Mapped["Dispatch"] = relationship("Dispatch", back_populates="invoice")
    buyer: Mapped["Buyer"] = relationship("Buyer")
