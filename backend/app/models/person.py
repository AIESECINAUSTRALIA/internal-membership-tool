"""The `person` table.

This is the only table allowed to hold PII (spec §4.1) — full name, email
addresses, phone number. Every other table refers to a person only
indirectly, through `membership`.
"""

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PersonStatus(enum.StrEnum):
    """A fixed lifecycle state — structural to how the app behaves, so a
    constrained column rather than an admin-editable lookup table."""

    ACTIVE = "ACTIVE"
    ALUMNUS = "ALUMNUS"
    INACTIVE = "INACTIVE"
    ANONYMISED = "ANONYMISED"


class Person(Base):
    __tablename__ = "person"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String)
    preferred_name: Mapped[str | None] = mapped_column(String, nullable=True)
    aiesec_email: Mapped[str] = mapped_column(String, unique=True, index=True)
    personal_email: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    join_date: Mapped[date] = mapped_column(Date)
    status: Mapped[PersonStatus] = mapped_column(
        Enum(
            PersonStatus, name="personstatus", native_enum=False, length=20, create_constraint=True
        ),
        default=PersonStatus.ACTIVE,
    )
    # Set when a deletion request results in anonymisation (spec §8.2).
    anonymised_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
