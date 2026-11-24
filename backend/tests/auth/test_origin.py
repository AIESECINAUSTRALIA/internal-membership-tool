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


def test_frontend_origin_is_allowed_with_trailing_slash_and_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Locally the browser app (FRONTEND_ORIGIN) is a different origin from the API
    (APP_BASE_URL). Writes from it must pass, however the variables are spelled."""
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8000/")
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://LocalHost:5173/")
    get_settings.cache_clear()

    try:
        with TestClient(app) as client:
            for origin in ("http://localhost:5173", "http://localhost:8000"):
                response = client.post("/api/v1/auth/logout", headers={"Origin": origin})
                assert response.status_code == 204, origin

            assert (
                client.post(
                    "/api/v1/auth/logout",
                    headers={"Origin": "http://localhost:3000"},
                ).status_code
                == 403
            )
    finally:
        get_settings.cache_clear()


def test_head_requests_skip_the_origin_check() -> None:
    with TestClient(app) as client:
        assert client.head("/healthz").status_code != 403
