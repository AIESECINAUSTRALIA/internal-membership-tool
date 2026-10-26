"""Tests for token verification and `GET /api/v1/me` (spec §9, docs/auth.md).

Tokens are signed in-test (see `tests/auth/helpers.py`); everything after that is
the real code. The full sign-in → permissions → audit path is in
`tests/test_sign_in_flow.py`.
"""

import time
from datetime import date, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.auth import AuthError, build_token_verifier, is_allowed_email
from app.main import app
from app.models.membership import Team, TeamMember
from app.models.person import PersonStatus
from tests.auth.helpers import bearer as _auth
from tests.auth.helpers import claims as _claims
from tests.auth.helpers import make_token as _token
from tests.helpers import (
    YEAR_AGO,
    make_function,
    make_lc,
    make_membership,
    make_person,
    make_position,
    make_term,
)

_OTHER_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())


# --- GET /api/v1/me: the happy paths ----------------------------------------


def test_me_returns_person_and_active_memberships(client: TestClient, db_session: Session) -> None:
    lc = make_lc(db_session)
    position = make_position(db_session)
    function = make_function(db_session)
    term = make_term(db_session)
    person = make_person(db_session)
    membership = make_membership(
        db_session, person=person, lc=lc, position=position, term=term, function=function
    )
    team = Team(lc_id=lc.id, function_id=function.id, term_id=term.id, name="Test Team")
    db_session.add(team)
    db_session.flush()
    db_session.add(TeamMember(team_id=team.id, membership_id=membership.id, start_date=YEAR_AGO))
    db_session.flush()

    response = client.get("/api/v1/me", headers=_auth(_token()))

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "test_ada@aiesec.net"
    assert body["person"] == {
        "id": person.id,
        "full_name": "Ada Lovelace",
        "preferred_name": None,
        "aiesec_email": "test_ada@aiesec.net",
    }
    assert body["memberships"] == [
        {
            "id": membership.id,
            "position": {"key": "test_member", "label": "Test Member"},
            "function": {"key": "test_bd", "label": "Test BD"},
            "lc": {"id": lc.id, "name": "AIESEC in Testville", "type": "LC"},
            "team": {"id": team.id, "name": "Test Team"},
            "start_date": YEAR_AGO.isoformat(),
            "end_date": None,
        }
    ]
    assert body["permissions"] == []


def test_me_returns_every_concurrent_membership(client: TestClient, db_session: Session) -> None:
    lc = make_lc(db_session)
    position = make_position(db_session)
    term = make_term(db_session)
    person = make_person(db_session)
    first = make_membership(db_session, person=person, lc=lc, position=position, term=term)
    second = make_membership(
        db_session,
        person=person,
        lc=lc,
        position=position,
        term=term,
        function=make_function(db_session),
    )

    body = client.get("/api/v1/me", headers=_auth(_token())).json()

    assert {m["id"] for m in body["memberships"]} == {first.id, second.id}
    assert all(m["team"] is None for m in body["memberships"])


def test_me_matches_email_case_insensitively(client: TestClient, db_session: Session) -> None:
    person = make_person(db_session, email="Test_Ada@AIESEC.net")

    body = client.get("/api/v1/me", headers=_auth(_token(email="TEST_ADA@aiesec.NET"))).json()

    assert body["person"]["id"] == person.id
    assert body["email"] == "test_ada@aiesec.net"


# --- GET /api/v1/me: signed in, but no access (the not-allocated page) ------


def test_me_with_no_matching_person_returns_null_person(client: TestClient) -> None:
    response = client.get("/api/v1/me", headers=_auth(_token(email="test_nobody@aiesec.net")))

    assert response.status_code == 200
    assert response.json() == {
        "email": "test_nobody@aiesec.net",
        "person": None,
        "memberships": [],
        "permissions": [],
    }


def test_me_treats_anonymised_person_as_no_match(client: TestClient, db_session: Session) -> None:
    person = make_person(db_session)
    person.status = PersonStatus.ANONYMISED
    db_session.flush()

    body = client.get("/api/v1/me", headers=_auth(_token())).json()

    assert body["person"] is None


def test_me_with_only_ended_membership_returns_no_memberships(
    client: TestClient, db_session: Session
) -> None:
    person = make_person(db_session)
    make_membership(
        db_session,
        person=person,
        lc=make_lc(db_session),
        position=make_position(db_session),
        term=make_term(db_session),
        end=date.today() - timedelta(days=1),
    )

    body = client.get("/api/v1/me", headers=_auth(_token())).json()

    assert body["person"]["id"] == person.id
    assert body["memberships"] == []


# --- GET /api/v1/me: rejected tokens ----------------------------------------


def test_me_without_token_is_401(client: TestClient) -> None:
    response = client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(_token(exp=int(time.time()) - 60), id="expired"),
        pytest.param(_token(aud="anon"), id="wrong-audience"),
        pytest.param(_token(iss="https://other.supabase.co/auth/v1"), id="wrong-issuer"),
        pytest.param(_token(key=_OTHER_PRIVATE_KEY), id="signed-by-another-key"),
        pytest.param(
            _token(key="an-hmac-secret-that-is-at-least-32-bytes", algorithm="HS256"),
            id="hs256-algorithm-confusion",
        ),
        pytest.param(jwt.encode(_claims(), None, algorithm="none"), id="unsigned-none-alg"),
        pytest.param(_token(email=None), id="no-email"),
        pytest.param("not-a-jwt", id="garbage"),
    ],
)
def test_me_with_invalid_token_is_401(client: TestClient, token: str) -> None:
    response = client.get("/api/v1/me", headers=_auth(token))

    assert response.status_code == 401


@pytest.mark.parametrize(
    "email",
    [
        "someone@gmail.com",
        "someone@notaiesec.net",
        "someone@aiesec.net.evil.com",
        "aiesec.net@gmail.com",
    ],
)
def test_me_with_email_outside_allowed_domains_is_403(client: TestClient, email: str) -> None:
    response = client.get("/api/v1/me", headers=_auth(_token(email=email)))

    assert response.status_code == 403
    assert response.json() == {"detail": "Only AIESEC accounts can sign in"}


def test_me_is_503_when_supabase_url_is_not_configured(db_session: Session) -> None:
    """Without SUPABASE_URL the API must refuse, never let everyone in."""
    app.dependency_overrides[get_settings] = lambda: Settings(supabase_url="")
    try:
        response = TestClient(app).get("/api/v1/me", headers=_auth(_token()))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503


# --- Unit tests -----------------------------------------------------------


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
def test_is_allowed_email(email: str, allowed: bool) -> None:
    assert is_allowed_email(email, frozenset({"aiesec.net", "aiesec.org.au"})) is allowed


def test_allowed_email_domains_setting_is_parsed() -> None:
    settings = Settings(allowed_email_domains=" aiesec.net, AIESEC.org.au ,,")

    assert settings.allowed_email_domain_set == frozenset({"aiesec.net", "aiesec.org.au"})


def test_build_token_verifier_targets_the_project_jwks() -> None:
    verifier = build_token_verifier(Settings(supabase_url="https://abc.supabase.co/"))

    assert verifier._issuer == "https://abc.supabase.co/auth/v1"
    key_resolver = verifier._key_resolver
    assert isinstance(key_resolver, jwt.PyJWKClient)
    assert key_resolver.uri == "https://abc.supabase.co/auth/v1/.well-known/jwks.json"


def test_build_token_verifier_refuses_empty_supabase_url() -> None:
    with pytest.raises(AuthError) as excinfo:
        build_token_verifier(Settings(supabase_url=""))

    assert excinfo.value.status_code == 503
