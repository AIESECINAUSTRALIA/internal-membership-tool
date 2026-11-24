"""Security tests for pending EXPA OAuth sessions."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.sessions import (
    consume_pending_session,
    create_pending_session,
    delete_pending_session,
    generate_token,
    get_valid_session,
    hash_token,
    utc_now,
)
from app.models.user_session import UserSession
from tests.helpers import make_person


def test_correct_state_and_cookie_are_accepted(db_session: Session) -> None:
    _, token, state = create_pending_session(db_session, ttl_hours=1)

    pending = consume_pending_session(
        db_session,
        token=token,
        state=state,
    )

    assert pending is not None
    assert pending.person_id is None


def test_wrong_state_is_rejected(db_session: Session) -> None:
    _, token, _ = create_pending_session(db_session, ttl_hours=1)

    pending = consume_pending_session(
        db_session,
        token=token,
        state="wrong-state",
    )

    assert pending is None


def test_wrong_browser_cookie_is_rejected(db_session: Session) -> None:
    _, _, state = create_pending_session(db_session, ttl_hours=1)

    pending = consume_pending_session(
        db_session,
        token="someone-elses-cookie",
        state=state,
    )

    assert pending is None


def test_missing_state_is_rejected(db_session: Session) -> None:
    _, token, _ = create_pending_session(db_session, ttl_hours=1)

    assert (
        consume_pending_session(
            db_session,
            token=token,
            state="",
        )
        is None
    )


def test_state_cannot_be_replayed(db_session: Session) -> None:
    _, token, state = create_pending_session(db_session, ttl_hours=1)

    first = consume_pending_session(db_session, token=token, state=state)
    second = consume_pending_session(db_session, token=token, state=state)

    assert first is not None
    assert second is None


def test_pending_session_cannot_access_authenticated_routes(
    db_session: Session,
) -> None:
    _, token, _ = create_pending_session(db_session, ttl_hours=1)

    assert get_valid_session(db_session, token) is None


def test_starting_a_sign_in_purges_stale_sessions(db_session: Session) -> None:
    """Expired and revoked rows are deleted whenever a new sign-in starts, so the
    table can't grow without bound."""
    expired = UserSession(
        token_hash=hash_token(generate_token()),
        expires_at=utc_now() - timedelta(minutes=1),
    )
    revoked = UserSession(
        token_hash=hash_token(generate_token()),
        expires_at=utc_now() + timedelta(hours=1),
        revoked_at=utc_now(),
    )
    live = UserSession(
        token_hash=hash_token(generate_token()),
        expires_at=utc_now() + timedelta(hours=1),
    )
    db_session.add_all([expired, revoked, live])
    db_session.flush()
    ids = {"expired": expired.id, "revoked": revoked.id, "live": live.id}

    create_pending_session(db_session, ttl_hours=1)
    db_session.expire_all()

    assert db_session.get(UserSession, ids["expired"]) is None
    assert db_session.get(UserSession, ids["revoked"]) is None
    assert db_session.get(UserSession, ids["live"]) is not None


def test_delete_pending_session_never_touches_active_sessions(db_session: Session) -> None:
    person = make_person(db_session)
    token = generate_token()
    active = UserSession(
        token_hash=hash_token(token),
        person_id=person.id,
        expires_at=utc_now() + timedelta(hours=1),
    )
    db_session.add(active)
    db_session.flush()

    delete_pending_session(db_session, token)
    db_session.expire_all()

    assert db_session.get(UserSession, active.id) is not None
