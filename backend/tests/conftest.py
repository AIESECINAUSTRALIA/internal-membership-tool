"""Shared pytest fixtures.

Supports PostgreSQL via `DATABASE_URL` as well as an in-memory SQLite fallback
for running unit and API tests in environments without a live PostgreSQL service.

Each test gets its own fresh in-memory SQLite database (via a per-invocation
engine) so hardcoded IDs in one test file never collide with those in another.
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


def _make_engine():
    if _database_url.startswith("sqlite"):
        engine = create_engine(
            _database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        return engine
    return create_engine(_database_url)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """A session backed by its own fresh in-memory SQLite database.

    Each invocation creates a new engine + schema so there is no state leakage
    between test functions, even when tests use hardcoded primary-key IDs.
    """
    engine = _make_engine()
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()
