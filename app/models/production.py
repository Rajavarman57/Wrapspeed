"""
app/models/production.py – Machines & Work Orders Models.
WHAT IT DOES:
  Defines machinery on the shop floor and WorkOrders that execute
  spinning, weaving, and dyeing operations.
WHY IT EXISTS:
  Coordinates machine allocation, progress tracking, and breakdown states.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class Machine(Base):
    """
    WHAT: Physical mill machine (Spinning frame, Weaving loom, Dyeing vat).
    WHY: Tracks shop floor machine status and availability.
    """
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)    # SPINNING, WEAVING, DYEING
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="IDLE")  # RUNNING, IDLE, BREAKDOWN
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    work_orders: Mapped[List["WorkOrder"]] = relationship("WorkOrder", back_populates="machine")


class WorkOrder(Base):
    """
    WHAT: Manufacturing job step executing meters on a specific machine.
    WHY: Coordinates spinning, weaving, and dyeing operations for an order.
    """
    __tablename__ = "work_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)    # SPINNING, WEAVING, DYEING
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="PENDING")  # PENDING, RUNNING, DONE
    target_meters: Mapped[float] = mapped_column(Float, nullable=False)
    completed_meters: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="work_orders")
    machine: Mapped["Machine"] = relationship("Machine", back_populates="work_orders")
    fabric_rolls: Mapped[List["FabricRoll"]] = relationship("FabricRoll", back_populates="work_order")
