"""Privacy tables: `audit_log` (and later `deletion_request`).

See `docs/data-model.md` for the full explanation. The audit_log is
append-only — enforced by DB triggers added in its migration.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    """One row per privacy/config action or sign-in.

    No FKs on actor columns by design — spec §8.3: a hard-deleted person
    leaves the log entry intact with a dangling id, which is correct
    behaviour. An FK would block the delete or (with ON DELETE SET NULL)
    try to update the log, which the append-only trigger rejects.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_membership_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_person_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String)
    resource_type: Mapped[str] = mapped_column(String)
    resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(String)
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
