from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models.kpi import KpiSource
from app.models.membership import Team, TeamMember
from app.repositories.attribute import AttributeValidationError
from app.repositories.kpi import record_kpi, sum_by_function
from tests.helpers import (
    YEAR_AGO,
    make_attribute,
    make_function,
    make_kpi_attribute,
    make_lc,
    make_membership,
    make_person,
    make_position,
    make_term,
)


def test_record_kpi_inserts_a_row(db_session: Session) -> None:
    lc = make_lc(db_session)
    term = make_term(db_session)
    position = make_position(db_session)
    function = make_function(db_session)
    person = make_person(db_session)
    membership = make_membership(
        db_session, person=person, lc=lc, position=position, term=term, function=function
    )
    attribute = make_kpi_attribute(db_session)

    record = record_kpi(
        db_session,
        attribute=attribute,
        membership_id=membership.id,
        value_number=5,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        source=KpiSource.SELF,
        recorded_by_membership_id=membership.id,
    )

    assert record.id is not None
    assert record.value_number == 5
    assert record.team_id is None


def test_record_kpi_resolves_team_id_as_of_period_start(db_session: Session) -> None:
    lc = make_lc(db_session)
    term = make_term(db_session)
    position = make_position(db_session)
    function = make_function(db_session)
    person = make_person(db_session)
    membership = make_membership(
        db_session, person=person, lc=lc, position=position, term=term, function=function
    )
    team = Team(lc_id=lc.id, function_id=function.id, term_id=term.id, name="BD Team 1")
    db_session.add(team)
    db_session.flush()
    db_session.add(
        TeamMember(team_id=team.id, membership_id=membership.id, start_date=YEAR_AGO, end_date=None)
    )
    db_session.flush()
    attribute = make_kpi_attribute(db_session)

    record = record_kpi(
        db_session,
        attribute=attribute,
        membership_id=membership.id,
        value_number=3,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        source=KpiSource.LEADER,
        recorded_by_membership_id=membership.id,
    )

    assert record.team_id == team.id


def test_record_kpi_on_team_handoff_day_picks_the_new_team(db_session: Session) -> None:
    lc = make_lc(db_session)
    term = make_term(db_session)
    position = make_position(db_session)
    function = make_function(db_session)
    person = make_person(db_session)
    membership = make_membership(
        db_session, person=person, lc=lc, position=position, term=term, function=function
    )
    team_a = Team(lc_id=lc.id, function_id=function.id, term_id=term.id, name="BD Team A")
    team_b = Team(lc_id=lc.id, function_id=function.id, term_id=term.id, name="BD Team B")
    db_session.add_all([team_a, team_b])
    db_session.flush()
    # Team A is inserted first, so without an ORDER BY Postgres would most
    # likely return it first — the test would fail on the old `.first()`.
    db_session.add(
        TeamMember(
            team_id=team_a.id,
            membership_id=membership.id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 1),
        )
    )
    db_session.add(
        TeamMember(
            team_id=team_b.id,
            membership_id=membership.id,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 5, 1),
        )
    )
    db_session.flush()
    attribute = make_kpi_attribute(db_session)

    # Mar 1 is both Team A's last day and Team B's first (end_date is inclusive).
    record = record_kpi(
        db_session,
        attribute=attribute,
        membership_id=membership.id,
        value_number=3,
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        source=KpiSource.LEADER,
        recorded_by_membership_id=membership.id,
    )

    assert record.team_id == team_b.id


def test_record_kpi_rejects_non_kpi_attribute(db_session: Session) -> None:
    lc = make_lc(db_session)
    term = make_term(db_session)
    position = make_position(db_session)
    function = make_function(db_session)
    person = make_person(db_session)
    membership = make_membership(
        db_session, person=person, lc=lc, position=position, term=term, function=function
    )
    not_a_kpi = make_attribute(
        db_session,
        key="test_shirt_size",
        label="Shirt size",
    )

    with pytest.raises(AttributeValidationError):
        record_kpi(
            db_session,
            attribute=not_a_kpi,
            membership_id=membership.id,
            value_number=1,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            source=KpiSource.SELF,
            recorded_by_membership_id=membership.id,
        )


def test_record_kpi_rejects_value_below_minimum(db_session: Session) -> None:
    lc = make_lc(db_session)
    term = make_term(db_session)
    position = make_position(db_session)
    function = make_function(db_session)
    person = make_person(db_session)
    membership = make_membership(
        db_session, person=person, lc=lc, position=position, term=term, function=function
    )
    attribute = make_kpi_attribute(db_session, minimum=0)

    with pytest.raises(AttributeValidationError):
        record_kpi(
            db_session,
            attribute=attribute,
            membership_id=membership.id,
            value_number=-1,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            source=KpiSource.SELF,
            recorded_by_membership_id=membership.id,
        )


def test_sum_by_function_returns_correct_totals_within_range(db_session: Session) -> None:
    lc = make_lc(db_session)
    term = make_term(db_session)
    position = make_position(db_session)
    bd = make_function(db_session, key="test_bd", label="Test BD")
    mkt = make_function(db_session, key="test_mkt", label="Test MKT")
    bd_person = make_person(db_session, email="test_bd@aiesec.net")
    mkt_person = make_person(db_session, email="test_mkt@aiesec.net")
    bd_member = make_membership(
        db_session, person=bd_person, lc=lc, position=position, term=term, function=bd
    )
    mkt_member = make_membership(
        db_session, person=mkt_person, lc=lc, position=position, term=term, function=mkt
    )
    attribute = make_kpi_attribute(db_session)

    # In range for both functions.
    record_kpi(
        db_session,
        attribute=attribute,
        membership_id=bd_member.id,
        value_number=10,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        source=KpiSource.SELF,
        recorded_by_membership_id=bd_member.id,
    )
    record_kpi(
        db_session,
        attribute=attribute,
        membership_id=bd_member.id,
        value_number=5,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        source=KpiSource.SELF,
        recorded_by_membership_id=bd_member.id,
    )
    record_kpi(
        db_session,
        attribute=attribute,
        membership_id=mkt_member.id,
        value_number=7,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        source=KpiSource.SELF,
        recorded_by_membership_id=mkt_member.id,
    )
    # Outside the queried range — must not be counted.
    record_kpi(
        db_session,
        attribute=attribute,
        membership_id=bd_member.id,
        value_number=100,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 1, 31),
        source=KpiSource.SELF,
        recorded_by_membership_id=bd_member.id,
    )

    totals = {
        function_key: total
        for function_key, _label, total in sum_by_function(
            db_session,
            lc_id=lc.id,
            attribute_id=attribute.id,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
        )
    }

    assert totals == {"test_bd": 15, "test_mkt": 7}


def test_sum_by_function_includes_memberships_without_a_function(db_session: Session) -> None:
    lc = make_lc(db_session)
    term = make_term(db_session)
    position = make_position(db_session)
    bd = make_function(db_session, key="test_bd", label="Test BD")
    bd_person = make_person(db_session, email="test_bd@aiesec.net")
    lcp_person = make_person(db_session, email="test_lcp@aiesec.net")
    bd_member = make_membership(
        db_session, person=bd_person, lc=lc, position=position, term=term, function=bd
    )
    # e.g. an LCP — not tied to any one function.
    lcp_member = make_membership(db_session, person=lcp_person, lc=lc, position=position, term=term)
    attribute = make_kpi_attribute(db_session)

    record_kpi(
        db_session,
        attribute=attribute,
        membership_id=bd_member.id,
        value_number=10,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        source=KpiSource.SELF,
        recorded_by_membership_id=bd_member.id,
    )
    record_kpi(
        db_session,
        attribute=attribute,
        membership_id=lcp_member.id,
        value_number=5,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        source=KpiSource.SELF,
        recorded_by_membership_id=lcp_member.id,
    )

    rows = sum_by_function(
        db_session,
        lc_id=lc.id,
        attribute_id=attribute.id,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
    )

    assert {tuple(row) for row in rows} == {
        ("test_bd", "Test BD", 10),
        (None, None, 5),
    }
