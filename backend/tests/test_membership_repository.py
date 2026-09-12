from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.membership import Membership
from app.models.org import LC, Function, LCType, Position, Term
from app.models.person import Person
from app.repositories.membership import get_active_memberships_for_person

TODAY = date(2026, 6, 15)
YEAR_AGO = TODAY - timedelta(days=365)
YEAR_AHEAD = TODAY + timedelta(days=365)


def _make_person_and_lookups(session: Session) -> tuple[Person, LC, Position, Term]:
    lc = LC(name="AIESEC in Testville", type=LCType.LC, active=True)
    position = Position(key="member", label="Member", rank=4, active=True)
    term = Term(name="Test Term", start_date=YEAR_AGO, end_date=YEAR_AHEAD)
    person = Person(
        full_name="Ada Lovelace",
        aiesec_email="ada@aiesec.net",
        join_date=YEAR_AGO,
    )
    session.add_all([lc, position, term, person])
    session.flush()
    return person, lc, position, term


def test_returns_membership_with_no_end_date(db_session: Session) -> None:
    person, lc, position, term = _make_person_and_lookups(db_session)
    current = Membership(
        person_id=person.id,
        lc_id=lc.id,
        position_id=position.id,
        term_id=term.id,
        start_date=YEAR_AGO,
        end_date=None,
    )
    db_session.add(current)
    db_session.flush()

    result = get_active_memberships_for_person(db_session, person.id, as_of=TODAY)

    assert [m.id for m in result] == [current.id]


def test_excludes_ended_membership(db_session: Session) -> None:
    person, lc, position, term = _make_person_and_lookups(db_session)
    ended = Membership(
        person_id=person.id,
        lc_id=lc.id,
        position_id=position.id,
        term_id=term.id,
        start_date=YEAR_AGO,
        end_date=TODAY - timedelta(days=1),
    )
    db_session.add(ended)
    db_session.flush()

    result = get_active_memberships_for_person(db_session, person.id, as_of=TODAY)

    assert result == []


def test_excludes_not_yet_started_membership(db_session: Session) -> None:
    person, lc, position, term = _make_person_and_lookups(db_session)
    future = Membership(
        person_id=person.id,
        lc_id=lc.id,
        position_id=position.id,
        term_id=term.id,
        start_date=TODAY + timedelta(days=1),
        end_date=None,
    )
    db_session.add(future)
    db_session.flush()

    result = get_active_memberships_for_person(db_session, person.id, as_of=TODAY)

    assert result == []


def test_returns_multiple_concurrent_memberships(db_session: Session) -> None:
    person, lc, position, term = _make_person_and_lookups(db_session)
    function = Function(key="bd", label="BD", active=True)
    db_session.add(function)
    db_session.flush()

    membership_one = Membership(
        person_id=person.id,
        lc_id=lc.id,
        position_id=position.id,
        term_id=term.id,
        start_date=YEAR_AGO,
        end_date=None,
    )
    membership_two = Membership(
        person_id=person.id,
        lc_id=lc.id,
        position_id=position.id,
        function_id=function.id,
        term_id=term.id,
        start_date=YEAR_AGO,
        end_date=None,
    )
    db_session.add_all([membership_one, membership_two])
    db_session.flush()

    result = get_active_memberships_for_person(db_session, person.id, as_of=TODAY)

    assert {m.id for m in result} == {membership_one.id, membership_two.id}


def test_does_not_return_another_persons_membership(db_session: Session) -> None:
    person, lc, position, term = _make_person_and_lookups(db_session)
    other_person = Person(
        full_name="Grace Hopper",
        aiesec_email="grace@aiesec.net",
        join_date=YEAR_AGO,
    )
    db_session.add(other_person)
    db_session.flush()

    other_membership = Membership(
        person_id=other_person.id,
        lc_id=lc.id,
        position_id=position.id,
        term_id=term.id,
        start_date=YEAR_AGO,
        end_date=None,
    )
    db_session.add(other_membership)
    db_session.flush()

    result = get_active_memberships_for_person(db_session, person.id, as_of=TODAY)

    assert result == []
