"""Tests for `get_current_actor`, the stub that ticket 7 (real OAuth) replaces."""

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_actor

from .helpers import make_lc, make_membership, make_person, make_position, make_term

DEV_FLAG = "DEV_ACTOR_HEADER_ENABLED"


def test_header_ignored_when_flag_unset(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    monkeypatch.delenv(DEV_FLAG, raising=False)
    person = make_person(db_session, email="test_real@aiesec.net")

    with pytest.raises(HTTPException) as exc:
        get_current_actor(db=db_session, x_actor_email=person.aiesec_email)

    assert exc.value.status_code == 401


def test_header_accepted_when_flag_true(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    monkeypatch.setenv(DEV_FLAG, "true")
    person = make_person(db_session, email="test_real@aiesec.net")

    actor = get_current_actor(db=db_session, x_actor_email="  TEST_Real@aiesec.net ")

    assert actor.person.id == person.id


def test_acting_membership_is_highest_rank(
    monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    monkeypatch.setenv(DEV_FLAG, "true")
    lc = make_lc(db_session)
    term = make_term(db_session)
    person = make_person(db_session, email="test_two_hats@aiesec.net")
    low = make_position(db_session, key="test_low", label="Low", rank=1)
    high = make_position(db_session, key="test_high", label="High", rank=3)
    # The lower-ranked membership is created first, so insertion order is not rank order.
    make_membership(db_session, person=person, lc=lc, position=low, term=term)
    m_high = make_membership(db_session, person=person, lc=lc, position=high, term=term)

    actor = get_current_actor(db=db_session, x_actor_email=person.aiesec_email)

    assert actor.acting_membership is not None
    assert actor.acting_membership.id == m_high.id
