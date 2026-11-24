"""Shared fixtures for EXPA authentication tests."""

from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.sessions import generate_token, hash_token, utc_now
from app.main import app
from app.models.person import Person
from app.models.user_session import UserSession
from tests.helpers import api_client_options


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Real FastAPI app using the test database session."""

    def _get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _get_db

    try:
        with TestClient(app, **api_client_options()) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def sign_in_as(client: TestClient, db: Session, person: Person) -> None:
    """Create a valid local session and attach its cookie to the test client."""
    if person.expa_id is None:
        person.expa_id = f"test-expa-{person.id}"

    token = generate_token()
    db.add(
        UserSession(
            token_hash=hash_token(token),
            person_id=person.id,
            expires_at=utc_now() + timedelta(hours=12),
        )
    )
    db.flush()
    client.cookies.set("__session", token)
