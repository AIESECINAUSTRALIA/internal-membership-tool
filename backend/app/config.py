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

    # CORS: the browser origin the API accepts requests from (the Vite dev server locally).
    frontend_origin: str = "http://localhost:5173"

    # The Supabase project URL, e.g. https://abcd.supabase.co. Access tokens are verified
    # against its public signing keys (JWKS) — see docs/auth.md. Empty means auth is not
    # configured, and protected endpoints answer 503 instead of letting anyone in.
    supabase_url: str = ""

    # Comma-separated email domains allowed to sign in (spec §9), e.g. "aiesec.net" or
    # "aiesec.net,aiesec.org.au". Data, not code: add a domain here, not in an if-statement.
    allowed_email_domains: str = "aiesec.net"

    @property
    def allowed_email_domain_set(self) -> frozenset[str]:
        """`allowed_email_domains` split, trimmed and lower-cased."""
        return frozenset(
            domain.strip().lower()
            for domain in self.allowed_email_domains.split(",")
            if domain.strip()
        )


@lru_cache
def get_settings() -> Settings:
    """The settings, read once per process. Tests override this with FastAPI's
    `app.dependency_overrides` or by clearing the cache."""
    return Settings()
