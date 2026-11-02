"""The signed-in person's own record: the Profile page (Spec §2A.9).

Two jobs:

- `build_me` assembles the `Me` payload (frontend/src/api/types.ts): identity,
  person-level custom fields, position history and resolved permissions.
- `update_own_custom_fields` writes the person's own custom fields.

Every function here takes the person from the signed-in actor and never from
the request, so these functions cannot read or write anyone else's record.
Only person-level custom fields (`attribute.applies_to = 'person'`, §4.2) are
editable. Name, email, membership and dates are locked: an admin changes those
on the Admin console (§2A.2).
"""

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.permissions import MembershipContext, resolve_all_grants
from app.models.attribute import (
    Attribute,
    AttributeAppliesTo,
    AttributeDataType,
    AttributeEntityType,
    AttributeValue,
)
from app.models.membership import Membership, Team, TeamMember
from app.models.org import LC, Function, Position
from app.models.person import Person
from app.repositories.attribute import (
    AttributeValidationError,
    set_attribute_value,
    stored_value,
    validate_and_coerce,
)
from app.repositories.membership import person_name_parts, position_payload


class UnknownCustomFieldError(ValueError):
    """Raised when an update names a key that isn't an editable person-level
    custom field. This is what rejects attempts to change locked fields such
    as `full_name` or `aiesec_email`: they are not in the attribute catalog."""

    def __init__(self, keys: Sequence[str]) -> None:
        self.keys = sorted(keys)
        super().__init__(f"These fields can't be edited here: {', '.join(self.keys)}")


# ---------------------------------------------------------------------------
# Custom fields
# ---------------------------------------------------------------------------


def list_editable_attributes(
    session: Session, active_memberships: Sequence[Membership]
) -> Sequence[Attribute]:
    """Person-level custom fields this person sees on Profile, in catalog order.

    An attribute with a `function_id` only applies to people currently in that
    function (§4.2). Inactive attributes are hidden but their values are kept.
    """
    function_ids = {m.function_id for m in active_memberships if m.function_id is not None}
    stmt = (
        select(Attribute)
        .where(
            Attribute.applies_to == AttributeAppliesTo.PERSON,
            Attribute.active.is_(True),
            or_(Attribute.function_id.is_(None), Attribute.function_id.in_(function_ids)),
        )
        .order_by(Attribute.id)
    )
    return session.execute(stmt).scalars().all()


def _values_by_attribute(session: Session, person_id: int) -> dict[int, AttributeValue]:
    """This person's `attribute_value` rows, keyed by attribute id."""
    rows = session.execute(
        select(AttributeValue).where(
            AttributeValue.entity_type == AttributeEntityType.PERSON,
            AttributeValue.entity_id == person_id,
        )
    ).scalars()
    return {row.attribute_id: row for row in rows}


def _to_json_value(value: object | None) -> object | None:
    """JSON has no date type: send dates as "YYYY-MM-DD", like the frontend's `IsoDate`."""
    return value.isoformat() if isinstance(value, date) else value


def _from_json_value(attribute: Attribute, raw_value: object) -> object:
    """The reverse of `_to_json_value`: DATE fields arrive as "YYYY-MM-DD"
    strings, but `validate_and_coerce` expects a `date`."""
    if attribute.data_type == AttributeDataType.DATE and isinstance(raw_value, str):
        try:
            return date.fromisoformat(raw_value)
        except ValueError as exc:
            raise AttributeValidationError(
                f"{attribute.key}: {raw_value!r} is not a date (expected YYYY-MM-DD)"
            ) from exc
    return raw_value


def get_custom_fields(
    session: Session, person_id: int, active_memberships: Sequence[Membership]
) -> list[dict[str, Any]]:
    """The `CustomField[]` list for Profile: each editable field and its value
    (None when nothing has been saved yet)."""
    values = _values_by_attribute(session, person_id)
    fields: list[dict[str, Any]] = []
    for attribute in list_editable_attributes(session, active_memberships):
        row = values.get(attribute.id)
        field: dict[str, Any] = {
            "key": attribute.key,
            "label": attribute.label,
            "dataType": attribute.data_type.value,
            "value": _to_json_value(stored_value(row)) if row else None,
        }
        if attribute.data_type == AttributeDataType.ENUM:
            field["enumOptions"] = attribute.enum_options or []
        fields.append(field)
    return fields


def update_own_custom_fields(
    session: Session,
    *,
    person: Person,
    active_memberships: Sequence[Membership],
    acting_membership: Membership,
    values: Mapping[str, object],
) -> list[str]:
    """Save the signed-in person's own custom fields. Returns the keys that changed.

    All or nothing: every key is checked before anything is written, so one bad
    field saves nothing. Keys that aren't editable raise
    `UnknownCustomFieldError`; values that fail `attribute.validation` raise
    `AttributeValidationError`. Fields left out of `values` are untouched, and
    None clears a field.

    Unchanged fields are not rewritten, so `recorded_at` keeps meaning "when
    this value was last changed". When something did change, one audit entry
    is added (§8.4). It lists the changed keys but **not their values**: custom
    fields are personal data, and audit entries can never be edited or deleted.

    Does not commit. The caller commits, so the values and the audit entry are
    saved together or not at all.
    """
    attributes = {a.key: a for a in list_editable_attributes(session, active_memberships)}
    unknown = [key for key in values if key not in attributes]
    if unknown:
        raise UnknownCustomFieldError(unknown)

    existing = _values_by_attribute(session, person.id)

    # Check every field first, so a failure part-way through writes nothing.
    to_write: list[tuple[Attribute, object]] = []
    for key, raw_value in values.items():
        attribute = attributes[key]
        value = None if raw_value is None else _from_json_value(attribute, raw_value)
        columns = validate_and_coerce(attribute, value)
        new_value = next((v for v in columns.values() if v is not None), None)
        row = existing.get(attribute.id)
        old_value = stored_value(row) if row else None
        if new_value != old_value:
            to_write.append((attribute, value))

    for attribute, value in to_write:
        set_attribute_value(
            session,
            attribute=attribute,
            entity_type=AttributeEntityType.PERSON,
            entity_id=person.id,
            raw_value=value,
            recorded_by_membership_id=acting_membership.id,
        )

    changed_keys = [attribute.key for attribute, _ in to_write]
    if changed_keys:
        record_audit(
            session,
            action="person.edit",
            resource_type="person",
            resource_id=person.id,
            summary=f"Person {person.id} edited their own custom fields: {', '.join(changed_keys)}",
            actor_membership_id=acting_membership.id,
            actor_person_id=person.id,
            diff={"changed_keys": changed_keys},
        )
    return changed_keys


# ---------------------------------------------------------------------------
# Me
# ---------------------------------------------------------------------------


def _membership_history(session: Session, person_id: int) -> list[dict[str, Any]]:
    """Every membership this person has held (past, current and future), newest
    first, in the `MembershipView` shape. Filtered by `person_id`, so it can never
    include anyone else's (§2A.9)."""
    memberships = (
        session.execute(
            select(Membership)
            .where(Membership.person_id == person_id)
            .order_by(Membership.start_date.desc(), Membership.id.desc())
        )
        .scalars()
        .all()
    )

    today = date.today()
    current_teams = {
        tm.membership_id: tm.team_id
        for tm in session.execute(
            select(TeamMember).where(
                TeamMember.membership_id.in_([m.id for m in memberships]),
                TeamMember.start_date <= today,
                or_(TeamMember.end_date.is_(None), TeamMember.end_date >= today),
            )
        ).scalars()
    }

    history: list[dict[str, Any]] = []
    for m in memberships:
        lc = session.get(LC, m.lc_id)
        pos = session.get(Position, m.position_id)
        func = session.get(Function, m.function_id) if m.function_id else None
        team_id = current_teams.get(m.id)
        team = session.get(Team, team_id) if team_id else None
        history.append(
            {
                "id": str(m.id),
                "position": position_payload(pos, lc),
                "function": {"key": func.key, "label": func.label} if func else None,
                "lc": {
                    "id": str(m.lc_id),
                    "name": lc.name if lc else "",
                    "type": lc.type.value.lower() if lc else "lc",
                    "state": lc.state if lc else None,
                    "active": lc.active if lc else False,
                },
                "team": {"id": str(team.id), "name": team.name} if team else None,
                "startDate": m.start_date.isoformat(),
                "endDate": m.end_date.isoformat() if m.end_date else None,
            }
        )
    return history


def build_me(
    session: Session,
    *,
    person: Person,
    active_memberships: Sequence[Membership],
    contexts: Sequence[MembershipContext],
) -> dict[str, Any]:
    """The `Me` payload for the signed-in person (§2A.9).

    `contexts` are the person's active memberships as `MembershipContext`s;
    permissions are resolved from them exactly as the server enforces them (§3.2).
    """
    first_name, last_name = person_name_parts(person)
    return {
        "person": {
            "id": str(person.id),
            "firstName": first_name,
            "lastName": last_name,
            "email": person.aiesec_email,
            "customFields": get_custom_fields(session, person.id, active_memberships),
        },
        "memberships": _membership_history(session, person.id),
        "permissions": [
            {"resource": resource, "action": action, "scope": scope}
            for resource, action, scope in resolve_all_grants(contexts)
        ],
    }
