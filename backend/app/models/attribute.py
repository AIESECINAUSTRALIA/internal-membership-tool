"""The attribute catalog and its values (spec §4.2).

`attribute` is the config table for every volatile, term-to-term-changing field —
custom person/membership fields *and* every KPI definition (`applies_to = 'kpi'`).
Adding a metric or a custom field is a row here, never a migration (spec §1.5).

`attribute_value` holds values for `applies_to IN ('person', 'membership')` only.
KPI values live in `kpi_record` (`app/models/kpi.py`) instead, because they're
time-series data, not a single per-entity value — see that module's docstring.

See `docs/data-model.md` → "EAV: attribute + attribute_value" for why this part of
the schema is EAV while everything else is plain relational tables.
"""

import enum
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AttributeAppliesTo(enum.StrEnum):
    """What kind of entity `attribute.key` describes. `KPI` attributes are
    catalogued here but their values live in `kpi_record`, not
    `attribute_value` — see `AttributeEntityType` below."""

    PERSON = "person"
    MEMBERSHIP = "membership"
    KPI = "kpi"


class AttributeDataType(enum.StrEnum):
    """The shape of value a given attribute expects. Determines which single
    typed column on `attribute_value` (or `kpi_record.value_number`, for
    `KPI`-applying attributes) gets written."""

    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    ENUM = "enum"


class AttributeEntityType(enum.StrEnum):
    """Which table `attribute_value.entity_id` points into. Deliberately a
    subset of `AttributeAppliesTo` — there is no `KPI` case here because KPI
    values are never stored as an `attribute_value` row."""

    PERSON = "person"
    MEMBERSHIP = "membership"


class Attribute(Base):
    """One catalog row per custom field or KPI. `key` is the stable
    machine-readable identifier code refers to; `label` and `validation` are
    freely admin-editable without touching either code or `key`."""

    __tablename__ = "attribute"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True, index=True)
    label: Mapped[str] = mapped_column(String)
    applies_to: Mapped[AttributeAppliesTo] = mapped_column(
        Enum(
            AttributeAppliesTo,
            name="attributeappliesto",
            native_enum=False,
            length=20,
            create_constraint=True,
        )
    )
    data_type: Mapped[AttributeDataType] = mapped_column(
        Enum(
            AttributeDataType,
            name="attributedatatype",
            native_enum=False,
            length=10,
            create_constraint=True,
        )
    )
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    # List of allowed strings when data_type = ENUM, e.g. ["XS", "S", "M", "L"].
    enum_options: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    # Applied on write by app/repositories/attribute.py::validate_and_coerce —
    # not a DB constraint, since the shape of "validation" varies per data_type.
    # Supported keys: required (bool), min / max (number or date attributes),
    # regex (text attributes). See docs/data-model.md for the full contract.
    validation: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    # Set when the attribute is scoped to one function (e.g. a BD-only field).
    # Null means it applies across every function.
    function_id: Mapped[int | None] = mapped_column(ForeignKey("function.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Provenance only — which term this attribute/KPI started being tracked in.
    # An FK to `term` (not a free-text field) so it stays consistent with every
    # other term-scoping column in the schema; never used to gate reads/writes.
    term_introduced_id: Mapped[int | None] = mapped_column(ForeignKey("term.id"), nullable=True)


class AttributeValue(Base):
    """A single `attribute` value recorded against a `person` or
    `membership` row. `entity_id` is a polymorphic reference (its meaning
    depends on `entity_type`) — it cannot be a real foreign key, since a
    single column can't reference two different tables. See
    docs/data-model.md for how referential integrity is kept anyway."""

    __tablename__ = "attribute_value"
    __table_args__ = (
        # One value per (attribute, entity) — every attribute here is
        # single-valued (spec §4.2). Leads with (entity_type, entity_id) so
        # the same index also serves "all attribute values for this person"
        # lookups, not just the uniqueness check.
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "attribute_id",
            name="uq_attribute_value_entity_attribute",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attribute_id: Mapped[int] = mapped_column(ForeignKey("attribute.id"))
    entity_type: Mapped[AttributeEntityType] = mapped_column(
        Enum(
            AttributeEntityType,
            name="attributeentitytype",
            native_enum=False,
            length=10,
            create_constraint=True,
        )
    )
    entity_id: Mapped[int] = mapped_column(Integer)
    # Exactly one of these four is set, matching attribute.data_type
    # (ENUM-typed attributes are stored as their option string in value_text).
    # Enforced by app/repositories/attribute.py on write, not a DB constraint.
    value_text: Mapped[str | None] = mapped_column(String, nullable=True)
    value_number: Mapped[float | None] = mapped_column(
        Numeric(12, 2, asdecimal=False), nullable=True
    )
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    value_bool: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    recorded_by: Mapped[int] = mapped_column(ForeignKey("membership.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
