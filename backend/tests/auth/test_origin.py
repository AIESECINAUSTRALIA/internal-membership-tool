"""Origin validation for state-changing requests."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_non_get_requests_require_matching_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_BASE_URL", "https://members.example.org")
    get_settings.cache_clear()

    try:
        with TestClient(app) as client:
            assert (
                client.post(
                    "/api/v1/auth/logout",
                    headers={"Origin": "https://evil.example.org"},
                ).status_code
                == 403
            )

            assert (
                client.post(
                    "/api/v1/auth/logout",
                ).status_code
                == 403
            )

            assert (
                client.post(
                    "/api/v1/auth/logout",
                    headers={"Origin": "https://members.example.org"},
                ).status_code
                == 204
            )
    finally:
        get_settings.cache_clear()
