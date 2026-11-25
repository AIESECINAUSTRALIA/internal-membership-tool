"""Integration tests for the EXPA OAuth callback."""

from datetime import date, timedelta
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1 import auth
from app.core.auth import ExpaIdentity
from app.core.sessions import hash_token
from app.models.org import LC, LCType, Position
from app.models.person import Person, PersonStatus
from app.models.privacy import AuditLog
from app.models.user_session import UserSession
from tests.helpers import (
    YEAR_AGO,
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
        Mock(return_value="fake-expa-token"),
    )
    monkeypatch.setattr(
        auth.ExpaOAuthClient,
        "get_current_person",
        Mock(return_value=identity),
    )

    return identity


def _start_login(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("EXPA_CLIENT_ID", "test-client")
    monkeypatch.setenv("EXPA_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("APP_BASE_URL", "https://members.example.org")
    monkeypatch.setenv("FRONTEND_ORIGIN", FRONTEND)

    from app.config import get_settings

    get_settings.cache_clear()

    response = client.get("/api/v1/auth/login", follow_redirects=False)
    assert response.status_code == 302

    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


FRONTEND = "https://members.example.org"


def _assert_sign_in_error(response: Response, reason: str) -> None:
    """A failed callback lands on the frontend sign-in page with `?error=<reason>`,
    and clears the pending-sign-in cookie."""
    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}" == FRONTEND
    assert location.path == "/sign-in"
    assert parse_qs(location.query) == {"error": [reason]}
    assert '__oauth_pending=""' in response.headers.get("set-cookie", "")


def _pending_rows(db: Session) -> list[UserSession]:
    return list(
        db.execute(select(UserSession).where(UserSession.person_id.is_(None))).scalars().all()
    )


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
    assert response.headers["location"] == f"{FRONTEND}/"
    assert "__session" in response.headers["set-cookie"]
    # Deployed over https, so the cookie is Secure.
    assert "secure" in response.headers["set-cookie"].lower()

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
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    _start_login(client, monkeypatch)
    pending_token = client.cookies.get("__oauth_pending")
    assert pending_token

    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code", "state": "incorrect"},
        follow_redirects=False,
    )

    _assert_sign_in_error(response, "expired")
    # The failed attempt's pending row is deleted, not left behind.
    assert all(row.token_hash != hash_token(pending_token) for row in _pending_rows(db_session))


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

    _assert_sign_in_error(response, "expired")


def test_disallowed_email_domain_is_rejected(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    monkeypatch.setattr(
        auth.ExpaOAuthClient,
        "get_current_person",
        Mock(
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

    _assert_sign_in_error(response, "domain")


def test_expa_token_exchange_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    from app.core.auth import AuthError

    monkeypatch.setattr(
        auth.ExpaOAuthClient,
        "exchange_code",
        Mock(side_effect=AuthError(502, "EXPA token exchange failed")),
    )

    state = _start_login(client, monkeypatch)
    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )

    _assert_sign_in_error(response, "expa")


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

    _assert_sign_in_error(response, "not_allocated")

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


def test_denied_on_expa_redirects_to_sign_in(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    state = _start_login(client, monkeypatch)

    response = client.get(
        "/api/v1/auth/callback",
        params={"error": "access_denied", "state": state},
        follow_redirects=False,
    )

    _assert_sign_in_error(response, "denied")


def test_ended_membership_is_not_allocated(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    """A person whose term has ended gets the not-allocated message, no session."""
    person = make_person(db_session, email=fake_expa.aiesec_email)
    make_membership(
        db_session,
        person=person,
        lc=make_lc(db_session),
        position=make_position(db_session),
        term=make_term(db_session),
        start=YEAR_AGO,
        end=date.today() - timedelta(days=1),
    )

    state = _start_login(client, monkeypatch)
    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )

    _assert_sign_in_error(response, "not_allocated")
    sessions = db_session.execute(
        select(UserSession).where(UserSession.person_id == person.id)
    ).scalars()
    assert list(sessions) == []


def test_email_fallback_tolerates_case_duplicates(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    """Two unlinked rows whose emails differ only in case: the oldest is used,
    rather than the callback crashing with MultipleResultsFound."""
    first = _allocated_person(db_session)
    first.aiesec_email = fake_expa.aiesec_email.upper()
    make_person(db_session, email=fake_expa.aiesec_email)
    db_session.flush()

    state = _start_login(client, monkeypatch)
    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == f"{FRONTEND}/"
    db_session.refresh(first)
    assert first.expa_id == fake_expa.expa_id


def _sign_in_audits(db: Session) -> list[AuditLog]:
    return list(
        db.execute(select(AuditLog).where(AuditLog.action == "auth.sign_in").order_by(AuditLog.id))
        .scalars()
        .all()
    )


def test_unallocated_sign_in_is_audited_with_person_id(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    person = make_person(db_session, email=fake_expa.aiesec_email)
    person_id = person.id
    before = len(_sign_in_audits(db_session))

    state = _start_login(client, monkeypatch)
    client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )

    audits = _sign_in_audits(db_session)
    assert len(audits) == before + 1
    entry = audits[-1]
    assert entry.diff == {"allocated": False, "reason": "not_allocated"}
    assert entry.actor_person_id == person_id
    assert "@" not in entry.summary and "@" not in str(entry.diff)


def test_unknown_person_sign_in_is_audited_without_person(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    before = len(_sign_in_audits(db_session))

    state = _start_login(client, monkeypatch)
    client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )

    audits = _sign_in_audits(db_session)
    assert len(audits) == before + 1
    assert audits[-1].actor_person_id is None
    assert audits[-1].resource_id is None
    assert audits[-1].diff == {"allocated": False, "reason": "not_allocated"}


def test_disallowed_domain_is_audited(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    monkeypatch.setattr(
        auth.ExpaOAuthClient,
        "get_current_person",
        Mock(return_value=ExpaIdentity(expa_id="987654", aiesec_email="someone@gmail.com")),
    )
    before = len(_sign_in_audits(db_session))

    state = _start_login(client, monkeypatch)
    client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )

    audits = _sign_in_audits(db_session)
    assert len(audits) == before + 1
    assert audits[-1].diff == {"allocated": False, "reason": "domain"}
    assert "gmail" not in audits[-1].summary


def test_unauthenticated_failures_are_not_audited(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    """Failures anyone can trigger without an EXPA account must not write to the
    permanent audit log."""
    before = len(_sign_in_audits(db_session))
    _start_login(client, monkeypatch)

    client.get(
        "/api/v1/auth/callback",
        params={"code": "x", "state": "wrong"},
        follow_redirects=False,
    )
    client.get(
        "/api/v1/auth/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )

    assert len(_sign_in_audits(db_session)) == before


def test_callback_refuses_inactive_person(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    """A deactivated person is refused even if a membership covers today."""
    person = make_person(db_session, email=fake_expa.aiesec_email)
    person.expa_id = fake_expa.expa_id
    person.status = PersonStatus.INACTIVE
    make_membership(
        db_session,
        person=person,
        lc=make_lc(db_session),
        position=make_position(db_session),
        term=make_term(db_session),
        start=YEAR_AGO,
        end=None,
    )
    db_session.flush()

    state = _start_login(client, monkeypatch)
    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )

    _assert_sign_in_error(response, "not_allocated")
    sessions = db_session.execute(
        select(UserSession).where(UserSession.person_id == person.id)
    ).scalars()
    assert list(sessions) == []

    # The callback's own SIGN_IN_BLOCKED branch refuses before it has a person id to
    # record, so its audit row has none. (The later "no active membership" branch does
    # record the person id, so this tells the two branches apart.)
    entry = _sign_in_audits(db_session)[-1]
    assert entry.actor_person_id is None
    assert entry.diff == {"allocated": False, "reason": "not_allocated"}


def _expa_identity_is(monkeypatch: pytest.MonkeyPatch, identity: ExpaIdentity) -> None:
    """Make the next EXPA lookup answer as this identity."""
    monkeypatch.setattr(
        auth.ExpaOAuthClient,
        "get_current_person",
        Mock(return_value=identity),
    )


def test_wrong_match_fixed_by_email_correction_then_unlink(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    fake_expa: ExpaIdentity,
) -> None:
    """P was linked to the wrong EXPA account (A). The admin corrects P's email to B's,
    then unlinks. B's next sign-in links to P, and A no longer signs in as P."""
    from datetime import date

    from app.repositories import admin_people as repo
    from app.repositories.membership import build_membership_context

    person = _allocated_person(db_session)
    person.expa_id = "A"
    person.aiesec_email = "wrong@aiesec.net"

    # An MCP (matrix grants it `manage` on memberships), ranking above P's position.
    mcp = db_session.execute(select(Position).where(Position.key == "mcp")).scalar_one_or_none()
    if mcp is None:
        mcp = Position(key="mcp", label="MCP", active=True)
        db_session.add(mcp)
    mcp.rank = 7
    mcp.active = True
    admin_person = make_person(db_session, email="test-fix-admin@aiesec.net")
    admin_membership = make_membership(
        db_session,
        person=admin_person,
        lc=make_lc(db_session, name="test-fix-mc", lc_type=LCType.MC),
        position=mcp,
        term=make_term(db_session, name="test-fix-term"),
        start=YEAR_AGO,
        end=None,
    )
    db_session.flush()
    actor = [build_membership_context(db_session, admin_membership)]

    # Correct the email first, then unlink.
    repo.update_person(
        db_session,
        actor,
        person.id,
        first_name=None,
        last_name=None,
        email="b@aiesec.net",
        allowed_domains={"aiesec.net"},
    )
    assert person.expa_id == "A"  # editing the email alone changes nobody's link
    repo.unlink_expa(db_session, actor, person.id, today=date.today())
    assert person.expa_id is None

    # B signs in: matched by email, so P is now linked to B.
    _expa_identity_is(monkeypatch, ExpaIdentity(expa_id="B", aiesec_email="b@aiesec.net"))
    state = _start_login(client, monkeypatch)
    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error" not in response.headers["location"]
    db_session.refresh(person)
    assert person.expa_id == "B"

    # A signs in: no one matches, so refused.
    _expa_identity_is(monkeypatch, ExpaIdentity(expa_id="A", aiesec_email="wrong@aiesec.net"))
    state = _start_login(client, monkeypatch)
    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )
    _assert_sign_in_error(response, "not_allocated")
