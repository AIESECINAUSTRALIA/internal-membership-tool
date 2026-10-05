"""Privacy tables: `audit_log` (spec §8.4).

`deletion_request` (spec §8) also belongs here; it isn't built yet.

`audit_log` is append-only: write entries through `app.core.audit.record_audit`,
never by building `AuditLog` rows by hand.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base


class AuditLog(Base):
    """One privacy/config action or sign-in: who did what to which record."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    # The two actor columns deliberately have no foreign keys (Spec §8.3).
    actor_membership_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_person_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String)
    resource_type: Mapped[str] = mapped_column(String)
    resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(String)
    diff: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
