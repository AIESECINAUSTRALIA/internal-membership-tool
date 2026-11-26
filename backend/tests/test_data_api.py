"""Tests for the Data page analytics endpoint (spec §2A.7, §6).

Scope filtering is the core behaviour under test: each scope must only
aggregate the records that fall within its boundary (team / function / lc /
all), and a viewer may not request a scope wider than their grant.
"""

from collections.abc import Generator
from dataclasses import dataclass
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.main import app
from app.models.attribute import Attribute
from app.models.kpi import KpiSource
from app.models.membership import Membership, TeamMember
from app.models.org import LC, Function, LCType, Position, Term
from app.models.person import Person
from app.repositories.kpi import record_kpi, set_home_chart_default
from tests.helpers import (
    make_function,
    make_kpi_attribute,
    make_lc,
    make_membership,
    make_person,
    make_team,
    make_term,
    YEAR_AGO,
    YEAR_AHEAD,
)

URL = "/api/v1/data/chart"

START = "2026-01-01"
END = "2026-12-31"
START_DATE = date(2026, 1, 1)
END_DATE = date(2026, 12, 31)


def _get_or_create_position(session: Session, *, key: str, rank: int) -> Position:
    from sqlalchemy import select

    position = session.execute(select(Position).where(Position.key == key)).scalar_one_or_none()
    if position is None:
        position = Position(key=key, label=key.upper(), rank=rank, active=True)
        session.add(position)
    session.flush()
    return position


@dataclass
class DataApiFixture:
    client: TestClient
    lc: LC
    term: Term
    function: Function
    kpi: Attribute
    team_member_a: Membership
    team_member_b: Membership
    team_id: int


def _act_as(actor: CurrentActor) -> None:
    app.dependency_overrides[get_current_actor] = lambda: actor


def _actor(person: Person, membership: Membership) -> CurrentActor:
    return CurrentActor(
        person=person, active_memberships=[membership], acting_membership=membership
    )


@pytest.fixture
def data_api(db_session: Session) -> Generator[DataApiFixture, None, None]:
    lc = make_lc(db_session, name="test-data-lc")
    term = make_term(db_session, name="test-data-term", start=YEAR_AGO, end=YEAR_AHEAD)
    function = make_function(db_session, key="test_data_fn", label="Test Data Fn")
    team = make_team(db_session, lc=lc, function=function, term=term, name="Test Data Team")
    # Shared KPI (function_id=None) so both function-scoped and function-less (LCP) actors can use it.
    kpi = make_kpi_attribute(db_session, key="test_data_kpi", label="Test KPI")
    set_home_chart_default(db_session, function_id=function.id, attribute=kpi)

    member_pos = _get_or_create_position(db_session, key="member", rank=1)
    tl_pos = _get_or_create_position(db_session, key="team_leader", rank=2)
    lcvp_pos = _get_or_create_position(db_session, key="lcvp", rank=3)

    person_a = make_person(db_session, email="test-data-a@aiesec.net")
    person_b = make_person(db_session, email="test-data-b@aiesec.net")
    mem_a = make_membership(db_session, person=person_a, lc=lc, position=member_pos, term=term, function=function)
    mem_b = make_membership(db_session, person=person_b, lc=lc, position=member_pos, term=term, function=function)
    db_session.add(TeamMember(team_id=team.id, membership_id=mem_a.id, start_date=YEAR_AGO))
    db_session.add(TeamMember(team_id=team.id, membership_id=mem_b.id, start_date=YEAR_AGO))
    db_session.flush()

    # Default viewer: a TL in the same team
    tl_person = make_person(db_session, email="test-data-tl@aiesec.net")
    tl_mem = make_membership(db_session, person=tl_person, lc=lc, position=tl_pos, term=term, function=function)
    db_session.add(TeamMember(team_id=team.id, membership_id=tl_mem.id, start_date=YEAR_AGO))
    db_session.flush()

    app.dependency_overrides[get_db] = lambda: db_session
    _act_as(_actor(tl_person, tl_mem))

    with TestClient(app) as client:
        yield DataApiFixture(
            client=client,
            lc=lc,
            term=term,
            function=function,
            kpi=kpi,
            team_member_a=mem_a,
            team_member_b=mem_b,
            team_id=team.id,
        )

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


def test_team_scope_aggregates_team_records(data_api: DataApiFixture, db_session: Session) -> None:
    _log(db_session, data_api.team_member_a, data_api.kpi, 3.0, date(2026, 3, 1))
    _log(db_session, data_api.team_member_b, data_api.kpi, 2.0, date(2026, 3, 1))

    res = data_api.client.get(URL, params={"scope": "team", "start": START, "end": END}).json()

    assert res["scope"] == "team"
    assert res["kpi"]["key"] == "test_data_kpi"
    assert sum(r["value"] for r in res["summaryRows"]) == pytest.approx(5.0)


def test_team_scope_monthly_points(data_api: DataApiFixture, db_session: Session) -> None:
    _log(db_session, data_api.team_member_a, data_api.kpi, 4.0, date(2026, 3, 10))
    _log(db_session, data_api.team_member_a, data_api.kpi, 1.0, date(2026, 5, 10))

    res = data_api.client.get(URL, params={"scope": "team", "start": START, "end": END}).json()

    months = {p["month"]: p["value"] for p in res["points"]}
    assert months["2026-03"] == pytest.approx(4.0)
    assert months["2026-04"] == pytest.approx(0.0)
    assert months["2026-05"] == pytest.approx(1.0)


def test_function_scope_aggregates_by_team(data_api: DataApiFixture, db_session: Session) -> None:
    lcvp_pos = _get_or_create_position(db_session, key="lcvp", rank=3)
    lcvp_person = make_person(db_session, email="test-data-lcvp@aiesec.net")
    lcvp_mem = make_membership(
        db_session, person=lcvp_person, lc=data_api.lc, position=lcvp_pos, term=data_api.term, function=data_api.function
    )
    _act_as(_actor(lcvp_person, lcvp_mem))

    _log(db_session, data_api.team_member_a, data_api.kpi, 5.0, date(2026, 4, 1))
    _log(db_session, data_api.team_member_b, data_api.kpi, 3.0, date(2026, 4, 1))

    res = data_api.client.get(URL, params={"scope": "function", "start": START, "end": END}).json()

    assert res["scope"] == "function"
    assert len(res["summaryRows"]) >= 1
    assert sum(r["value"] for r in res["summaryRows"]) == pytest.approx(8.0)


def test_lc_scope_aggregates_by_function(data_api: DataApiFixture, db_session: Session) -> None:
    lcp_pos = _get_or_create_position(db_session, key="lcp", rank=4)
    lcp_person = make_person(db_session, email="test-data-lcp@aiesec.net")
    lcp_mem = make_membership(db_session, person=lcp_person, lc=data_api.lc, position=lcp_pos, term=data_api.term)
    _act_as(_actor(lcp_person, lcp_mem))

    _log(db_session, data_api.team_member_a, data_api.kpi, 6.0, date(2026, 5, 1))

    # Pass kpi key explicitly: the LCP has no function_id so there is no default.
    res = data_api.client.get(
        URL, params={"scope": "lc", "start": START, "end": END, "kpi": "test_data_kpi"}
    ).json()

    assert res["scope"] == "lc"
    assert sum(r["value"] for r in res["summaryRows"]) == pytest.approx(6.0)


def test_all_scope_aggregates_by_lc(data_api: DataApiFixture, db_session: Session) -> None:
    mcvp_pos = _get_or_create_position(db_session, key="mcvp", rank=6)
    mc_lc = make_lc(db_session, name="test-data-mc", lc_type=LCType.MC)
    mcvp_person = make_person(db_session, email="test-data-mcvp@aiesec.net")
    mcvp_mem = make_membership(
        db_session, person=mcvp_person, lc=mc_lc, position=mcvp_pos, term=data_api.term, function=data_api.function
    )
    _act_as(_actor(mcvp_person, mcvp_mem))

    _log(db_session, data_api.team_member_a, data_api.kpi, 7.0, date(2026, 6, 1))

    res = data_api.client.get(URL, params={"scope": "all", "start": START, "end": END}).json()

    assert res["scope"] == "all"
    lc_labels = [r["label"] for r in res["summaryRows"]]
    assert data_api.lc.name in lc_labels
    total = sum(r["value"] for r in res["summaryRows"])
    assert total == pytest.approx(7.0)


def test_requesting_wider_scope_than_grant_is_forbidden(
    data_api: DataApiFixture, db_session: Session
) -> None:
    # TL has analytics_report.view at 'function' scope — 'lc' is wider, must be 403.
    res = data_api.client.get(URL, params={"scope": "lc", "start": START, "end": END})

    assert res.status_code == 403


def test_no_records_returns_empty_rows_and_points(data_api: DataApiFixture) -> None:
    res = data_api.client.get(URL, params={"scope": "team", "start": START, "end": END}).json()

    assert res["summaryRows"] == []
    assert res["points"] == []
    assert res["kpi"]["key"] == "test_data_kpi"


def test_start_after_end_is_bad_request(data_api: DataApiFixture) -> None:
    res = data_api.client.get(URL, params={"scope": "team", "start": "2026-12-31", "end": "2026-01-01"})

    assert res.status_code == 400


def test_unallocated_person_is_forbidden(data_api: DataApiFixture, db_session: Session) -> None:
    nobody = make_person(db_session, email="test-data-nobody@aiesec.net")
    _act_as(CurrentActor(person=nobody, active_memberships=[], acting_membership=None))

    assert data_api.client.get(URL, params={"scope": "team", "start": START, "end": END}).status_code == 403
