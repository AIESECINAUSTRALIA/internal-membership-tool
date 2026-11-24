from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.org import Position
from app.repositories.membership import (
    _position_can_add_same_rank,
    _position_level,
    build_membership_context,
    effective_position_rank,
    get_active_memberships_for_person,
)
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
    other_person = make_person(db_session, email="test_grace@aiesec.net")
    make_membership(db_session, person=other_person, lc=lc, position=position, term=term)

    result = get_active_memberships_for_person(db_session, person.id, as_of=TODAY)

    assert result == []


# ---------------------------------------------------------------------------
# Position columns win over the key-based fallbacks (DEV-0049, spec §2, §3.4, §3.6).
# An admin can change these on the Positions & functions screen, so the
# permission code must read the table, not a hardcoded list of keys.
# ---------------------------------------------------------------------------


def _position_with_key(session: Session, key: str) -> Position:
    """The position with this key: the seeded one if it exists, else a new one."""
    position = session.execute(select(Position).where(Position.key == key)).scalar_one_or_none()
    if position is None:
        position = make_position(session, key=key, label=f"Test {key}", rank=4)
    return position


def test_president_flag_can_be_switched_off(db_session: Session) -> None:
    lcp = _position_with_key(db_session, "lcp")
    lcp.can_add_same_rank = False
    db_session.flush()
    membership = make_membership(
        db_session,
        person=make_person(db_session),
        lc=make_lc(db_session),
        position=lcp,
        term=make_term(db_session),
    )

    context = build_membership_context(db_session, membership)

    assert context.can_add_same_rank is False


def test_president_flag_falls_back_to_key_when_unset() -> None:
    assert _position_can_add_same_rank(Position(key="mcp", can_add_same_rank=None)) is True
    assert _position_can_add_same_rank(Position(key="lcvp", can_add_same_rank=None)) is False


def test_stored_level_wins_over_key() -> None:
    assert _position_level(Position(key="test_custom_mc_role", level="mc")) == "mc"


def test_level_falls_back_to_key_when_unset() -> None:
    assert _position_level(Position(key="mcp", level=None)) == "mc"
    assert _position_level(Position(key="lcvp", level=None)) == "lc"


def test_rank_zero_is_used_not_treated_as_missing() -> None:
    assert effective_position_rank(Position(key="mcp", rank=0)) == 0


def test_rank_falls_back_to_key_when_unset() -> None:
    assert effective_position_rank(Position(key="mcp", rank=None)) == 7
