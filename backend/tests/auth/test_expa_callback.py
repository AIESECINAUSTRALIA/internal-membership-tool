"""Integration tests for the EXPA OAuth callback."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1 import auth
from app.core.auth import ExpaIdentity
from app.models.org import LC
from app.models.person import Person
from app.models.privacy import AuditLog
from app.models.user_session import UserSession
from tests.helpers import (
    make_lc,
    make_membership,
    make_person,
    make_position,
    make_term,
)


@pytest.fixture
def fake_expa(monkeypatch: pytest.MonkeyPatch):
    """Replace external EXPA calls, not the application's OAuth routes."""

    identity = ExpaIdentity(
        expa_id="123456",
        aiesec_email="test_ada@aiesec.net",
    )

    monkeypatch.setattr(
        auth.ExpaOAuthClient,
        "exchange_code",
        AsyncMock(return_value="fake-expa-token"),
    )
    monkeypatch.setattr(
        auth.ExpaOAuthClient,
        "get_current_person",
        AsyncMock(return_value=identity),
    )

    return identity


def _start_login(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("EXPA_CLIENT_ID", "test-client")
    monkeypatch.setenv("EXPA_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("APP_BASE_URL", "https://members.example.org")

    from app.config import get_settings

    get_settings.cache_clear()

    response = client.get("/api/v1/auth/login", follow_redirects=False)
    assert response.status_code == 302

    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def _allocated_person(db: Session) -> Person:
    person = make_person(db)
    lc: LC = make_lc(db)
    make_membership(
        db,
        person=person,
        lc=lc,
        position=make_position(db),
        term=make_term(db),
    )
    return person


def test_successful_callback_creates_session_and_audit(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    person = _allocated_person(db_session)
    before = (
        db_session.execute(select(AuditLog).where(AuditLog.action == "auth.sign_in"))
        .scalars()
        .all()
    )

    state = _start_login(client, monkeypatch)

    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "__session" in response.headers["set-cookie"]

    db_session.refresh(person)
    assert person.expa_id == fake_expa.expa_id

    sessions = (
        db_session.execute(select(UserSession).where(UserSession.person_id == person.id))
        .scalars()
        .all()
    )
    assert len(sessions) == 1

    after = (
        db_session.execute(select(AuditLog).where(AuditLog.action == "auth.sign_in"))
        .scalars()
        .all()
    )
    assert len(after) == len(before) + 1
    assert after[-1].actor_person_id == person.id
    assert "@" not in str(after[-1].diff)


def test_wrong_state_is_rejected(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    _start_login(client, monkeypatch)

    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code", "state": "incorrect"},
        follow_redirects=False,
    )

    assert response.status_code == 401


def test_missing_state_is_rejected(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    _start_login(client, monkeypatch)

    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code"},
        follow_redirects=False,
    )

    assert response.status_code == 401


def test_disallowed_email_domain_is_rejected(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    monkeypatch.setattr(
        auth.ExpaOAuthClient,
        "get_current_person",
        AsyncMock(
            return_value=ExpaIdentity(
                expa_id="987654",
                aiesec_email="someone@gmail.com",
            )
        ),
    )

    state = _start_login(client, monkeypatch)
    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 403


def test_expa_token_exchange_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    from app.core.auth import AuthError

    monkeypatch.setattr(
        auth.ExpaOAuthClient,
        "exchange_code",
        AsyncMock(side_effect=AuthError(502, "EXPA token exchange failed")),
    )

    state = _start_login(client, monkeypatch)
    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 502


def test_unallocated_person_is_rejected(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    person = make_person(db_session)

    state = _start_login(client, monkeypatch)
    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Account is not allocated"

    db_session.refresh(person)
    assert person.expa_id is None


def test_existing_expa_id_takes_precedence_over_email(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    original = _allocated_person(db_session)
    original.expa_id = fake_expa.expa_id
    original.aiesec_email = "original@aiesec.net"

    other = make_person(db_session, email=fake_expa.aiesec_email)
    db_session.flush()

    state = _start_login(client, monkeypatch)
    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302

    sessions = (
        db_session.execute(select(UserSession).where(UserSession.person_id == original.id))
        .scalars()
        .all()
    )

    assert len(sessions) == 1
    assert other.expa_id is None
