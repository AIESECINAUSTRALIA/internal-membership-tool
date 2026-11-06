"""Catalog management for `attribute`, and write-path validation and CRUD for
`attribute_value` (spec §1.5, §4.2).

`attribute.validation` (min/max, required, regex) is applied here, not as a
DB constraint — what "valid" means depends on `attribute.data_type`, which
varies per catalog row, so a single CHECK constraint on `attribute_value`
can't express it. This module is the only place that should write an
`attribute_value` row; route new call sites through `set_attribute_value`
rather than constructing rows directly.

Catalog edits are limited so they can't strand values already stored (see
`docs/data-model.md` → "Editing the catalog"). Every catalog change calls
`record_audit` in the same session, so the audit entry is saved if and only if
the change is saved. Attributes are never hard-deleted: "delete" means
`deactivate_attribute`, which leaves every value that references the row alone.
"""

import math
import re
from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.models.attribute import (
    Attribute,
    AttributeAppliesTo,
    AttributeDataType,
    AttributeEntityType,
    AttributeValue,
)
from app.models.kpi import KpiRecord
from app.models.org import Function

# The four typed columns on attribute_value, in data_type-independent order.
_VALUE_COLUMNS = ("value_text", "value_number", "value_date", "value_bool")

# `attribute.key` is what code refers to, so it stays machine-friendly.
_KEY_PATTERN = re.compile(r"[a-z][a-z0-9_]*")

# Which `attribute.validation` rules mean something for each data_type. `min` and
# `max` are numbers for NUMBER and ISO date strings for DATE (JSON has no date type).
_ALLOWED_RULES: dict[AttributeDataType, frozenset[str]] = {
    AttributeDataType.TEXT: frozenset({"required", "regex"}),
    AttributeDataType.NUMBER: frozenset({"required", "min", "max"}),
    AttributeDataType.DATE: frozenset({"required", "min", "max"}),
    AttributeDataType.BOOLEAN: frozenset({"required"}),
    AttributeDataType.ENUM: frozenset({"required"}),
}

# The columns an edit may change, also what the audit log snapshots. `key` and
# `applies_to` are not here: they are fixed when the attribute is created.
_EDITABLE_FIELDS = ("label", "data_type", "unit", "enum_options", "validation", "function_id")


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
        # NaN compares False against everything, so it would slip past min/max.
        if not math.isfinite(raw_value):
            raise AttributeValidationError(f"{attribute.key}: {raw_value!r} is not a finite number")
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
    number/date, a regex mismatch on text, or an attribute that has been retired
    (`active = false`): its old values stay, but it takes no new ones.
    """
    if not attribute.active:
        raise AttributeValidationError(f"{attribute.key} is retired and takes no new values")

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
    if attribute.applies_to.value != entity_type.value:
        raise AttributeValidationError(
            f"{attribute.key} applies to {attribute.applies_to.value!r}, not {entity_type.value!r}"
        )

    columns = validate_and_coerce(attribute, raw_value)
    values = {
        **columns,
        "recorded_by": recorded_by_membership_id,
        "recorded_at": datetime.now(UTC),
    }

    # One atomic INSERT ... ON CONFLICT DO UPDATE instead of SELECT-then-INSERT,
    # which races: two concurrent first writes would both see "no row" and the
    # second would hit the unique constraint.
    stmt = (
        insert(AttributeValue)
        .values(
            attribute_id=attribute.id,
            entity_type=entity_type,
            entity_id=entity_id,
            **values,
        )
        .on_conflict_do_update(
            constraint="uq_attribute_value_entity_attribute",
            set_=values,
        )
        .returning(AttributeValue)
        # Refresh the object if this row is already loaded in the session —
        # otherwise SQLAlchemy hands back the cached, pre-update copy.
        .execution_options(populate_existing=True)
    )
    return session.execute(stmt).scalar_one()


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
        value: object | None = getattr(row, column)
        if value is not None:
            return value
    return None


# ---------------------------------------------------------------------------
# The catalog (spec §1.5): add, edit, retire
# ---------------------------------------------------------------------------


def _check_bound(data_type: AttributeDataType, rule: str, bound: object) -> float | date:
    """Return a `min`/`max` rule as a comparable value, or raise if it's malformed."""
    if data_type == AttributeDataType.DATE:
        try:
            return date.fromisoformat(str(bound))
        except ValueError:
            raise AttributeValidationError(f"{rule} must be an ISO date (YYYY-MM-DD)") from None
    if isinstance(bound, bool) or not isinstance(bound, int | float) or not math.isfinite(bound):
        raise AttributeValidationError(f"{rule} must be a number")
    return float(bound)


def _check_validation_rules(
    data_type: AttributeDataType, validation: Mapping[str, object] | None
) -> None:
    """Reject rules `validate_and_coerce` couldn't apply, so a bad rule fails here
    when an admin saves it, not later when someone records a value."""
    if validation is None:
        return

    unknown = set(validation) - _ALLOWED_RULES[data_type]
    if unknown:
        raise AttributeValidationError(
            f"{', '.join(sorted(unknown))} can't be used on a {data_type.value} attribute"
        )
    if not isinstance(validation.get("required", False), bool):
        raise AttributeValidationError("required must be true or false")

    bound_min = validation.get("min")
    bound_max = validation.get("max")
    parsed_min = None if bound_min is None else _check_bound(data_type, "min", bound_min)
    parsed_max = None if bound_max is None else _check_bound(data_type, "max", bound_max)
    if parsed_min is not None and parsed_max is not None:
        if parsed_min > parsed_max:  # type: ignore[operator]
            raise AttributeValidationError("min can't be above max")

    regex = validation.get("regex")
    if regex is not None:
        try:
            re.compile(str(regex))
        except re.error:
            raise AttributeValidationError("regex is not a valid pattern") from None


def _check_enum_options(data_type: AttributeDataType, enum_options: Sequence[str] | None) -> None:
    if data_type != AttributeDataType.ENUM:
        if enum_options is not None:
            raise AttributeValidationError("Only enum attributes can have options")
        return
    if not enum_options or any(not option.strip() for option in enum_options):
        raise AttributeValidationError("An enum attribute needs at least one non-blank option")
    if len(set(enum_options)) != len(enum_options):
        raise AttributeValidationError("Enum options must be unique")


def _check_definition(
    *,
    label: str,
    applies_to: AttributeAppliesTo,
    data_type: AttributeDataType,
    enum_options: Sequence[str] | None,
    validation: Mapping[str, object] | None,
) -> None:
    """Raise `AttributeValidationError` unless these fields form a usable attribute."""
    if not label.strip():
        raise AttributeValidationError("Enter a label")
    # kpi_record only has value_number, so `record_kpi` refuses anything else.
    if applies_to == AttributeAppliesTo.KPI and data_type != AttributeDataType.NUMBER:
        raise AttributeValidationError("A KPI must have data type number")
    _check_enum_options(data_type, enum_options)
    _check_validation_rules(data_type, validation)


def _require_known_function(session: Session, function_id: int | None) -> None:
    if function_id is not None and session.get(Function, function_id) is None:
        raise AttributeValidationError(f"Function {function_id} not found")


def _snapshot(attribute: Attribute) -> dict[str, object]:
    """The audit-log view of an attribute. Catalog config only, no personal data."""
    snapshot: dict[str, object] = {field: getattr(attribute, field) for field in _EDITABLE_FIELDS}
    snapshot["data_type"] = attribute.data_type.value
    return snapshot


def list_attributes(
    session: Session,
    *,
    applies_to: AttributeAppliesTo | None = None,
    include_inactive: bool = False,
) -> Sequence[Attribute]:
    """Return catalog rows ordered by label. Active-only by default."""
    stmt = select(Attribute).order_by(Attribute.label, Attribute.id)
    if applies_to is not None:
        stmt = stmt.where(Attribute.applies_to == applies_to)
    if not include_inactive:
        stmt = stmt.where(Attribute.active.is_(True))
    return session.execute(stmt).scalars().all()


def attribute_ids_in_use(session: Session, attribute_ids: Collection[int]) -> set[int]:
    """Which of `attribute_ids` have a stored `attribute_value` or `kpi_record`."""
    values = select(AttributeValue.attribute_id).where(
        AttributeValue.attribute_id.in_(attribute_ids)
    )
    records = select(KpiRecord.attribute_id).where(KpiRecord.attribute_id.in_(attribute_ids))
    return set(session.execute(values.union(records)).scalars())


def create_attribute(
    session: Session,
    *,
    key: str,
    label: str,
    applies_to: AttributeAppliesTo,
    data_type: AttributeDataType,
    unit: str | None = None,
    enum_options: list[str] | None = None,
    validation: dict[str, object] | None = None,
    function_id: int | None = None,
    actor_membership_id: int | None = None,
) -> Attribute:
    """Insert a catalog row and audit-log the creation.

    Raises `AttributeValidationError` if the definition is unusable. A taken
    `key` surfaces as `IntegrityError` from the unique constraint.
    """
    if _KEY_PATTERN.fullmatch(key) is None:
        raise AttributeValidationError(
            "Key must start with a lowercase letter and use only a-z, 0-9 and _"
        )
    _check_definition(
        label=label,
        applies_to=applies_to,
        data_type=data_type,
        enum_options=enum_options,
        validation=validation,
    )
    _require_known_function(session, function_id)

    attribute = Attribute(
        key=key,
        label=label.strip(),
        applies_to=applies_to,
        data_type=data_type,
        unit=unit,
        enum_options=enum_options,
        validation=validation,
        function_id=function_id,
        active=True,
    )
    session.add(attribute)
    session.flush()
    record_audit(
        session,
        action="attribute.create",
        resource_type="attribute",
        resource_id=attribute.id,
        summary=f"Attribute {attribute.id} ('{key}') created",
        actor_membership_id=actor_membership_id,
        diff={"after": {"key": key, "applies_to": applies_to.value, **_snapshot(attribute)}},
    )
    return attribute


def _require_safe_for_stored_values(
    session: Session,
    *,
    attribute: Attribute,
    new_data_type: AttributeDataType,
    new_enum_options: Sequence[str] | None,
) -> None:
    """Refuse an edit that would strand values already stored against `attribute`.

    Values sit in a column chosen by `data_type`, so that can't change once any
    exist. A removed enum option is only a problem if a value still holds it.
    Changing `validation` is always allowed: it applies to new writes only.
    """
    if new_data_type != attribute.data_type and attribute_ids_in_use(session, {attribute.id}):
        raise AttributeValidationError(
            "The data type can't change once values have been recorded. "
            "Retire this attribute and add a new one instead."
        )

    removed = set(attribute.enum_options or []) - set(new_enum_options or [])
    if not removed:
        return
    still_used = session.execute(
        select(AttributeValue.value_text)
        .where(AttributeValue.attribute_id == attribute.id, AttributeValue.value_text.in_(removed))
        .distinct()
    ).scalars()
    in_use = sorted(value for value in still_used if value is not None)
    if in_use:
        raise AttributeValidationError(f"Still in use, can't remove: {', '.join(in_use)}")


def update_attribute(
    session: Session,
    *,
    attribute_id: int,
    changes: Mapping[str, Any],
    actor_membership_id: int | None = None,
) -> Attribute:
    """Apply `changes` (only the `_EDITABLE_FIELDS` being edited) and audit-log
    the fields that really changed. A change that alters nothing logs nothing.

    The result is checked as a whole, so changing `data_type` and `validation`
    together works. Raises `AttributeValidationError` if the attribute is
    missing, the result is unusable, or stored values would be stranded.
    """
    attribute = session.get(Attribute, attribute_id)
    if attribute is None:
        raise AttributeValidationError(f"Attribute {attribute_id} not found")

    label: str = changes.get("label", attribute.label).strip()
    data_type: AttributeDataType = changes.get("data_type", attribute.data_type)
    unit: str | None = changes.get("unit", attribute.unit)
    enum_options: list[str] | None = changes.get("enum_options", attribute.enum_options)
    validation: dict[str, object] | None = changes.get("validation", attribute.validation)
    function_id: int | None = changes.get("function_id", attribute.function_id)

    _check_definition(
        label=label,
        applies_to=attribute.applies_to,
        data_type=data_type,
        enum_options=enum_options,
        validation=validation,
    )
    if function_id != attribute.function_id:
        _require_known_function(session, function_id)
    _require_safe_for_stored_values(
        session,
        attribute=attribute,
        new_data_type=data_type,
        new_enum_options=enum_options,
    )

    before = _snapshot(attribute)
    attribute.label = label
    attribute.data_type = data_type
    attribute.unit = unit
    attribute.enum_options = enum_options
    attribute.validation = validation
    attribute.function_id = function_id
    session.flush()

    after = _snapshot(attribute)
    changed = [field for field in _EDITABLE_FIELDS if before[field] != after[field]]
    if changed:
        record_audit(
            session,
            action="attribute.edit",
            resource_type="attribute",
            resource_id=attribute.id,
            summary=f"Attribute {attribute.id} ('{attribute.key}') edited",
            actor_membership_id=actor_membership_id,
            diff={
                "before": {field: before[field] for field in changed},
                "after": {field: after[field] for field in changed},
            },
        )
    return attribute


def _set_active(
    session: Session,
    *,
    attribute_id: int,
    active: bool,
    actor_membership_id: int | None,
) -> Attribute:
    """Flip `active` and audit-log it. Already in that state: nothing to log."""
    attribute = session.get(Attribute, attribute_id)
    if attribute is None:
        raise AttributeValidationError(f"Attribute {attribute_id} not found")
    if attribute.active == active:
        return attribute

    attribute.active = active
    session.flush()
    record_audit(
        session,
        action="attribute.activate" if active else "attribute.deactivate",
        resource_type="attribute",
        resource_id=attribute.id,
        summary=(
            f"Attribute {attribute.id} ('{attribute.key}') marked "
            f"{'active' if active else 'inactive'}"
        ),
        actor_membership_id=actor_membership_id,
    )
    return attribute


def deactivate_attribute(
    session: Session,
    *,
    attribute_id: int,
    actor_membership_id: int | None = None,
) -> Attribute:
    """Retire an attribute. Stored `attribute_value` and `kpi_record` rows are
    untouched and keep counting; it just stops accepting new values.

    This is the only way to remove an attribute (spec §1.5): there is no hard delete.
    """
    return _set_active(
        session,
        attribute_id=attribute_id,
        active=False,
        actor_membership_id=actor_membership_id,
    )


def activate_attribute(
    session: Session,
    *,
    attribute_id: int,
    actor_membership_id: int | None = None,
) -> Attribute:
    """Bring a retired attribute back (undo for a mistaken deactivation)."""
    return _set_active(
        session,
        attribute_id=attribute_id,
        active=True,
        actor_membership_id=actor_membership_id,
    )
