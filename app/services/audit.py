"""
app/services/audit.py – Audit Logging Service.
WHAT IT DOES:
  Appends an audit record to the `audit_logs` table.
WHY IT EXISTS:
  Implements the rule: Audit log on EVERY write operation.
"""

import json
from typing import Optional, Any
from sqlalchemy.orm import Session
from app.models.audit import AuditLog


def log_write(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: Optional[int],
    user_id: Optional[int] = None,
    details: Optional[Any] = None,
) -> AuditLog:
    """
    WHAT: Creates an audit log record within the current transaction.
    WHY: Preserves an unalterable history of who modified which entity and why.
    """
    details_str = None
    if details is not None:
        if isinstance(details, (dict, list)):
            details_str = json.dumps(details, default=str)
        else:
            details_str = str(details)

    log_entry = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        details=details_str,
    )
    db.add(log_entry)
    return log_entry
