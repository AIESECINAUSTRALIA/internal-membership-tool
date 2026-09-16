from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.attribute import Attribute, AttributeAppliesTo, AttributeDataType
from app.models.kpi import KpiSource
from app.models.membership import Membership, Team, TeamMember
from app.models.org import LC, Function, LCType, Position, Term
from app.models.person import Person
from app.repositories.attribute import AttributeValidationError
from app.repositories.kpi import record_kpi, sum_by_function

TODAY = date(2026, 6, 15)
YEAR_AGO = TODAY - timedelta(days=365)
YEAR_AHEAD = TODAY + timedelta(days=365)


def _make_lc_and_term(session: Session) -> tuple[LC, Term, Position]:
    lc = LC(name="AIESEC in Testville", type=LCType.LC, active=True)
    term = Term(name="Test Term", start_date=YEAR_AGO, end_date=YEAR_AHEAD)
    position = Position(key="member", label="Member", rank=4, active=True)
    session.add_all([lc, term, position])
    session.flush()
    return lc, term, position


def _make_membership(
    session: Session, *, lc: LC, term: Term, position: Position, function: Function, email: str
) -> Membership:
    person = Person(full_name=email, aiesec_email=email, join_date=YEAR_AGO)
    session.add(person)
    session.flush()
    membership = Membership(
        person_id=person.id,
        lc_id=lc.id,
        position_id=position.id,
        function_id=function.id,
        term_id=term.id,
        start_date=YEAR_AGO,
        end_date=None,
    )
    session.add(membership)
    session.flush()
    return membership


def _make_kpi_attribute(
    session: Session, *, key: str = "ol_signups", minimum: float = 0
) -> Attribute:
    attribute = Attribute(
        key=key,
        label="OL Signups",
        applies_to=AttributeAppliesTo.KPI,
        data_type=AttributeDataType.NUMBER,
        unit="count",
        validation={"required": True, "min": minimum},
        active=True,
    )
    session.add(attribute)
    session.flush()
    return attribute


def test_record_kpi_inserts_a_row(db_session: Session) -> None:
    lc, term, position = _make_lc_and_term(db_session)
    function = Function(key="bd", label="BD", active=True)
    db_session.add(function)
    db_session.flush()
    membership = _make_membership(
        db_session, lc=lc, term=term, position=position, function=function, email="a@aiesec.net"
    )
    attribute = _make_kpi_attribute(db_session)

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
    lc, term, position = _make_lc_and_term(db_session)
    function = Function(key="bd", label="BD", active=True)
    db_session.add(function)
    db_session.flush()
    membership = _make_membership(
        db_session, lc=lc, term=term, position=position, function=function, email="a@aiesec.net"
    )
    team = Team(lc_id=lc.id, function_id=function.id, term_id=term.id, name="BD Team 1")
    db_session.add(team)
    db_session.flush()
    db_session.add(
        TeamMember(team_id=team.id, membership_id=membership.id, start_date=YEAR_AGO, end_date=None)
    )
    db_session.flush()
    attribute = _make_kpi_attribute(db_session)

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


def test_record_kpi_rejects_non_kpi_attribute(db_session: Session) -> None:
    lc, term, position = _make_lc_and_term(db_session)
    function = Function(key="bd", label="BD", active=True)
    db_session.add(function)
    db_session.flush()
    membership = _make_membership(
        db_session, lc=lc, term=term, position=position, function=function, email="a@aiesec.net"
    )
    not_a_kpi = Attribute(
        key="shirt_size",
        label="Shirt size",
        applies_to=AttributeAppliesTo.PERSON,
        data_type=AttributeDataType.TEXT,
        active=True,
    )
    db_session.add(not_a_kpi)
    db_session.flush()

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
    lc, term, position = _make_lc_and_term(db_session)
    function = Function(key="bd", label="BD", active=True)
    db_session.add(function)
    db_session.flush()
    membership = _make_membership(
        db_session, lc=lc, term=term, position=position, function=function, email="a@aiesec.net"
    )
    attribute = _make_kpi_attribute(db_session, minimum=0)

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
    lc, term, position = _make_lc_and_term(db_session)
    bd = Function(key="bd", label="BD", active=True)
    mkt = Function(key="mkt", label="MKT", active=True)
    db_session.add_all([bd, mkt])
    db_session.flush()

    bd_member = _make_membership(
        db_session, lc=lc, term=term, position=position, function=bd, email="bd@aiesec.net"
    )
    mkt_member = _make_membership(
        db_session, lc=lc, term=term, position=position, function=mkt, email="mkt@aiesec.net"
    )
    attribute = _make_kpi_attribute(db_session)

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

    assert totals == {"bd": 15, "mkt": 7}
