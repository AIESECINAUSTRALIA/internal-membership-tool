"""Declarative base and model import registry.

Every ORM model inherits from ``Base``. ``app.models`` (imported below and by
Alembic's ``env.py``) must import every model module so that ``Base.metadata``
is fully populated before autogenerate runs.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
