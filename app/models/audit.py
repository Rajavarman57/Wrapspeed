"""
app/models/audit.py – System Write Audit Log Model.
WHAT IT DOES:
  Records an immutable trail of every write action across the entire ERP.
WHY IT EXISTS:
  Implements the core business rule: audit log on EVERY write action.
  Provides full accountability (who changed what, when, and with what payload).
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base


class AuditLog(Base):
    """
    WHAT: Immutable audit log entry recorded whenever database state changes.
    WHY: Rule requirement: Guarantees full operational transparency and traceability.
    """
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User")
