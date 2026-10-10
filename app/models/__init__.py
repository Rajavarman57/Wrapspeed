"""
app/models/__init__.py – Export all SQLAlchemy 2.0 models.
WHAT IT DOES:
  Imports all models into a single module namespace.
WHY IT EXISTS:
  Allows Base.metadata.create_all and Alembic to discover every table.
"""

from app.models.user import User, Supplier, Buyer
from app.models.yarn import Material, YarnLot, StockMovement
from app.models.order import Order
from app.models.production import Machine, WorkOrder
from app.models.quality import FabricRoll, QCRecord
from app.models.dispatch import Dispatch, DispatchItem, Invoice
from app.models.audit import AuditLog

__all__ = [
    "User",
    "Supplier",
    "Buyer",
    "Material",
    "YarnLot",
    "StockMovement",
    "Order",
    "Machine",
    "WorkOrder",
    "FabricRoll",
    "QCRecord",
    "Dispatch",
    "DispatchItem",
    "Invoice",
    "AuditLog",
]
