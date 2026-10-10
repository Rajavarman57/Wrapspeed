"""
app/models/yarn.py – Material Master, Yarn Lots & Stock Ledger Models.
WHAT IT DOES:
  Defines Material items, specific physical YarnLots, and the append-only
  StockMovement ledger table.
WHY IT EXISTS:
  Implements the core business rule: stock is NEVER a stored number.
  Available, on-hand, and reserved stock are computed directly from ledger records.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class Material(Base):
    """
    WHAT: Raw yarn or material catalog definition.
    WHY: Stores item specifications and reorder thresholds.
         CRITICAL: Has NO quantity_in_stock column. Stock is computed dynamically.
    """
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    colour: Mapped[str] = mapped_column(String(60), nullable=False, default="Natural")
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="kg")
    reorder_level: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    yarn_lots: Mapped[List["YarnLot"]] = relationship("YarnLot", back_populates="material")
    movements: Mapped[List["StockMovement"]] = relationship("StockMovement", back_populates="material")


class YarnLot(Base):
    """
    WHAT: A specific received physical batch of yarn.
    WHY: Enables lot traceability and FIFO (oldest-lot-first) consumption.
    """
    __tablename__ = "yarn_lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lot_no: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), nullable=False)
    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    initial_qty: Mapped[float] = mapped_column(Float, nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    received_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    material: Mapped["Material"] = relationship("Material", back_populates="yarn_lots")
    supplier: Mapped[Optional["Supplier"]] = relationship("Supplier", back_populates="yarn_lots")
    movements: Mapped[List["StockMovement"]] = relationship("StockMovement", back_populates="yarn_lot")


class StockMovement(Base):
    """
    WHAT: Append-only ledger entry tracking material movements:
          - RECEIPT: Adds physical stock to warehouse
          - RESERVE: Allocates stock to a confirmed order
          - RELEASE: Frees reserved stock
          - CONSUME: Physically uses up yarn in a work order
    WHY: Guarantees complete auditability and prevents stock drift.
    """
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), nullable=False, index=True)
    lot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("yarn_lots.id"), nullable=True)
    order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("orders.id"), nullable=True)
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)  # RECEIPT, RESERVE, RELEASE, CONSUME
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    material: Mapped["Material"] = relationship("Material", back_populates="movements")
    yarn_lot: Mapped[Optional["YarnLot"]] = relationship("YarnLot", back_populates="movements")
    order: Mapped[Optional["Order"]] = relationship("Order", back_populates="stock_movements")
