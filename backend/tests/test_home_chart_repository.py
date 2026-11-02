"""Tests for the homepage chart's repository functions (spec §2A.4,
docs/home-chart.md): the per-function default KPI and the monthly rollup."""

from datetime import date
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core.permissions import home_chart_scope
from app.models.attribute import Attribute, AttributeAppliesTo, AttributeDataType
from app.models.kpi import HomeChartDefault, KpiSource
from app.models.membership import Membership, TeamMember
from app.models.org import LC, Function
from app.repositories.attribute import AttributeValidationError
from app.repositories.kpi import (
    list_home_chart_kpis,
    month_starts,
    monthly_totals,
    record_kpi,
    resolve_home_chart_kpi,
    set_home_chart_default,
)
from tests.helpers import (
    YEAR_AGO,
    make_attribute,
    make_function,
    make_kpi_attribute,
    make_lc,
    make_membership,
    make_person,
    make_position,
    make_team,
    make_term,
)

# ---------------------------------------------------------------------------
# Scope by position
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("position_key", "expected"),
    [
        ("member", "team"),
        ("team_leader", "team"),
        ("lcvp", "function"),
        ("lcp", "function"),
        ("mcd", "all"),
        ("mcvp", "all"),
        ("mcp", "all"),
    ],
)
def test_home_chart_scope_follows_position(position_key: str, expected: str) -> None:
    assert home_chart_scope(position_key) == expected


# ---------------------------------------------------------------------------
# Default KPI per function
# ---------------------------------------------------------------------------


def test_set_default_then_replace_then_clear(db_session: Session) -> None:
    function = make_function(db_session)
    first = make_kpi_attribute(db_session, key="test_first")
    second = make_kpi_attribute(db_session, key="test_second", function=function)

    set_home_chart_default(db_session, function_id=function.id, attribute=first)
    assert resolve_home_chart_kpi(db_session, function_id=function.id, kpi_key=None) == first

    set_home_chart_default(db_session, function_id=function.id, attribute=second)
    assert resolve_home_chart_kpi(db_session, function_id=function.id, kpi_key=None) == second

    set_home_chart_default(db_session, function_id=function.id, attribute=None)
    assert db_session.get(HomeChartDefault, function.id) is None
    assert resolve_home_chart_kpi(db_session, function_id=function.id, kpi_key=None) is None


def test_default_must_be_a_kpi(db_session: Session) -> None:
    function = make_function(db_session)
    not_a_kpi = make_attribute(
        db_session, applies_to=AttributeAppliesTo.MEMBERSHIP, data_type=AttributeDataType.NUMBER
    )

    with pytest.raises(AttributeValidationError, match="not a KPI"):
        set_home_chart_default(db_session, function_id=function.id, attribute=not_a_kpi)


def test_default_cannot_belong_to_another_function(db_session: Session) -> None:
    function = make_function(db_session)
    other = make_function(db_session, key="test_other", label="Test Other")
    others_kpi = make_kpi_attribute(db_session, function=other)

    with pytest.raises(AttributeValidationError, match="different function"):
        set_home_chart_default(db_session, function_id=function.id, attribute=others_kpi)


def test_default_cannot_be_inactive(db_session: Session) -> None:
    function = make_function(db_session)
    kpi = make_kpi_attribute(db_session)
    kpi.active = False

    with pytest.raises(AttributeValidationError, match="inactive"):
        set_home_chart_default(db_session, function_id=function.id, attribute=kpi)


def test_a_default_deactivated_later_counts_as_no_default(db_session: Session) -> None:
    function = make_function(db_session)
    kpi = make_kpi_attribute(db_session)
    set_home_chart_default(db_session, function_id=function.id, attribute=kpi)

    kpi.active = False
    db_session.flush()

    assert resolve_home_chart_kpi(db_session, function_id=function.id, kpi_key=None) is None


# ---------------------------------------------------------------------------
# Picking a KPI
# ---------------------------------------------------------------------------


def test_an_explicit_pick_wins_over_the_default(db_session: Session) -> None:
    function = make_function(db_session)
    default = make_kpi_attribute(db_session, key="test_default")
    picked = make_kpi_attribute(db_session, key="test_picked", function=function)
    set_home_chart_default(db_session, function_id=function.id, attribute=default)

    resolved = resolve_home_chart_kpi(db_session, function_id=function.id, kpi_key="test_picked")

    assert resolved == picked


def test_picking_another_functions_kpi_is_rejected(db_session: Session) -> None:
    function = make_function(db_session)
    other = make_function(db_session, key="test_other", label="Test Other")
    make_kpi_attribute(db_session, key="test_others", function=other)

    with pytest.raises(AttributeValidationError, match="different function"):
        resolve_home_chart_kpi(db_session, function_id=function.id, kpi_key="test_others")


def test_picking_an_unknown_kpi_is_rejected(db_session: Session) -> None:
    function = make_function(db_session)

    with pytest.raises(AttributeValidationError, match="Unknown KPI"):
        resolve_home_chart_kpi(db_session, function_id=function.id, kpi_key="test_no_such_kpi")


def test_available_kpis_are_own_and_shared_active_kpis(db_session: Session) -> None:
    function = make_function(db_session)
    other = make_function(db_session, key="test_other", label="Test Other")
    own = make_kpi_attribute(db_session, key="test_own", function=function)
    shared = make_kpi_attribute(db_session, key="test_shared")
    others = make_kpi_attribute(db_session, key="test_others", function=other)
    inactive = make_kpi_attribute(db_session, key="test_inactive", function=function)
    inactive.active = False
    not_a_kpi = make_attribute(db_session, key="test_not_a_kpi")
    db_session.flush()

    available = list_home_chart_kpis(db_session, function_id=function.id)

    # Other tests' or seeded shared KPIs may also be present, so check membership.
    assert own in available
    assert shared in available
    assert others not in available
    assert inactive not in available
    assert not_a_kpi not in available


# ---------------------------------------------------------------------------
# Monthly rollup
# ---------------------------------------------------------------------------


def test_month_starts_crosses_a_year_boundary() -> None:
    assert month_starts(date(2026, 11, 20), date(2027, 2, 3)) == [
        date(2026, 11, 1),
        date(2026, 12, 1),
        date(2027, 1, 1),
        date(2027, 2, 1),
    ]


def _member(
    session: Session, *, email: str, lc: LC, function: Function, team_id: int | None = None
) -> Membership:
    position = make_position(session, key=f"test_pos_{email}", label="Test", rank=1)
    term = make_term(session, name=f"test-term-{email}")
    person = make_person(session, email=email)
    membership = make_membership(
        session, person=person, lc=lc, position=position, term=term, function=function
    )
    if team_id is not None:
        session.add(TeamMember(team_id=team_id, membership_id=membership.id, start_date=YEAR_AGO))
        session.flush()
    return membership


def _log(session: Session, membership: Membership, kpi: Attribute, value: float, day: date) -> None:
    record_kpi(
        session,
        attribute=kpi,
        membership_id=membership.id,
        value_number=value,
        period_start=day,
        period_end=day,
        source=KpiSource.SELF,
        recorded_by_membership_id=membership.id,
    )


def test_monthly_totals_by_scope(db_session: Session) -> None:
    lc = make_lc(db_session, name="test-lc-a")
    other_lc = make_lc(db_session, name="test-lc-b")
    function = make_function(db_session)
    other_function = make_function(db_session, key="test_other", label="Test Other")
    team = make_team(db_session, lc=lc, function=function, term=make_term(db_session))
    kpi = make_kpi_attribute(db_session)

    on_team = _member(
        db_session, email="test_a@aiesec.net", lc=lc, function=function, team_id=team.id
    )
    same_function = _member(db_session, email="test_b@aiesec.net", lc=lc, function=function)
    other_fn = _member(db_session, email="test_c@aiesec.net", lc=lc, function=other_function)
    elsewhere = _member(db_session, email="test_d@aiesec.net", lc=other_lc, function=function)

    _log(db_session, on_team, kpi, 2, date(2026, 6, 3))
    _log(db_session, on_team, kpi, 3, date(2026, 6, 20))  # same month: summed
    _log(db_session, on_team, kpi, 1, date(2026, 7, 1))
    _log(db_session, same_function, kpi, 10, date(2026, 6, 5))
    _log(db_session, other_fn, kpi, 100, date(2026, 6, 5))
    _log(db_session, elsewhere, kpi, 1000, date(2026, 6, 5))
    _log(db_session, on_team, kpi, 9999, date(2026, 9, 1))  # outside the window

    def totals(**scope: Any) -> dict[date, float]:
        """June to August 2026 for this KPI; `scope` picks whose records count."""
        return monthly_totals(
            db_session, attribute_id=kpi.id, start=date(2026, 6, 1), end=date(2026, 8, 31), **scope
        )

    june, july = date(2026, 6, 1), date(2026, 7, 1)

    assert totals(scope="team", team_id=team.id) == {june: 5, july: 1}
    assert totals(scope="function", lc_id=lc.id, function_id=function.id) == {june: 15, july: 1}
    assert totals(scope="all") == {june: 1115, july: 1}


def test_team_scope_without_a_team_is_empty_not_everything(db_session: Session) -> None:
    lc = make_lc(db_session)
    function = make_function(db_session)
    kpi = make_kpi_attribute(db_session)
    member = _member(db_session, email="test_a@aiesec.net", lc=lc, function=function)
    _log(db_session, member, kpi, 5, date(2026, 6, 3))

    totals = monthly_totals(
        db_session,
        attribute_id=kpi.id,
        scope="team",
        team_id=None,
        start=date(2026, 6, 1),
        end=date(2026, 6, 30),
    )

    assert totals == {}
