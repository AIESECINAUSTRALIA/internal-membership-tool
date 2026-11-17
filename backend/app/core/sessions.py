"""Creation, validation and revocation of server-side sessions."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
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
    """Create a pending OAuth session and return its cookie token and state."""
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
