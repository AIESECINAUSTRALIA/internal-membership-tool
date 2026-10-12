"""KPI / productivity records (spec §4.3).

KPIs are catalogued in `attribute` (`applies_to = 'kpi'`, spec §4.2) like any
other attribute, but a KPI's *values* live in their own time-series table
here rather than in `attribute_value` — a KPI is recorded once per member per
reporting period, not once ever, so it doesn't fit `attribute_value`'s
one-row-per-entity shape.

**Grain rule**: one `kpi_record` row per member (`membership_id`) per KPI
(`attribute_id`) per reporting period (`period_start`/`period_end`), or per
discrete event for functions that track events instead of periods. Never
store a pre-summed total — every LC/function/team/date-range rollup is a
`SUM(value_number)` computed at query time (see
`app/repositories/kpi.py::sum_by_function`). This rule is not a DB
constraint (a function might legitimately log more than one event-based
record in the same window) — it's enforced by convention and by
`app/repositories/kpi.py::record_kpi` being the only write path.
"""

import enum
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KpiSource(enum.StrEnum):
    """Where a `kpi_record` came from — structural to how the record was
    produced, so a constrained column rather than an admin-editable lookup."""

    SELF = "self"
    LEADER = "leader"
    IMPORT = "import"
    SYSTEM = "system"


class KpiRecord(Base):
    __tablename__ = "kpi_record"
    __table_args__ = (
        # spec §10: the index dashboards/reports need for a date-range rollup
        # of one KPI, scoped to a member (and, transitively via membership, an
        # LC/function/team).
        Index(
            "ix_kpi_record_attribute_membership_period",
            "attribute_id",
            "membership_id",
            "period_start",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Which KPI. Must reference an attribute row with applies_to = 'kpi' —
    # a plain FK can't express that condition, so it's enforced by
    # app/repositories/kpi.py::record_kpi on write (see docs/data-model.md).
    attribute_id: Mapped[int] = mapped_column(ForeignKey("attribute.id"))
    # Whose contribution. Gives person, LC, function, and term transitively
    # through membership — this table does not duplicate those columns.
    membership_id: Mapped[int] = mapped_column(ForeignKey("membership.id"))
    # Denormalised for fast team rollups (spec §4.3) — the team the member
    # belonged to as of period_start, resolved once at write time by
    # app/repositories/kpi.py::record_kpi. Not kept in sync afterwards: a
    # later team move doesn't rewrite past kpi_record rows, matching the
    # append-only history convention used by membership/team_member.
    team_id: Mapped[int | None] = mapped_column(ForeignKey("team.id"), nullable=True)
    value_number: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    source: Mapped[KpiSource] = mapped_column(
        Enum(KpiSource, name="kpisource", native_enum=False, length=10, create_constraint=True)
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[int] = mapped_column(ForeignKey("membership.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
