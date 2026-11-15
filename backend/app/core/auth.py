"""Verifying who is calling the API (spec §9). Read `docs/auth.md` first.

The browser signs in with Google through Supabase Auth and gets a short-lived
access token (a JWT). It sends that token on every request as
`Authorization: Bearer <token>`. This module checks the token and returns the
caller's email. It does NOT decide what the caller may do — that is the
permission matrix's job (spec §3), resolved from the email's `person` row.

Why this is safe without a shared secret: Supabase signs tokens with a private
key that only Supabase holds, and publishes the matching public keys at
`<SUPABASE_URL>/auth/v1/.well-known/jwks.json` (a "JWKS"). We verify the
signature with the public key, so a token we accept can only have come from our
Supabase project.
"""

from dataclasses import dataclass
from typing import Any, Protocol

import jwt

from app.config import Settings

# Supabase signs with ES256 (an elliptic-curve key). Accepting only asymmetric
# algorithms matters: if HS256 were allowed, an attacker could sign a token with
# the PUBLIC key as an HMAC secret ("algorithm confusion").
ALGORITHMS = ["ES256"]
# Every token Supabase issues to a signed-in user carries this audience.
AUDIENCE = "authenticated"


class AuthError(Exception):
    """Authentication failed. `status_code` is the HTTP status to answer with:
    401 (no valid token: sign in again), 403 (valid token, but an email outside
    the allowed domains), or 503 (auth not configured on this server)."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class AuthenticatedUser:
    """Who the token says the caller is. `email` is lower-cased."""

    subject: str  # Supabase's user id (`sub` claim). Not stored anywhere by us.
    email: str
    # Supabase's id for this sign-in session (`session_id` claim). It stays the same
    # across token refreshes and changes on each new sign-in, so it tells "a new
    # sign-in" apart from "a page reload". Not personal data.
    session_id: str | None = None


class SigningKeyResolver(Protocol):
    """Finds the public key a token was signed with. `jwt.PyJWKClient` fits this
    shape; tests pass a stub holding a key they generated themselves."""

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK: ...


class TokenVerifier:
    """Checks an access token: signature, expiry, issuer, audience, email domain."""

    def __init__(
        self,
        *,
        issuer: str,
        allowed_email_domains: frozenset[str],
        key_resolver: SigningKeyResolver,
    ) -> None:
        self._issuer = issuer
        self._allowed_email_domains = allowed_email_domains
        self._key_resolver = key_resolver

    def verify(self, token: str) -> AuthenticatedUser:
        claims = self._decode(token)

        email = claims.get("email")
        subject = claims.get("sub")
        if not isinstance(email, str) or not email or not isinstance(subject, str):
            raise AuthError(401, "Token has no email or subject")

        email = email.strip().lower()
        if not is_allowed_email(email, self._allowed_email_domains):
            raise AuthError(403, "Only AIESEC accounts can sign in")

        session_id = claims.get("session_id")
        return AuthenticatedUser(
            subject=subject,
            email=email,
            session_id=session_id if isinstance(session_id, str) and session_id else None,
        )

    def _decode(self, token: str) -> dict[str, Any]:
        try:
            signing_key = self._key_resolver.get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=ALGORITHMS,
                audience=AUDIENCE,
                issuer=self._issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.PyJWKClientConnectionError as exc:
            # We couldn't download Supabase's public keys. Not the caller's fault.
            raise AuthError(503, "Could not reach the sign-in provider") from exc
        except jwt.PyJWTError as exc:
            # Bad signature, expired, wrong audience/issuer, unknown key, malformed...
            # The caller only needs to know "sign in again"; the reason stays server-side.
            raise AuthError(401, "Invalid or expired token") from exc
        return claims


def is_allowed_email(email: str, allowed_domains: frozenset[str]) -> bool:
    """True when the part after the LAST `@` is exactly one of `allowed_domains`.

    An exact match, not `endswith`: `x@notaiesec.net` and `x@aiesec.net.evil.com`
    are both rejected.
    """
    _, at, domain = email.rpartition("@")
    return bool(at) and domain.lower() in allowed_domains


_verifier_cache: dict[tuple[str, frozenset[str]], TokenVerifier] = {}


def build_token_verifier(settings: Settings) -> TokenVerifier:
    """The verifier for the configured Supabase project.

    Cached, because `PyJWKClient` caches the downloaded public keys: building a new
    one per request would fetch the JWKS on every call.
    """
    supabase_url = settings.supabase_url.rstrip("/")
    if not supabase_url:
        raise AuthError(503, "Authentication is not configured (SUPABASE_URL is empty)")

    cache_key = (supabase_url, settings.allowed_email_domain_set)
    verifier = _verifier_cache.get(cache_key)
    if verifier is None:
        verifier = TokenVerifier(
            issuer=f"{supabase_url}/auth/v1",
            allowed_email_domains=settings.allowed_email_domain_set,
            key_resolver=jwt.PyJWKClient(f"{supabase_url}/auth/v1/.well-known/jwks.json"),
        )
        _verifier_cache[cache_key] = verifier
    return verifier
