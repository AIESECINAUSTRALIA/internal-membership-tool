"""SQLAlchemy engine and session factory.

The connection string comes from `DATABASE_URL` (see `.env.example`) — the
same environment variable `migrations/env.py` reads, so the app, Alembic, and
the test suite always target the same database.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(os.environ["DATABASE_URL"])
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
