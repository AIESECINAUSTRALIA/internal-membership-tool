"""Shared pytest fixtures.

Supports PostgreSQL via `DATABASE_URL` as well as an in-memory SQLite fallback
for running unit and API tests in environments without a live PostgreSQL service.
"""

import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base

_database_url = os.environ.get("DATABASE_URL", "sqlite:///:memory:")

if _database_url.startswith("sqlite"):
    _test_engine = create_engine(
        _database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=_test_engine)
else:
    _test_engine = create_engine(_database_url)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """A session bound to a connection-level transaction that's rolled back."""
    connection = _test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
