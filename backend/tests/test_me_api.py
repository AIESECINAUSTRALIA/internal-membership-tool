"""Tests for the Profile endpoints, `/api/v1/me` (Spec §2A.9).

Covers the ticket's acceptance criteria:
- Read and write your own person-level `attribute_value` rows, validated
  against each `attribute.validation`.
- You can only ever edit your own record, never another person's.
- Name, email, membership and dates stay locked: the endpoint rejects them.
- Edits are audit-logged, without the values themselves.

Like `test_membership_api.py`, the signed-in user is a test double set through
`app.dependency_overrides`, and every row created here uses a `test` prefix,
so the tests pass on an empty CI database and a seeded local one.
"""

from collections.abc import Generator
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.main import app
from app.models.attribute import (
    Attribute,
    AttributeAppliesTo,
    AttributeDataType,
    AttributeEntityType,
    AttributeValue,
)
from app.models.membership import Membership
from app.models.org import Position
from app.models.person import Person
from app.models.privacy import AuditLog
from app.repositories.attribute import get_attribute_value, set_attribute_value

from .helpers import make_attribute, make_function, make_lc, make_membership, make_person, make_term

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class Seed:
    alice: Person
    bob: Person
    m_alice: Membership
    m_bob: Membership
    shirt: Attribute  # enum
    notes: Attribute  # text, with a regex
    year: Attribute  # number, with min/max
    birthday: Attribute  # date
    vegan: Attribute  # boolean


Fixture = tuple[TestClient, Seed]


def _member_position(session: Session) -> Position:
    """The real `member` position: permissions are looked up by position key,
    so a `test_`-prefixed position would hold no grants at all."""
    position = session.execute(
        select(Position).where(Position.key == "member")
    ).scalar_one_or_none()
    if position is None:
        position = Position(key="member", label="Member", rank=1, active=True)
        session.add(position)
        session.flush()
    return position


def _actor(person: Person, membership: Membership | None) -> CurrentActor:
    memberships = [membership] if membership else []
    return CurrentActor(person=person, active_memberships=memberships, acting_membership=membership)


@pytest.fixture
def client(db_session: Session) -> Generator[Fixture, None, None]:
    """A test client signed in as Alice. Bob is a second person, for the
    "never someone else's record" tests."""
    lc = make_lc(db_session, name="test-me-lc")
    term = make_term(
        db_session, name="test-me-term", start=date(2026, 1, 1), end=date(2026, 12, 31)
    )
    member = _member_position(db_session)
    alice = make_person(db_session, full_name="Alice Example", email="test-me-alice@aiesec.net")
    bob = make_person(db_session, full_name="Bob Example", email="test-me-bob@aiesec.net")
    m_alice = make_membership(
        db_session, person=alice, lc=lc, position=member, term=term, start=date(2026, 1, 1)
    )
    m_bob = make_membership(
        db_session, person=bob, lc=lc, position=member, term=term, start=date(2026, 1, 1)
    )

    seed = Seed(
        alice=alice,
        bob=bob,
        m_alice=m_alice,
        m_bob=m_bob,
        shirt=make_attribute(
            db_session,
            key="test_me_shirt",
            data_type=AttributeDataType.ENUM,
            enum_options=["S", "M", "L"],
        ),
        notes=make_attribute(db_session, key="test_me_notes", validation={"regex": "[a-z ]+"}),
        year=make_attribute(
            db_session,
            key="test_me_year",
            data_type=AttributeDataType.NUMBER,
            validation={"min": 1, "max": 6},
        ),
        birthday=make_attribute(
            db_session, key="test_me_birthday", data_type=AttributeDataType.DATE
        ),
        vegan=make_attribute(db_session, key="test_me_vegan", data_type=AttributeDataType.BOOLEAN),
    )

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_actor] = lambda: _actor(alice, m_alice)
    try:
        yield TestClient(app), seed
    finally:
        app.dependency_overrides.clear()


def _fields(body: dict[str, Any]) -> dict[str, Any]:
    """Custom-field values from a `Me` response, keyed by attribute key.
    Only this test's own `test_me_` fields, so seeded fields don't interfere."""
    return {
        f["key"]: f["value"]
        for f in body["person"]["customFields"]
        if f["key"].startswith("test_me_")
    }


def _value(session: Session, attribute: Attribute, person: Person) -> object | None:
    return get_attribute_value(
        session, attribute=attribute, entity_type=AttributeEntityType.PERSON, entity_id=person.id
    )


def _audit_rows(session: Session, person: Person) -> list[AuditLog]:
    return list(
        session.execute(
            select(AuditLog).where(
                AuditLog.action == "person.edit", AuditLog.resource_id == person.id
            )
        ).scalars()
    )


# ---------------------------------------------------------------------------
# Reading your own record
# ---------------------------------------------------------------------------


def test_get_me_returns_own_record(client: Fixture) -> None:
    c, seed = client
    resp = c.get("/api/v1/me")
    assert resp.status_code == 200
    body = resp.json()

    person = body["person"]
    assert person["id"] == str(seed.alice.id)
    assert (person["firstName"], person["lastName"]) == ("Alice", "Example")
    assert person["email"] == "test-me-alice@aiesec.net"
    # Nothing saved yet: every field is listed, with no value.
    assert _fields(body) == {
        "test_me_shirt": None,
        "test_me_notes": None,
        "test_me_year": None,
        "test_me_birthday": None,
        "test_me_vegan": None,
    }
    shirt = next(f for f in body["person"]["customFields"] if f["key"] == "test_me_shirt")
    assert shirt["enumOptions"] == ["S", "M", "L"]

    # Position history is Alice's only.
    assert [m["id"] for m in body["memberships"]] == [str(seed.m_alice.id)]
    assert body["memberships"][0]["position"]["key"] == "member"
    assert body["memberships"][0]["startDate"] == "2026-01-01"

    # Permissions are the server's resolved grants.
    assert {"resource": "member_record", "action": "edit", "scope": "own"} in body["permissions"]


def test_get_me_does_not_list_membership_attributes(client: Fixture, db_session: Session) -> None:
    c, _ = client
    make_attribute(db_session, key="test_me_onboarded", applies_to=AttributeAppliesTo.MEMBERSHIP)
    keys = [f["key"] for f in c.get("/api/v1/me").json()["person"]["customFields"]]
    assert "test_me_onboarded" not in keys


def test_function_scoped_field_only_for_that_function(client: Fixture, db_session: Session) -> None:
    c, _ = client
    other_function = make_function(db_session, key="test_me_fn", label="Test Fn")
    bd_only = make_attribute(db_session, key="test_me_bd_only")
    bd_only.function_id = other_function.id
    db_session.flush()

    assert "test_me_bd_only" not in _fields(c.get("/api/v1/me").json())
    resp = c.patch("/api/v1/me/custom-fields", json={"test_me_bd_only": "x"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Editing your own custom fields
# ---------------------------------------------------------------------------


def test_update_saves_every_data_type(client: Fixture, db_session: Session) -> None:
    c, seed = client
    resp = c.patch(
        "/api/v1/me/custom-fields",
        json={
            "test_me_shirt": "M",
            "test_me_notes": "loves hiking",
            "test_me_year": 2,
            "test_me_birthday": "2004-03-09",
            "test_me_vegan": True,
        },
    )
    assert resp.status_code == 200
    assert _fields(resp.json()) == {
        "test_me_shirt": "M",
        "test_me_notes": "loves hiking",
        "test_me_year": 2,
        "test_me_birthday": "2004-03-09",
        "test_me_vegan": True,
    }
    # And it really is in the database, recorded by Alice's membership.
    assert _value(db_session, seed.birthday, seed.alice) == date(2004, 3, 9)
    row = db_session.execute(
        select(AttributeValue).where(
            AttributeValue.attribute_id == seed.shirt.id,
            AttributeValue.entity_id == seed.alice.id,
        )
    ).scalar_one()
    assert row.recorded_by == seed.m_alice.id


def test_update_with_null_clears_a_field(client: Fixture, db_session: Session) -> None:
    c, seed = client
    c.patch("/api/v1/me/custom-fields", json={"test_me_shirt": "L"})
    resp = c.patch("/api/v1/me/custom-fields", json={"test_me_shirt": None})
    assert resp.status_code == 200
    assert _fields(resp.json())["test_me_shirt"] is None
    assert _value(db_session, seed.shirt, seed.alice) is None


def test_fields_left_out_are_untouched(client: Fixture) -> None:
    c, _ = client
    c.patch("/api/v1/me/custom-fields", json={"test_me_shirt": "S"})
    resp = c.patch("/api/v1/me/custom-fields", json={"test_me_vegan": False})
    assert _fields(resp.json())["test_me_shirt"] == "S"


@pytest.mark.parametrize(
    "body",
    [
        {"test_me_shirt": "XXXL"},  # not one of enum_options
        {"test_me_notes": "Has Capitals 123"},  # fails the regex
        {"test_me_year": 9},  # above max
        {"test_me_year": "two"},  # wrong type
        {"test_me_birthday": "09/03/2004"},  # not YYYY-MM-DD
        {"test_me_vegan": "yes"},  # wrong type
    ],
)
def test_invalid_value_is_rejected(
    client: Fixture, db_session: Session, body: dict[str, Any]
) -> None:
    c, seed = client
    resp = c.patch("/api/v1/me/custom-fields", json=body)
    assert resp.status_code == 422
    assert _audit_rows(db_session, seed.alice) == []


def test_one_bad_field_saves_nothing(client: Fixture, db_session: Session) -> None:
    c, seed = client
    resp = c.patch("/api/v1/me/custom-fields", json={"test_me_shirt": "M", "test_me_year": 99})
    assert resp.status_code == 422
    assert _value(db_session, seed.shirt, seed.alice) is None
    assert _audit_rows(db_session, seed.alice) == []


def test_required_field_cannot_be_cleared(client: Fixture, db_session: Session) -> None:
    c, _ = client
    make_attribute(db_session, key="test_me_required", validation={"required": True})
    resp = c.patch("/api/v1/me/custom-fields", json={"test_me_required": None})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Only your own record
# ---------------------------------------------------------------------------


def test_cannot_edit_someone_elses_record(client: Fixture, db_session: Session) -> None:
    c, seed = client
    set_attribute_value(
        db_session,
        attribute=seed.shirt,
        entity_type=AttributeEntityType.PERSON,
        entity_id=seed.bob.id,
        raw_value="S",
        recorded_by_membership_id=seed.m_bob.id,
    )

    # Alice saves her own shirt size: Bob's is untouched.
    assert c.patch("/api/v1/me/custom-fields", json={"test_me_shirt": "L"}).status_code == 200
    assert _value(db_session, seed.shirt, seed.alice) == "L"
    assert _value(db_session, seed.shirt, seed.bob) == "S"

    # There is no way to name another person: an id in the body is just an unknown field.
    for body in (
        {"person_id": seed.bob.id, "test_me_shirt": "M"},
        {"entity_id": seed.bob.id, "test_me_shirt": "M"},
        {"id": str(seed.bob.id), "test_me_shirt": "M"},
    ):
        assert c.patch("/api/v1/me/custom-fields", json=body).status_code == 422
    assert _value(db_session, seed.shirt, seed.bob) == "S"
    assert _value(db_session, seed.shirt, seed.alice) == "L"


def test_get_me_never_shows_someone_elses_values(client: Fixture, db_session: Session) -> None:
    c, seed = client
    set_attribute_value(
        db_session,
        attribute=seed.notes,
        entity_type=AttributeEntityType.PERSON,
        entity_id=seed.bob.id,
        raw_value="bobs notes",
        recorded_by_membership_id=seed.m_bob.id,
    )
    assert _fields(c.get("/api/v1/me").json())["test_me_notes"] is None


# ---------------------------------------------------------------------------
# Locked fields (§2A.9)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key, value",
    [
        ("full_name", "New Name"),
        ("firstName", "New"),
        ("lastName", "Name"),
        ("aiesec_email", "someone-else@aiesec.net"),
        ("email", "someone-else@aiesec.net"),
        ("position_id", 1),
        ("function_id", 1),
        ("lc_id", 1),
        ("start_date", "2020-01-01"),
        ("end_date", "2030-01-01"),
        ("join_date", "2020-01-01"),
        ("status", "ALUMNUS"),
    ],
)
def test_locked_fields_are_rejected(
    client: Fixture, db_session: Session, key: str, value: object
) -> None:
    c, seed = client
    resp = c.patch("/api/v1/me/custom-fields", json={key: value, "test_me_shirt": "M"})
    assert resp.status_code == 422
    assert key in resp.json()["detail"]

    db_session.refresh(seed.alice)
    db_session.refresh(seed.m_alice)
    assert seed.alice.full_name == "Alice Example"
    assert seed.alice.aiesec_email == "test-me-alice@aiesec.net"
    assert seed.m_alice.start_date == date(2026, 1, 1)
    # The valid field in the same request was not saved either.
    assert _value(db_session, seed.shirt, seed.alice) is None
    assert _audit_rows(db_session, seed.alice) == []


def test_membership_and_inactive_attributes_are_rejected(
    client: Fixture, db_session: Session
) -> None:
    c, _ = client
    make_attribute(db_session, key="test_me_onboarded", applies_to=AttributeAppliesTo.MEMBERSHIP)
    retired = make_attribute(db_session, key="test_me_retired")
    retired.active = False
    db_session.flush()

    for key in ("test_me_onboarded", "test_me_retired"):
        assert c.patch("/api/v1/me/custom-fields", json={key: "x"}).status_code == 422


# ---------------------------------------------------------------------------
# Audit log (§8.4)
# ---------------------------------------------------------------------------


def test_edit_is_audit_logged_without_values(client: Fixture, db_session: Session) -> None:
    c, seed = client
    c.patch(
        "/api/v1/me/custom-fields",
        json={"test_me_shirt": "M", "test_me_notes": "very private"},
    )

    [entry] = _audit_rows(db_session, seed.alice)
    assert entry.resource_type == "person"
    assert entry.actor_membership_id == seed.m_alice.id
    assert entry.diff == {"changed_keys": ["test_me_shirt", "test_me_notes"]}
    # Values are personal data and never reach the (permanent) log.
    assert "very private" not in entry.summary
    assert "Alice" not in entry.summary


def test_saving_unchanged_values_writes_no_audit_entry(
    client: Fixture, db_session: Session
) -> None:
    c, seed = client
    c.patch("/api/v1/me/custom-fields", json={"test_me_shirt": "M"})
    c.patch("/api/v1/me/custom-fields", json={"test_me_shirt": "M", "test_me_year": None})
    assert len(_audit_rows(db_session, seed.alice)) == 1


# ---------------------------------------------------------------------------
# Who may call it
# ---------------------------------------------------------------------------


def test_signed_out_gets_401(client: Fixture, monkeypatch: pytest.MonkeyPatch) -> None:
    c, _ = client
    del app.dependency_overrides[get_current_actor]
    monkeypatch.delenv("DEV_ACTOR_HEADER_ENABLED", raising=False)
    assert c.get("/api/v1/me").status_code == 401
    assert c.patch("/api/v1/me/custom-fields", json={}).status_code == 401


def test_unallocated_person_cannot_edit(client: Fixture, db_session: Session) -> None:
    c, seed = client
    app.dependency_overrides[get_current_actor] = lambda: _actor(seed.alice, None)
    resp = c.patch("/api/v1/me/custom-fields", json={"test_me_shirt": "M"})
    assert resp.status_code == 403
    count = db_session.execute(
        select(func.count())
        .select_from(AttributeValue)
        .where(AttributeValue.entity_id == seed.alice.id)
    ).scalar_one()
    assert count == 0
