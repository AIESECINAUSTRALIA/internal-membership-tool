"""Tests for authenticated actor resolution and membership selection."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_actor
from app.main import app

from .helpers import make_lc, make_membership, make_person, make_position, make_term


@pytest.mark.parametrize("dev_flag", ["true", "false"])
def test_actor_email_header_cannot_authenticate(
    monkeypatch: pytest.MonkeyPatch,
    dev_flag: str,
) -> None:
    """The old development header must never authenticate a request."""
    monkeypatch.setenv("DEV_ACTOR_HEADER_ENABLED", dev_flag)

    client = TestClient(app)
    response = client.post(
        "/api/v1/members/summary",
        headers={"X-Actor-Email": "someone@aiesec.net"},
        json={},
    )

    assert response.status_code == 401


def test_acting_membership_is_highest_rank(db_session: Session) -> None:
    lc = make_lc(db_session)
    term = make_term(db_session)
    person = make_person(db_session, email="test_two_hats@aiesec.net")
    low = make_position(db_session, key="test_low", label="Low", rank=1)
    high = make_position(db_session, key="test_high", label="High", rank=3)

    # Create the lower-ranked membership first.
    make_membership(db_session, person=person, lc=lc, position=low, term=term)
    m_high = make_membership(db_session, person=person, lc=lc, position=high, term=term)

    actor = get_current_actor(person=person, db=db_session)

    assert actor.acting_membership is not None
    assert actor.acting_membership.id == m_high.id
    assert len(actor.active_memberships) == 2
