"""Privacy tables: `audit_log` (spec §8.4).

`deletion_request` (spec §8) also belongs here; it isn't built yet.

`audit_log` is **append-only, enforced by the database**: the migration that
creates it installs triggers that reject every `UPDATE`, `DELETE` and
`TRUNCATE`, whichever role is connected. See `docs/data-model.md` → "audit_log"
for why a trigger rather than `GRANT`s. Write entries through
`app.core.audit.record_audit`, never by building `AuditLog` rows by hand.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    """One privacy/config action or sign-in: who did what to which record."""

    __tablename__ = "audit_log"

    # BigInteger: a log only ever grows, and ids are never reused.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # The two actor columns deliberately have **no foreign keys**. Spec §8.3:
    # when a person is hard-deleted, the log is retained and these become
    # dangling ids by design. An FK would either block that delete or — with
    # ON DELETE SET NULL — try to UPDATE this table, which the triggers reject.
    # Null for `system` actions.
    actor_membership_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Set for sign-ins, which happen before a membership is chosen.
    actor_person_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # `<resource>.<verb>`, e.g. `kpi_record.edit`, `permission_matrix.update`.
    action: Mapped[str] = mapped_column(String)
    resource_type: Mapped[str] = mapped_column(String)
    resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(String)
    # Before/after for config-type changes. Must never contain personal data.
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Indexed for the Admin console's date-range filter (spec §2A.10).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
