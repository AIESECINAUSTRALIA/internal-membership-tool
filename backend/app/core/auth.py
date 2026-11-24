"""Talking to EXPA, AIESEC's own OAuth provider (spec §9). Read `docs/auth.md` first.

Sign-in is the standard OAuth "authorization code" flow, run by the backend:

1. `GET /auth/login` sends the browser to EXPA's sign-in page (`authorization_url`).
2. EXPA sends the browser back to `GET /auth/callback?code=...&state=...`.
3. The backend swaps the one-time `code` for an EXPA access token (`exchange_code`),
   using our client secret, so the browser never sees the token.
4. The backend asks EXPA's GraphQL API who that token belongs to
   (`get_current_person`): their EXPA person id and AIESEC email.

The EXPA access token is used for those two calls and then thrown away: we never
store it and never call EXPA on the user's behalf afterwards. From then on the user
is identified by our own session cookie (`app/core/sessions.py`).

This module does NOT decide what the user may do. That is the permission matrix's
job (spec §3), resolved from their `person` row and memberships.

The HTTP calls are synchronous on purpose: the callback route is a plain `def`, which
FastAPI runs in a worker thread, so the database work in the same route can't block
other requests.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.config import Settings


class AuthError(Exception):
    """Authentication failure with an HTTP status and safe public message."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class AuthenticatedUser:
    """Identity established through EXPA and a local server-side session."""

    subject: str
    email: str


@dataclass(frozen=True)
class ExpaIdentity:
    """Identity returned by EXPA GraphQL."""

    expa_id: str
    aiesec_email: str


def is_allowed_email(email: str, allowed_domains: frozenset[str]) -> bool:
    """Check the exact email domain, never a suffix match."""
    _, at, domain = email.strip().lower().rpartition("@")
    return bool(at) and bool(domain) and domain in allowed_domains


class ExpaOAuthClient:
    """Exchange an OAuth code and retrieve the authenticated EXPA identity."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def callback_url(self) -> str:
        return f"{self.settings.app_base_url.rstrip('/')}/api/v1/auth/callback"

    def authorization_url(self, state: str) -> str:
        if not self.settings.expa_client_id:
            raise AuthError(503, "EXPA authentication is not configured")

        params = urlencode(
            {
                "response_type": "code",
                "client_id": self.settings.expa_client_id,
                "redirect_uri": self.callback_url,
                "state": state,
            }
        )
        return f"{self.settings.expa_auth_url.rstrip('/')}/oauth/authorize?{params}"

    def exchange_code(self, code: str) -> str:
        if not self.settings.expa_client_id or not self.settings.expa_client_secret:
            raise AuthError(503, "EXPA authentication is not configured")

        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.settings.expa_client_id,
            "client_secret": self.settings.expa_client_secret,
            "redirect_uri": self.callback_url,
        }

        try:
            with httpx.Client(timeout=15) as client:
                response = client.post(
                    f"{self.settings.expa_auth_url.rstrip('/')}/oauth/token",
                    data=payload,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthError(502, "EXPA token exchange failed") from exc

        token = data.get("access_token") if isinstance(data, dict) else None
        if not isinstance(token, str) or not token:
            raise AuthError(502, "EXPA returned no access token")

        return token

    def get_current_person(self, access_token: str) -> ExpaIdentity:
        query = """
        query GetCurrentPerson {
          currentPerson {
            id
            aiesec_email
          }
        }
        """

        try:
            with httpx.Client(timeout=15) as client:
                response = client.post(
                    self.settings.expa_graphql_url,
                    json={"query": query},
                    headers={
                        "Authorization": access_token,
                    },
                )
                response.raise_for_status()
                result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthError(502, "Could not retrieve EXPA identity") from exc

        if not isinstance(result, dict) or result.get("errors"):
            raise AuthError(502, "EXPA identity lookup failed")

        data = result.get("data")
        person = data.get("currentPerson") if isinstance(data, dict) else None
        if not isinstance(person, dict):
            raise AuthError(502, "EXPA returned no person")

        expa_id = person.get("id")
        email = person.get("aiesec_email")

        if expa_id is None or not isinstance(email, str) or not email.strip():
            raise AuthError(502, "EXPA identity is incomplete")

        return ExpaIdentity(
            expa_id=str(expa_id),
            aiesec_email=email.strip().lower(),
        )
