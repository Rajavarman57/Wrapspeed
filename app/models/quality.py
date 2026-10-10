"""
app/models/quality.py – Fabric Roll & Append-Only QC Record Models.
WHAT IT DOES:
  Defines physical cut FabricRolls and the immutable QCRecord log.
WHY IT EXISTS:
  Implements the business rule: QC decisions are APPEND-ONLY.
  Every inspection creates a new QCRecord rather than overwriting existing logs.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class FabricRoll(Base):
    """
    WHAT: Individual 50-meter roll of finished fabric with a unique barcode.
    WHY: Represents physical finished goods staged for QC inspection and dispatch.
    """
    __tablename__ = "fabric_rolls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    roll_code: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    work_order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("work_orders.id"), nullable=True)
    machine_id: Mapped[Optional[int]] = mapped_column(ForeignKey("machines.id"), nullable=True)
    yarn_lot_no: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    length_m: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="fabric_rolls")
    work_order: Mapped[Optional["WorkOrder"]] = relationship("WorkOrder", back_populates="fabric_rolls")
    qc_records: Mapped[List["QCRecord"]] = relationship(
        "QCRecord", back_populates="roll", order_by="desc(QCRecord.id)", cascade="all, delete-orphan"
    )
    dispatch_item: Mapped[Optional["DispatchItem"]] = relationship("DispatchItem", back_populates="roll", uselist=False)

    @property
    def current_qc_status(self) -> str:
        """
        WHAT: Returns the outcome of the latest inspection.
        WHY: Default is PENDING until a QC Inspector records a decision.
        """
        if self.qc_records:
            return self.qc_records[0].status
        return "PENDING"

    @property
    def is_dispatched(self) -> bool:
        """Checks if the roll has already been assigned to a dispatch item."""
        return self.dispatch_item is not None


class QCRecord(Base):
    """
    WHAT: Immutable quality control inspection event.
    WHY: Rule requirement: QC decisions are append-only to preserve quality audit trails.
    """
    __tablename__ = "qc_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    roll_id: Mapped[int] = mapped_column(ForeignKey("fabric_rolls.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # PASS, REWORK, REJECT
    defect_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    inspector_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    roll: Mapped["FabricRoll"] = relationship("FabricRoll", back_populates="qc_records")
    inspector: Mapped[Optional["User"]] = relationship("User")
