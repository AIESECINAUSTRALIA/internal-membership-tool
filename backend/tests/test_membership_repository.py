from datetime import timedelta

from sqlalchemy.orm import Session

from app.repositories.membership import get_active_memberships_for_person
from tests.helpers import (
    TODAY,
    make_function,
    make_lc,
    make_membership,
    make_person,
    make_position,
    make_term,
)


def test_returns_membership_with_no_end_date(db_session: Session) -> None:
    lc = make_lc(db_session)
    position = make_position(db_session)
    term = make_term(db_session)
    person = make_person(db_session)
    current = make_membership(db_session, person=person, lc=lc, position=position, term=term)

    result = get_active_memberships_for_person(db_session, person.id, as_of=TODAY)

    assert [m.id for m in result] == [current.id]


def test_excludes_ended_membership(db_session: Session) -> None:
    lc = make_lc(db_session)
    position = make_position(db_session)
    term = make_term(db_session)
    person = make_person(db_session)
    make_membership(
        db_session,
        person=person,
        lc=lc,
        position=position,
        term=term,
        end=TODAY - timedelta(days=1),
    )

    result = get_active_memberships_for_person(db_session, person.id, as_of=TODAY)

    assert result == []


def test_excludes_not_yet_started_membership(db_session: Session) -> None:
    lc = make_lc(db_session)
    position = make_position(db_session)
    term = make_term(db_session)
    person = make_person(db_session)
    make_membership(
        db_session,
        person=person,
        lc=lc,
        position=position,
        term=term,
        start=TODAY + timedelta(days=1),
    )

    result = get_active_memberships_for_person(db_session, person.id, as_of=TODAY)

    assert result == []


def test_returns_multiple_concurrent_memberships(db_session: Session) -> None:
    lc = make_lc(db_session)
    position = make_position(db_session)
    term = make_term(db_session)
    person = make_person(db_session)
    function = make_function(db_session)
    membership_one = make_membership(db_session, person=person, lc=lc, position=position, term=term)
    membership_two = make_membership(
        db_session, person=person, lc=lc, position=position, term=term, function=function
    )

    result = get_active_memberships_for_person(db_session, person.id, as_of=TODAY)

    assert {m.id for m in result} == {membership_one.id, membership_two.id}


def test_does_not_return_another_persons_membership(db_session: Session) -> None:
    lc = make_lc(db_session)
    position = make_position(db_session)
    term = make_term(db_session)
    person = make_person(db_session)
    other_person = make_person(db_session, email="grace@aiesec.net")
    make_membership(db_session, person=other_person, lc=lc, position=position, term=term)

    result = get_active_memberships_for_person(db_session, person.id, as_of=TODAY)

    assert result == []
