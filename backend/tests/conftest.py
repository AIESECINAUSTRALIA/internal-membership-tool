"""Shared pytest fixtures.

Tests run against the real, already-migrated database pointed to by
`DATABASE_URL` (see `docs/local-development.md` and the CI workflow) rather
than a mocked or in-memory one, so they catch anything a mock would hide —
constraint violations, FK behaviour, enum/check constraints.
"""

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from app.db.session import engine


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """A session bound to a connection-level transaction that's always rolled
    back, so a test can `add`/`flush` freely without leaving data behind or
    depending on any other test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
