"""Write path and rollup queries for `kpi_record` (spec §4.3).

`record_kpi` is the only place a `kpi_record` row should be created — it
enforces the one thing a plain FK can't (`attribute_id` must point at an
`applies_to = 'kpi'` attribute), applies `attribute.validation`, and resolves
the denormalised `team_id` once at write time. Route new call sites through
it rather than constructing rows directly.
"""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.attribute import Attribute, AttributeAppliesTo
from app.models.kpi import KpiRecord, KpiSource
from app.models.membership import Membership, TeamMember
from app.models.org import Function
from app.repositories.attribute import AttributeValidationError


def _resolve_team_id(session: Session, membership_id: int, as_of: date) -> int | None:
    """The team `membership_id` belonged to as of `as_of`. A point-in-time
    snapshot taken once at write time (spec §4.3) — a later team move does
    not rewrite past `kpi_record` rows, matching the append-only history
    convention `membership`/`team_member` already use. None if the member
    wasn't on a team as of that date."""
    stmt = select(TeamMember.team_id).where(
        TeamMember.membership_id == membership_id,
        TeamMember.start_date <= as_of,
        or_(TeamMember.end_date.is_(None), TeamMember.end_date >= as_of),
    )
    return session.execute(stmt).scalars().first()


def _validate_value(attribute: Attribute, value_number: float) -> None:
    rules = attribute.validation or {}
    if "min" in rules and value_number < rules["min"]:  # type: ignore[operator]
        raise AttributeValidationError(
            f"{attribute.key}: {value_number} is below the minimum {rules['min']}"
        )
    if "max" in rules and value_number > rules["max"]:  # type: ignore[operator]
        raise AttributeValidationError(
            f"{attribute.key}: {value_number} is above the maximum {rules['max']}"
        )


def record_kpi(
    session: Session,
    *,
    attribute: Attribute,
    membership_id: int,
    value_number: float,
    period_start: date,
    period_end: date,
    source: KpiSource,
    recorded_by_membership_id: int,
    note: str | None = None,
) -> KpiRecord:
    """Insert one `kpi_record` row.

    `attribute` must be a KPI-type attribute (`applies_to = 'kpi'`) — a plain
    FK can't express that condition, so it's checked here instead of at the
    DB layer (see docs/data-model.md).
    """
    if attribute.applies_to != AttributeAppliesTo.KPI:
        raise AttributeValidationError(
            f"{attribute.key} is not a KPI attribute (applies_to={attribute.applies_to})"
        )
    _validate_value(attribute, value_number)

    record = KpiRecord(
        attribute_id=attribute.id,
        membership_id=membership_id,
        team_id=_resolve_team_id(session, membership_id, period_start),
        value_number=value_number,
        period_start=period_start,
        period_end=period_end,
        source=source,
        note=note,
        recorded_by=recorded_by_membership_id,
        recorded_at=datetime.utcnow(),
    )
    session.add(record)
    session.flush()
    return record


def sum_by_function(
    session: Session,
    *,
    lc_id: int,
    attribute_id: int,
    period_start: date,
    period_end: date,
) -> Sequence[Any]:
    """`SUM(value_number)` for one KPI within one LC, grouped by function,
    over every `kpi_record` whose period **overlaps** `[period_start,
    period_end]` — not only records fully contained in it, since a
    dashboard's custom range (spec §6) won't usually line up exactly with
    recorded periods.

    Returns `(function_key, function_label, total)` rows; a function with no
    matching records is simply absent, not returned with a zero total.
    """
    stmt = (
        select(Function.key, Function.label, func.sum(KpiRecord.value_number))
        .join(Membership, Membership.id == KpiRecord.membership_id)
        .join(Function, Function.id == Membership.function_id)
        .where(
            Membership.lc_id == lc_id,
            KpiRecord.attribute_id == attribute_id,
            KpiRecord.period_start <= period_end,
            KpiRecord.period_end >= period_start,
        )
        .group_by(Function.key, Function.label)
    )
    return session.execute(stmt).all()
