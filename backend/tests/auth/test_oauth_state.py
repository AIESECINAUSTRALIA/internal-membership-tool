"""Security tests for pending EXPA OAuth sessions."""

from sqlalchemy.orm import Session

from app.core.sessions import (
    consume_pending_session,
    create_pending_session,
    get_valid_session,
)


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
