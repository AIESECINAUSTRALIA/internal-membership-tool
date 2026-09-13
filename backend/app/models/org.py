"""Org-structural lookup tables: `lc`, `term`, `position`, `function`.

See `docs/data-model.md` for the full explanation of each table. In short:
`position` and `function` are plain data-driven lookup tables (not a hardcoded
enum) so a non-technical admin can add, rename, or deactivate a value at
runtime without a developer touching code (spec §1.5).
"""

import enum
from datetime import date

from sqlalchemy import Boolean, Date, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LCType(enum.StrEnum):
    LC = "LC"
    MC = "MC"


class LC(Base):
    """One row per AIESEC entity — a Local Committee, or the MC (`type = MC`)."""

    __tablename__ = "lc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    type: Mapped[LCType] = mapped_column(
        Enum(LCType, name="lctype", native_enum=False, length=10, create_constraint=True)
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Term(Base):
    """A cycle (e.g. a semester or year) used to time-scope memberships."""

    __tablename__ = "term"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)


class Position(Base):
    """Lookup: "what role" a membership represents (LCP, Team Leader, Member, ...)."""

    __tablename__ = "position"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True, index=True)
    label: Mapped[str] = mapped_column(String)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Function(Base):
    """Lookup: "which function" a membership represents (BD, MKT, oGV, ...)."""

    __tablename__ = "function"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True, index=True)
    label: Mapped[str] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
