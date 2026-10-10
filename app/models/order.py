"""
app/models/order.py – Customer Orders & Material Requirement Models.
WHAT IT DOES:
  Defines the Order model for fabric production requests.
WHY IT EXISTS:
  Coordinates commercial customer orders with factory production schedules.
  NOTE: Order status is DERIVED dynamically from child work orders and fabric rolls.
"""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import String, Integer, Float, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class Order(Base):
    """
    WHAT: Customer fabric production order placed by a Buyer.
    WHY: Drives yarn reservations, work order scheduling, and dispatch shipments.
    """
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("buyers.id"), nullable=False, index=True)
    fabric_type: Mapped[str] = mapped_column(String(80), nullable=False)
    colour: Mapped[str] = mapped_column(String(60), nullable=False)
    meters: Mapped[float] = mapped_column(Float, nullable=False)
    price_per_meter: Mapped[float] = mapped_column(Float, nullable=False)
    deadline: Mapped[date] = mapped_column(Date, nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    buyer: Mapped["Buyer"] = relationship("Buyer", back_populates="orders")
    work_orders: Mapped[List["WorkOrder"]] = relationship("WorkOrder", back_populates="order", cascade="all, delete-orphan")
    fabric_rolls: Mapped[List["FabricRoll"]] = relationship("FabricRoll", back_populates="order")
    stock_movements: Mapped[List["StockMovement"]] = relationship("StockMovement", back_populates="order")

    def derive_status(self) -> str:
        """
        WHAT: Computes order lifecycle stage from work orders and fabric rolls.
        WHY: Rule requirement: Order status is NEVER stored as a mutable state flag;
             it reflects the earliest unfinished stage on the factory floor.
        """
        if not self.work_orders:
            return "NEW"

        spinning_wos = [wo for wo in self.work_orders if wo.stage == "SPINNING"]
        weaving_wos = [wo for wo in self.work_orders if wo.stage == "WEAVING"]
        dyeing_wos = [wo for wo in self.work_orders if wo.stage == "DYEING"]

        # Check spinning
        if spinning_wos and any(wo.status in ["PENDING", "RUNNING"] for wo in spinning_wos):
            if all(wo.status == "PENDING" and wo.completed_meters == 0 for wo in spinning_wos):
                return "NEW"
            return "SPINNING"

        # Check weaving
        if weaving_wos and any(wo.status in ["PENDING", "RUNNING"] for wo in weaving_wos):
            if all(wo.status == "PENDING" and wo.completed_meters == 0 for wo in weaving_wos):
                return "NEW"
            return "WEAVING"

        # Check dyeing
        if dyeing_wos and any(wo.status in ["PENDING", "RUNNING"] for wo in dyeing_wos):
            return "DYEING"

        # Check fabric rolls QC and dispatch
        if self.fabric_rolls:
            if any(r.current_qc_status == "PENDING" for r in self.fabric_rolls):
                return "QC"
            if all(r.is_dispatched for r in self.fabric_rolls):
                return "DISPATCHED"
            return "READY"

        return "NEW"

    @property
    def status(self) -> str:
        """Convenience property for derived status."""
        return self.derive_status()
