"""Signing test access tokens the way Supabase would.

Real Supabase tokens can't be minted in a test, so tests sign their own with a key
pair generated here and give the API the matching public key. Everything after
that — signature, expiry, issuer, audience, the domain check, the email → person
lookup — is the real code. See docs/auth.md.
"""

import time
import uuid
from collections.abc import Generator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_token_verifier
from app.core.auth import TokenVerifier
from app.main import app

ISSUER = "https://test-project.supabase.co/auth/v1"
ALLOWED_DOMAINS = frozenset({"aiesec.net"})

PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())


class StaticKeyResolver:
    """Stands in for `jwt.PyJWKClient`: always returns our test public key."""

    def __init__(self) -> None:
        jwk = ECAlgorithm.to_jwk(PRIVATE_KEY.public_key(), as_dict=True)
        self._key = jwt.PyJWK(jwk, algorithm="ES256")

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        return self._key


def test_verifier() -> TokenVerifier:
    return TokenVerifier(
        issuer=ISSUER, allowed_email_domains=ALLOWED_DOMAINS, key_resolver=StaticKeyResolver()
    )


# Not a test, despite the name pytest would otherwise collect.
test_verifier.__test__ = False  # type: ignore[attr-defined]


def claims(**overrides: Any) -> dict[str, Any]:
    """Claims shaped like a Supabase access token. A fresh `session_id` each call
    unless one is passed, i.e. each call is a new sign-in by default."""
    now = int(time.time())
    base: dict[str, Any] = {
        "sub": "00000000-0000-0000-0000-000000000001",
        "email": "test_ada@aiesec.net",
        "aud": "authenticated",
        "iss": ISSUER,
        "iat": now,
        "exp": now + 3600,
        "role": "authenticated",
        "session_id": str(uuid.uuid4()),
    }
    base.update(overrides)
    return base


def make_token(key: Any = PRIVATE_KEY, algorithm: str = "ES256", **overrides: Any) -> str:
    return jwt.encode(claims(**overrides), key, algorithm=algorithm)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """The real app, using the rolled-back test session and the test signing key."""

    def _get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_token_verifier] = test_verifier
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
