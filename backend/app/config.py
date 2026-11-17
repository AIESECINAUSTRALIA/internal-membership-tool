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

    frontend_origin: str = "http://localhost:5173"

    # AIESEC OAuth authorization endpoint.
    expa_auth_url: str = "https://auth.aiesec.org"

    # EXPA GraphQL API endpoint.
    expa_graphql_url: str = "https://gis-api.aiesec.org/graphql"

    # Registered OAuth application credentials.
    expa_client_id: str = ""
    expa_client_secret: str = ""

    # Public origin of the deployed application.
    app_base_url: str = "http://localhost:8000"

    # Fixed session lifetime; requests never extend expiry.
    session_ttl_hours: int = 12

    # Exact permitted AIESEC email domains.
    allowed_email_domains: str = "aiesec.net"

    @property
    def allowed_email_domain_set(self) -> frozenset[str]:
        return frozenset(
            domain.strip().lower()
            for domain in self.allowed_email_domains.split(",")
            if domain.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
