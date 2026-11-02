"""Tests for the homepage chart endpoint (spec §2A.4, docs/home-chart.md).

Authentication is replaced with test-double actors, as in `test_lc_api.py`.
The window is the actor's term up to today, so these tests check the months
they logged rather than the total number of points.
"""

from collections.abc import Generator
from dataclasses import dataclass
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.main import app
from app.models.attribute import Attribute
from app.models.kpi import KpiSource
from app.models.membership import Membership, TeamMember
from app.models.org import LC, Function, Position, Term
from app.models.person import Person
from app.repositories.kpi import record_kpi, set_home_chart_default
from tests.helpers import (
    YEAR_AGO,
    make_function,
    make_kpi_attribute,
    make_lc,
    make_membership,
    make_person,
    make_team,
    make_term,
)

URL = "/api/v1/home/chart"


def _get_or_create_position(session: Session, *, key: str, rank: int) -> Position:
    position = session.execute(select(Position).where(Position.key == key)).scalar_one_or_none()
    if position is None:
        position = Position(key=key, label=key.upper(), rank=rank, active=True)
        session.add(position)
    session.flush()
    return position


@dataclass
class HomeApiFixture:
    client: TestClient
    lc: LC
    term: Term
    member: Membership
    function: Function
    default_kpi: Attribute
    other_kpi: Attribute
    others_kpi: Attribute


def _act_as(actor: CurrentActor) -> None:
    app.dependency_overrides[get_current_actor] = lambda: actor


def _actor(person: Person, membership: Membership) -> CurrentActor:
    return CurrentActor(
        person=person, active_memberships=[membership], acting_membership=membership
    )


@pytest.fixture
def home_api(db_session: Session) -> Generator[HomeApiFixture, None, None]:
    lc = make_lc(db_session, name="test-home-lc")
    term = make_term(db_session, name="test-home-term")
    function = make_function(db_session, key="test_home_fn", label="Test Home Fn")
    other_function = make_function(db_session, key="test_home_other", label="Test Home Other")
    team = make_team(db_session, lc=lc, function=function, term=term, name="Test Home Team")

    person = make_person(db_session, email="test-home-member@aiesec.net")
    member = make_membership(
        db_session,
        person=person,
        lc=lc,
        position=_get_or_create_position(db_session, key="member", rank=1),
        term=term,
        function=function,
    )
    db_session.add(TeamMember(team_id=team.id, membership_id=member.id, start_date=YEAR_AGO))
    db_session.flush()

    default_kpi = make_kpi_attribute(
        db_session, key="test_home_default", label="Test Default", function=function
    )
    other_kpi = make_kpi_attribute(db_session, key="test_home_shared", label="Test Shared")
    others_kpi = make_kpi_attribute(
        db_session, key="test_home_others", label="Test Others", function=other_function
    )
    set_home_chart_default(db_session, function_id=function.id, attribute=default_kpi)

    app.dependency_overrides[get_db] = lambda: db_session
    _act_as(_actor(person, member))

    with TestClient(app) as client:
        yield HomeApiFixture(client, lc, term, member, function, default_kpi, other_kpi, others_kpi)

    app.dependency_overrides.clear()


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


def test_member_sees_their_teams_default_kpi_month_by_month(
    home_api: HomeApiFixture, db_session: Session
) -> None:
    _log(db_session, home_api.member, home_api.default_kpi, 4, date(2026, 6, 10))
    _log(db_session, home_api.member, home_api.default_kpi, 2, date(2026, 8, 10))

    chart = home_api.client.get(URL).json()

    assert chart["scope"] == "team"
    assert chart["kpi"]["key"] == "test_home_default"
    assert chart["title"] == "Test Default, Test Home Team"
    values = {point["month"]: point["value"] for point in chart["points"]}
    assert values["2026-06"] == 4
    assert values["2026-07"] == 0  # a month with no records is a zero, not a gap
    assert values["2026-08"] == 2


def test_lcvp_sees_their_function_across_teams(
    home_api: HomeApiFixture, db_session: Session
) -> None:
    person = make_person(db_session, email="test-home-lcvp@aiesec.net")
    lcvp = make_membership(
        db_session,
        person=person,
        lc=home_api.lc,
        position=_get_or_create_position(db_session, key="lcvp", rank=3),
        term=home_api.term,
        function=home_api.function,
    )
    _log(db_session, home_api.member, home_api.default_kpi, 4, date(2026, 6, 10))
    _log(db_session, lcvp, home_api.default_kpi, 1, date(2026, 6, 11))  # on no team
    _act_as(_actor(person, lcvp))

    chart = home_api.client.get(URL).json()

    assert chart["scope"] == "function"
    assert chart["title"] == "Test Default, Test Home Fn"
    assert {p["month"]: p["value"] for p in chart["points"]}["2026-06"] == 5


def test_available_kpis_are_own_and_shared(home_api: HomeApiFixture) -> None:
    keys = {kpi["key"] for kpi in home_api.client.get(URL).json()["availableKpis"]}

    assert {"test_home_default", "test_home_shared"} <= keys
    assert "test_home_others" not in keys


def test_picking_a_kpi_plots_that_kpi(home_api: HomeApiFixture, db_session: Session) -> None:
    _log(db_session, home_api.member, home_api.other_kpi, 7, date(2026, 6, 10))

    chart = home_api.client.get(URL, params={"kpi": "test_home_shared"}).json()

    assert chart["kpi"]["key"] == "test_home_shared"
    assert {p["month"]: p["value"] for p in chart["points"]}["2026-06"] == 7


def test_picking_another_functions_kpi_is_rejected(home_api: HomeApiFixture) -> None:
    response = home_api.client.get(URL, params={"kpi": "test_home_others"})

    assert response.status_code == 400


def test_no_records_means_no_points(home_api: HomeApiFixture) -> None:
    chart = home_api.client.get(URL).json()

    assert chart["kpi"]["key"] == "test_home_default"
    assert chart["points"] == []


def test_no_default_means_no_kpi_but_still_lists_choices(
    home_api: HomeApiFixture, db_session: Session
) -> None:
    set_home_chart_default(db_session, function_id=home_api.function.id, attribute=None)

    chart = home_api.client.get(URL).json()

    assert chart["kpi"] is None
    assert chart["points"] == []
    assert chart["availableKpis"]


def test_unallocated_person_is_forbidden(home_api: HomeApiFixture, db_session: Session) -> None:
    person = make_person(db_session, email="test-home-nobody@aiesec.net")
    _act_as(CurrentActor(person=person, active_memberships=[], acting_membership=None))

    assert home_api.client.get(URL).status_code == 403
