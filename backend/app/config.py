"""Application settings, read from environment variables (see `.env.example`).

Every value the API reads from the environment is declared here, once, with a
type and a safe default. Code imports `get_settings()` instead of calling
`os.environ` directly, so there is one place to look for "what can I configure?".

`DATABASE_URL` is the one exception: it is read in `app/db/session.py` and
`migrations/env.py` directly, so Alembic can use it without importing the app.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # Where the browser app runs (the Vite dev server locally). Used for CORS, for the
    # Origin check on writes (app/main.py), and as the page the browser lands on after
    # signing in. On a deployment this equals APP_BASE_URL (Firebase serves both).
    frontend_origin: str = "http://localhost:5173"

    # EXPA's OAuth server: where the browser is sent to sign in. EXPA staging on dev.
    expa_auth_url: str = "https://auth.aiesec.org"

    # EXPA's GraphQL API, asked "who is this?" with the access token after sign-in.
    expa_graphql_url: str = "https://gis-api.aiesec.org/graphql"

    # Credentials of our EXPA developer app (owned by the shared MC EXPA account, never
    # a personal one). The secret lives in Secret Manager / `.env`, never in git. Empty
    # means sign-in is not configured, and `/auth/login` answers 503.
    expa_client_id: str = ""
    expa_client_secret: str = ""

    # Public URL of the API as EXPA sees it. The OAuth callback URL is built from it
    # (`<APP_BASE_URL>/api/v1/auth/callback`), and must match the redirect URI
    # registered with EXPA exactly.
    app_base_url: str = "http://localhost:8000"

    # How long a session lasts after sign-in. Fixed: using the app does not extend it,
    # so a stolen cookie is useless after this many hours at most.
    session_ttl_hours: int = 12

    # Comma-separated email domains allowed to sign in (spec §9), e.g. "aiesec.net" or
    # "aiesec.net,aiesec.org.au". Data, not code: add a domain here, not in an if-statement.
    # Checked once, at sign-in: changing it does not end sessions that already exist
    # (they run out within SESSION_TTL_HOURS). See docs/auth.md.
    allowed_email_domains: str = "aiesec.net"

    @property
    def allowed_email_domain_set(self) -> frozenset[str]:
        """`allowed_email_domains` split, trimmed and lower-cased."""
        return frozenset(
            domain.strip().lower()
            for domain in self.allowed_email_domains.split(",")
            if domain.strip()
        )

    @property
    def uses_https(self) -> bool:
        """True on deployments. Cookies are marked `Secure` only then, because some
        browsers (Safari) drop `Secure` cookies on plain http://localhost."""
        return self.app_base_url.strip().lower().startswith("https://")


@lru_cache
def get_settings() -> Settings:
    """The settings, read once per process. Tests override this with FastAPI's
    `app.dependency_overrides` or by clearing the cache."""
    return Settings()
