"""Authentication tests for EXPA-backed server-side sessions."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.auth import is_allowed_email
from app.core.sessions import (
    create_pending_session,
    get_valid_session,
    hash_token,
    revoke_session,
    utc_now,
)
from app.models.user_session import UserSession
from tests.helpers import make_person


@pytest.mark.parametrize(
    ("email", "allowed"),
    [
        ("a@aiesec.net", True),
        ("a@AIESEC.NET", True),
        ("a@aiesec.org.au", True),
        ("a@notaiesec.net", False),
        ("a@aiesec.net.evil.com", False),
        ("a@sub.aiesec.net", False),
        ("aiesec.net", False),
        ("", False),
    ],
)
def test_allowed_email_domains(email: str, allowed: bool) -> None:
    domains = frozenset({"aiesec.net", "aiesec.org.au"})
    assert is_allowed_email(email, domains) is allowed


def test_allowed_email_domains_setting() -> None:
    settings = Settings(allowed_email_domains=" aiesec.net, AIESEC.org.au ,,")
    assert settings.allowed_email_domain_set == frozenset({"aiesec.net", "aiesec.org.au"})


def test_missing_cookie_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401


def test_old_actor_header_cannot_authenticate(client: TestClient) -> None:
    response = client.get(
        "/api/v1/me",
        headers={"X-Actor-Email": "test_ada@aiesec.net"},
    )
    assert response.status_code == 401


def test_invalid_session_cookie_returns_401(client: TestClient) -> None:
    response = client.get(
        "/api/v1/me",
        cookies={"__session": "not-a-valid-session"},
    )
    assert response.status_code == 401


def test_pending_session_is_not_authenticated(
    client: TestClient,
    db_session: Session,
) -> None:
    _, token, _ = create_pending_session(db_session, ttl_hours=1)

    response = client.get(
        "/api/v1/me",
        cookies={"__session": token},
    )
    assert response.status_code == 401


def test_expired_session_is_rejected(db_session: Session) -> None:
    person = make_person(db_session)
    token = "expired-test-session"

    session = UserSession(
        token_hash=hash_token(token),
        person_id=person.id,
        expires_at=utc_now() - timedelta(seconds=1),
    )
    db_session.add(session)
    db_session.flush()

    assert get_valid_session(db_session, token) is None


def test_revoked_session_is_rejected(db_session: Session) -> None:
    person = make_person(db_session)
    token = "revoked-test-session"

    session = UserSession(
        token_hash=hash_token(token),
        person_id=person.id,
        expires_at=utc_now() + timedelta(hours=12),
    )
    db_session.add(session)
    db_session.flush()

    assert get_valid_session(db_session, token) is not None

    revoke_session(db_session, session)

    assert get_valid_session(db_session, token) is None
