"""Declarative base and model import registry.

Every ORM model inherits from ``Base``. ``app.models`` (imported below and by
Alembic's ``env.py``) must import every model module so that ``Base.metadata``
is fully populated before autogenerate runs.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Matches the naming already baked into the initial migration (e.g.
# `ix_position_key`), so a future `alembic revision --autogenerate` names new
# indexes/constraints the same way instead of proposing a rename of existing
# ones. Primary keys and foreign keys are left unnamed, same as the initial
# migration. `uq` covers a future multi-column UniqueConstraint (single-column
# uniqueness here is expressed as a unique index instead).
_NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=_NAMING_CONVENTION)
