"""Write path and rollup queries for `kpi_record` (spec §4.3).

`record_kpi` is the only place a `kpi_record` row should be created — it
enforces the one thing a plain FK can't (`attribute_id` must point at an
`applies_to = 'kpi'` attribute), applies `attribute.validation`, and resolves
the denormalised `team_id` once at write time. Route new call sites through
it rather than constructing rows directly.

The homepage chart (spec §2A.4, docs/home-chart.md) also lives here: its
per-function default KPI (`home_chart_default`) and its monthly rollup.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Date, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.permissions import HomeChartScope
from app.models.attribute import Attribute, AttributeAppliesTo, AttributeDataType
from app.models.kpi import HomeChartDefault, KpiRecord, KpiSource
from app.models.membership import Membership, TeamMember
from app.models.org import Function
from app.repositories.attribute import AttributeValidationError, validate_and_coerce


def _resolve_team_id(session: Session, membership_id: int, as_of: date) -> int | None:
    """The team `membership_id` belonged to as of `as_of`. A point-in-time
    snapshot taken once at write time (spec §4.3) — a later team move does
    not rewrite past `kpi_record` rows, matching the append-only history
    convention `membership`/`team_member` already use. None if the member
    wasn't on a team as of that date.

    `end_date` is inclusive, so on a handoff day (old team ends the same day
    the new one starts) two rows match. The most recently started team wins;
    `id` breaks any remaining tie, so the result never depends on the order
    Postgres happens to return rows in."""
    stmt = (
        select(TeamMember.team_id)
        .where(
            TeamMember.membership_id == membership_id,
            TeamMember.start_date <= as_of,
            or_(TeamMember.end_date.is_(None), TeamMember.end_date >= as_of),
        )
        .order_by(TeamMember.start_date.desc(), TeamMember.id.desc())
    )
    return session.execute(stmt).scalars().first()


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
    # kpi_record only has value_number, so a KPI must be numeric.
    if attribute.data_type != AttributeDataType.NUMBER:
        raise AttributeValidationError(
            f"{attribute.key}: KPI attributes must have data_type 'number', "
            f"not {attribute.data_type.value!r}"
        )
    # A kpi_record always holds a number. `validate_and_coerce` lets None through
    # (clearing an attribute_value is allowed, even on a retired attribute), so a
    # blank value is refused here rather than failing on the NOT NULL column.
    if value_number is None:
        raise AttributeValidationError(f"{attribute.key}: a KPI record needs a value")
    # Shared with attribute_value writes; the returned column mapping isn't
    # needed here, only the type check and min/max rules (raises on failure).
    validate_and_coerce(attribute, value_number)

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
        recorded_at=datetime.now(UTC),
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

    Records from memberships with no function (`function_id` is NULL, e.g.
    LCP) are grouped into a single `(None, None, total)` row rather than
    dropped, so the per-function totals always add up to the LC total.
    """
    stmt = (
        select(Function.key, Function.label, func.sum(KpiRecord.value_number))
        .join(Membership, Membership.id == KpiRecord.membership_id)
        # Outer join: an inner join would silently drop records from
        # memberships whose function_id is NULL.
        .outerjoin(Function, Function.id == Membership.function_id)
        .where(
            Membership.lc_id == lc_id,
            KpiRecord.attribute_id == attribute_id,
            KpiRecord.period_start <= period_end,
            KpiRecord.period_end >= period_start,
        )
        .group_by(Function.key, Function.label)
    )
    return session.execute(stmt).all()


# ---------------------------------------------------------------------------
# Homepage chart (spec §2A.4, docs/home-chart.md)
# ---------------------------------------------------------------------------


def check_kpi_for_function(attribute: Attribute, function_id: int | None) -> None:
    """The one rule both setting a function's default and picking a KPI on the
    chart share: an active KPI attribute that is this function's own or
    shared by every function (`attribute.function_id` NULL). Raises
    `AttributeValidationError` otherwise."""
    if attribute.applies_to != AttributeAppliesTo.KPI:
        raise AttributeValidationError(f"{attribute.key} is not a KPI attribute")
    if not attribute.active:
        raise AttributeValidationError(f"{attribute.key} is inactive")
    if attribute.function_id not in (None, function_id):
        raise AttributeValidationError(f"{attribute.key} belongs to a different function")


def set_home_chart_default(
    session: Session, *, function_id: int, attribute: Attribute | None
) -> None:
    """Set, replace, or (with None) clear a function's default homepage KPI.
    The only write path for `home_chart_default`."""
    existing = session.get(HomeChartDefault, function_id)
    if attribute is None:
        if existing is not None:
            session.delete(existing)
    else:
        check_kpi_for_function(attribute, function_id)
        if existing is None:
            session.add(HomeChartDefault(function_id=function_id, attribute_id=attribute.id))
        else:
            existing.attribute_id = attribute.id
    session.flush()


def list_home_chart_kpis(session: Session, *, function_id: int | None) -> Sequence[Attribute]:
    """Every KPI a viewer in this function may pick on the homepage chart:
    active, and the function's own or shared. Ordered by label for a dropdown."""
    stmt = (
        select(Attribute)
        .where(
            Attribute.applies_to == AttributeAppliesTo.KPI,
            Attribute.active.is_(True),
            or_(Attribute.function_id.is_(None), Attribute.function_id == function_id),
        )
        .order_by(Attribute.label)
    )
    return session.execute(stmt).scalars().all()


def resolve_home_chart_kpi(
    session: Session, *, function_id: int | None, kpi_key: str | None
) -> Attribute | None:
    """The KPI to plot: the viewer's pick if given, else the function's
    default. None when nothing is picked and there is no usable default.

    A default that has since become unusable (deactivated, or moved to
    another function) counts as no default rather than an error: the viewer
    didn't ask for it, so they shouldn't see a failure. An explicit pick that
    breaks the rule raises `AttributeValidationError`."""
    if kpi_key is None:
        if function_id is None:
            return None
        default = session.get(HomeChartDefault, function_id)
        if default is None:
            return None
        attribute = session.get(Attribute, default.attribute_id)
        if attribute is None:
            return None
        try:
            check_kpi_for_function(attribute, function_id)
        except AttributeValidationError:
            return None
        return attribute

    # One message for every reason a pick is refused (unknown, inactive, not a
    # KPI, another function's). Separate messages would let a viewer find out
    # which KPI keys exist in other functions by trying keys. Admins still get
    # the detailed reasons through `set_home_chart_default`.
    refused = f"{kpi_key!r} is not a KPI you can chart"

    picked = session.execute(select(Attribute).where(Attribute.key == kpi_key)).scalar_one_or_none()
    if picked is None:
        raise AttributeValidationError(refused)
    try:
        check_kpi_for_function(picked, function_id)
    except AttributeValidationError as exc:
        raise AttributeValidationError(refused) from exc
    return picked


def month_starts(start: date, end: date) -> list[date]:
    """The first day of every month from `start`'s month to `end`'s, inclusive."""
    months: list[date] = []
    current = start.replace(day=1)
    while current <= end:
        months.append(current)
        current = date(current.year + current.month // 12, current.month % 12 + 1, 1)
    return months


def monthly_totals(
    session: Session,
    *,
    attribute_id: int,
    scope: HomeChartScope,
    start: date,
    end: date,
    lc_id: int | None = None,
    function_id: int | None = None,
    team_id: int | None = None,
) -> dict[date, float]:
    """`SUM(value_number)` of one KPI per calendar month, for records whose
    `period_start` falls in `[start, end]`. Keyed by the month's first day;
    a month with no records is absent (the caller fills in zeros).

    Scope decides whose records count (spec §2A.4):
    - `team`: records logged against `team_id` (`kpi_record.team_id`, the team
      as of the record's period). No team means nothing to show, so `{}` —
      never an unfiltered total.
    - `function`: memberships in `lc_id` with `function_id`.
    - `all`: every LC.

    A record is bucketed by the month its `period_start` falls in. Records are
    weekly, monthly or per-event (spec §4.3), so they almost never straddle a
    month boundary by much; splitting a value across months would invent data.
    """
    month = cast(func.date_trunc("month", KpiRecord.period_start), Date)
    stmt = (
        select(month, func.sum(KpiRecord.value_number))
        .where(
            KpiRecord.attribute_id == attribute_id,
            KpiRecord.period_start >= start,
            KpiRecord.period_start <= end,
        )
        .group_by(month)
    )
    if scope == "team":
        if team_id is None:
            return {}
        stmt = stmt.where(KpiRecord.team_id == team_id)
    elif scope == "function":
        if lc_id is None:
            return {}
        stmt = stmt.join(Membership, Membership.id == KpiRecord.membership_id).where(
            Membership.lc_id == lc_id,
            # IS NULL when the membership has no function, rather than `= NULL`
            # (which matches nothing).
            Membership.function_id.is_(None)
            if function_id is None
            else Membership.function_id == function_id,
        )
    return {row[0]: float(row[1]) for row in session.execute(stmt).all()}
