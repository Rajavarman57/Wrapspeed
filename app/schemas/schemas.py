"""
app/schemas/schemas.py – Pydantic validation models (Compatible with v1 & v2).
WHAT IT DOES:
  Defines input request schemas and output serialization models.
WHY IT EXISTS:
  Validates all form and JSON payloads at the router layer before
  invoking business services.
"""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ── User & Auth Schemas ─────────────────────────────────────────
class UserLogin(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class UserOut(BaseModel):
    id: int
    username: str
    name: str
    role: str
    buyer_id: Optional[int] = None

    class Config:
        orm_mode = True
        from_attributes = True


# ── Inventory & Stock Schemas ───────────────────────────────────
class ReceiveStockIn(BaseModel):
    material_id: int
    lot_no: str
    supplier_id: Optional[int] = None
    qty: float = Field(..., gt=0.0)
    unit_cost: float = Field(..., ge=0.0)


class MaterialStockSummary(BaseModel):
    material_id: int
    name: str
    colour: str
    unit: str
    on_hand: float
    reserved: float
    available: float
    reorder_level: float
    is_low: bool


# ── Order Schemas ───────────────────────────────────────────────
class CreateOrderIn(BaseModel):
    buyer_id: int
    fabric_type: str
    colour: str
    meters: float = Field(..., gt=0.0)
    price_per_meter: float = Field(..., gt=0.0)
    deadline: date


class OrderOut(BaseModel):
    id: int
    buyer_id: int
    fabric_type: str
    colour: str
    meters: float
    price_per_meter: Optional[float] = None  # May be stripped for FLOOR
    deadline: date
    confirmed: bool
    status: str
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


# ── Production Schemas ──────────────────────────────────────────
class StartWorkOrderIn(BaseModel):
    order_id: int
    machine_id: int
    stage: str


class LogOutputIn(BaseModel):
    work_order_id: int
    meters: float = Field(..., gt=0.0)


# ── Quality Control Schemas ─────────────────────────────────────
class QCRecordIn(BaseModel):
    roll_id: int
    status: str
    defect_type: Optional[str] = None
    notes: Optional[str] = None


class FabricRollOut(BaseModel):
    id: int
    roll_code: str
    order_id: int
    length_m: float
    qc_status: str
    is_dispatched: bool
    yarn_lot_no: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True


# ── Dispatch & Invoice Schemas ──────────────────────────────────
class CreateDispatchIn(BaseModel):
    buyer_id: int
    truck_no: str
    roll_ids: List[int] = Field(..., min_items=1)


class DispatchOut(BaseModel):
    id: int
    buyer_id: int
    truck_no: str
    roll_count: int
    total_meters: float
    created_at: datetime
    invoice_number: Optional[str] = None


# ── Costing & Financials ────────────────────────────────────────
class OrderCostSummary(BaseModel):
    order_id: int
    meters: float
    material_cost: Optional[float] = None
    wages_cost: Optional[float] = None
    overhead_cost: Optional[float] = None
    total_cost: Optional[float] = None
    revenue: Optional[float] = None
    profit: Optional[float] = None
    margin_pct: Optional[float] = None
