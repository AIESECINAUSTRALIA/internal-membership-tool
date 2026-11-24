"""Server-side sessions for EXPA sign-in. Read `docs/auth.md` first.

One `user_session` row goes through two stages:

1. **Pending** (`person_id` is NULL): created by `GET /auth/login` before the browser
   is sent to EXPA. It holds a hash of the OAuth `state` and of a cookie token, so the
   callback can prove it is the same browser that started the sign-in (CSRF on login).
2. **Active** (`person_id` set): after a successful callback the row is linked to the
   person and given a fresh token. That token is the `__session` cookie.

Only SHA-256 hashes of tokens are stored. Someone who reads the database (or a
backup) can't use what they find there to sign in.

Cleanup: rows that have expired or been revoked are deleted by
`purge_stale_sessions`, which runs each time someone starts a sign-in. That keeps the
table small without a scheduled job, even if someone calls `/auth/login` in a loop:
pending rows expire after an hour.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models.user_session import UserSession


def utc_now() -> datetime:
    return datetime.now(UTC)


def generate_token() -> str:
    """Generate a cryptographically random, URL-safe token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Store only SHA-256 digests, never raw session tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_pending_session(
    db: Session,
    *,
    ttl_hours: int,
) -> tuple[UserSession, str, str]:
    """Create a pending OAuth session and return its cookie token and state.

    Stale rows are purged first, in the same transaction.
    """
    purge_stale_sessions(db)

    token = generate_token()
    state = generate_token()

    session = UserSession(
        token_hash=hash_token(token),
        oauth_state_hash=hash_token(state),
        person_id=None,
        expires_at=utc_now() + timedelta(hours=ttl_hours),
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return session, token, state


def get_valid_session(db: Session, token: str) -> UserSession | None:
    """Return an authenticated, unexpired, unrevoked session."""
    session = db.execute(
        select(UserSession).where(
            UserSession.token_hash == hash_token(token),
            UserSession.person_id.is_not(None),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > utc_now(),
        )
    ).scalar_one_or_none()

    return session


def consume_pending_session(
    db: Session,
    *,
    token: str,
    state: str,
) -> UserSession | None:
    """Validate a pending OAuth attempt against both cookie and state."""
    if not token or not state:
        return None

    session = db.execute(
        select(UserSession)
        .where(
            UserSession.token_hash == hash_token(token),
            UserSession.oauth_state_hash == hash_token(state),
            UserSession.person_id.is_(None),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > utc_now(),
        )
        .with_for_update()
    ).scalar_one_or_none()

    if session is None:
        return None

    # Consume the state before any external EXPA requests.
    session.oauth_state_hash = None
    db.commit()

    return session


def activate_session(
    db: Session,
    *,
    session: UserSession,
    person_id: int,
    ttl_hours: int,
) -> str:
    """Rotate the pending token into a new authenticated session token."""
    token = generate_token()

    session.token_hash = hash_token(token)
    session.oauth_state_hash = None
    session.person_id = person_id
    session.created_at = utc_now()
    session.expires_at = utc_now() + timedelta(hours=ttl_hours)
    session.revoked_at = None

    return token


def revoke_session(db: Session, session: UserSession) -> None:
    """Invalidate a session immediately."""
    session.revoked_at = utc_now()
    db.commit()


def purge_stale_sessions(db: Session) -> int:
    """Delete expired and revoked sessions. Returns how many rows were deleted.

    A consumed-but-unfinished pending row (its callback is running right now) is not
    expired yet, so a concurrent sign-in never deletes it from under the callback.
    The caller commits.
    """
    result = db.execute(
        delete(UserSession).where(
            or_(
                UserSession.expires_at <= utc_now(),
                UserSession.revoked_at.is_not(None),
            )
        )
    )
    return int(getattr(result, "rowcount", 0) or 0)


def delete_pending_session(db: Session, token: str) -> None:
    """Delete the pending sign-in started with this cookie token, if any.

    Called when a callback fails, so failed attempts don't leave rows behind. Only
    pending rows (no person) match, so this can never end a real session. The
    caller commits.
    """
    db.execute(
        delete(UserSession).where(
            UserSession.token_hash == hash_token(token),
            UserSession.person_id.is_(None),
        )
    )
