"""SQLAlchemy engine and session factory.

The connection string comes from `DATABASE_URL` (see `.env.example`) — the
same environment variable `migrations/env.py` reads, so the app, Alembic, and
the test suite always target the same database.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_database_url = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://membership:localdevpassword@localhost:5432/membership",
)
engine = create_engine(_database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
