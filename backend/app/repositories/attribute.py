"""Write-path validation and CRUD for `attribute_value` (spec §4.2).

`attribute.validation` (min/max, required, regex) is applied here, not as a
DB constraint — what "valid" means depends on `attribute.data_type`, which
varies per catalog row, so a single CHECK constraint on `attribute_value`
can't express it. This module is the only place that should write an
`attribute_value` row; route new call sites through `set_attribute_value`
rather than constructing rows directly.
"""

import re
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.attribute import (
    Attribute,
    AttributeDataType,
    AttributeEntityType,
    AttributeValue,
)

# The four typed columns on attribute_value, in data_type-independent order.
_VALUE_COLUMNS = ("value_text", "value_number", "value_date", "value_bool")


class AttributeValidationError(ValueError):
    """Raised when a value fails type-checking against `attribute.data_type`
    or a rule in `attribute.validation`."""


def _type_check(attribute: Attribute, raw_value: object) -> dict[str, object | None]:
    """Check `raw_value` matches `attribute.data_type` and return the
    `{column_name: value}` mapping to write, with the other three typed
    columns explicitly None."""
    columns: dict[str, object | None] = dict.fromkeys(_VALUE_COLUMNS)

    if attribute.data_type == AttributeDataType.TEXT:
        if not isinstance(raw_value, str):
            raise AttributeValidationError(f"{attribute.key}: expected text, got {raw_value!r}")
        columns["value_text"] = raw_value
    elif attribute.data_type == AttributeDataType.NUMBER:
        # Two sequential checks (rather than one combined condition) so type
        # narrowing carries `raw_value` through to `int | float` below.
        if isinstance(raw_value, bool):
            raise AttributeValidationError(f"{attribute.key}: expected a number, got {raw_value!r}")
        if not isinstance(raw_value, int | float):
            raise AttributeValidationError(f"{attribute.key}: expected a number, got {raw_value!r}")
        columns["value_number"] = float(raw_value)
    elif attribute.data_type == AttributeDataType.DATE:
        if isinstance(raw_value, datetime):
            raise AttributeValidationError(f"{attribute.key}: expected a date, got {raw_value!r}")
        if not isinstance(raw_value, date):
            raise AttributeValidationError(f"{attribute.key}: expected a date, got {raw_value!r}")
        columns["value_date"] = raw_value
    elif attribute.data_type == AttributeDataType.BOOLEAN:
        if not isinstance(raw_value, bool):
            raise AttributeValidationError(
                f"{attribute.key}: expected a boolean, got {raw_value!r}"
            )
        columns["value_bool"] = raw_value
    elif attribute.data_type == AttributeDataType.ENUM:
        options = attribute.enum_options or []
        if not isinstance(raw_value, str) or raw_value not in options:
            raise AttributeValidationError(
                f"{attribute.key}: {raw_value!r} is not one of {options}"
            )
        columns["value_text"] = raw_value

    return columns


def _parse_bound(attribute: Attribute, bound: object) -> object | None:
    """`attribute.validation["min"/"max"]` for a DATE attribute is stored as
    an ISO date string (JSON has no date type) — parse it back before
    comparing against the coerced value."""
    if bound is None:
        return None
    if attribute.data_type == AttributeDataType.DATE and isinstance(bound, str):
        return date.fromisoformat(bound)
    return bound


def validate_and_coerce(attribute: Attribute, raw_value: object) -> dict[str, object | None]:
    """Validate `raw_value` against `attribute.data_type` and
    `attribute.validation`, returning the `{column_name: value}` mapping
    ready to assign onto an `AttributeValue` row.

    Raises `AttributeValidationError` on any failure: wrong type, an enum
    value outside `enum_options`, a missing required value, an out-of-range
    number/date, or a regex mismatch on text.
    """
    rules = attribute.validation or {}

    if raw_value is None:
        if rules.get("required"):
            raise AttributeValidationError(f"{attribute.key} is required")
        return dict.fromkeys(_VALUE_COLUMNS)

    columns = _type_check(attribute, raw_value)
    stored_value = next(value for value in columns.values() if value is not None)

    if attribute.data_type in (AttributeDataType.NUMBER, AttributeDataType.DATE):
        bound_min = _parse_bound(attribute, rules.get("min"))
        bound_max = _parse_bound(attribute, rules.get("max"))
        if bound_min is not None and stored_value < bound_min:  # type: ignore[operator]
            raise AttributeValidationError(
                f"{attribute.key}: {stored_value} is below the minimum {bound_min}"
            )
        if bound_max is not None and stored_value > bound_max:  # type: ignore[operator]
            raise AttributeValidationError(
                f"{attribute.key}: {stored_value} is above the maximum {bound_max}"
            )

    if attribute.data_type == AttributeDataType.TEXT:
        regex = rules.get("regex")
        if regex is not None and re.fullmatch(str(regex), str(stored_value)) is None:
            raise AttributeValidationError(
                f"{attribute.key}: {stored_value!r} does not match the required format"
            )

    return columns


def set_attribute_value(
    session: Session,
    *,
    attribute: Attribute,
    entity_type: AttributeEntityType,
    entity_id: int,
    raw_value: object,
    recorded_by_membership_id: int,
) -> AttributeValue:
    """Validate `raw_value` and upsert the `attribute_value` row for
    `(attribute, entity_type, entity_id)`. Every attribute here is
    single-valued (spec §4.2), so calling this again for the same entity
    overwrites the existing row rather than inserting a duplicate.
    """
    columns = validate_and_coerce(attribute, raw_value)

    existing = session.execute(
        select(AttributeValue).where(
            AttributeValue.attribute_id == attribute.id,
            AttributeValue.entity_type == entity_type,
            AttributeValue.entity_id == entity_id,
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = AttributeValue(
            attribute_id=attribute.id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        session.add(existing)

    for column, value in columns.items():
        setattr(existing, column, value)
    existing.recorded_by = recorded_by_membership_id
    existing.recorded_at = datetime.utcnow()

    session.flush()
    return existing


def get_attribute_value(
    session: Session,
    *,
    attribute: Attribute,
    entity_type: AttributeEntityType,
    entity_id: int,
) -> object | None:
    """The single typed value recorded for `(attribute, entity_type,
    entity_id)`, or None if nothing has been recorded yet."""
    row = session.execute(
        select(AttributeValue).where(
            AttributeValue.attribute_id == attribute.id,
            AttributeValue.entity_type == entity_type,
            AttributeValue.entity_id == entity_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    for column in _VALUE_COLUMNS:
        value = getattr(row, column)
        if value is not None:
            return value
    return None
