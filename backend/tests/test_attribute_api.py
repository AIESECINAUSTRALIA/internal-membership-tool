"""Tests for the attribute catalog endpoints: KPIs and custom fields (spec §1.5, §4.2).

Authentication is replaced with test-double actors, as in `test_lc_api.py`.
Error-path tests only check the response: the endpoint rolls back on an error,
which also discards the fixture's own rows.
"""

from collections.abc import Generator
from dataclasses import dataclass
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.main import app
from app.models.attribute import (
    Attribute,
    AttributeAppliesTo,
    AttributeDataType,
    AttributeEntityType,
)
from app.models.kpi import KpiRecord, KpiSource
from app.models.membership import Membership
from app.models.org import LC, Function, LCType, Position
from app.models.privacy import AuditLog
from app.repositories.attribute import set_attribute_value
from app.repositories.kpi import record_kpi, set_home_chart_default
from tests.helpers import (
    make_attribute,
    make_function,
    make_kpi_attribute,
    make_lc,
    make_membership,
    make_person,
    make_term,
)

URL = "/api/v1/attributes"


def _get_or_create_position(session: Session, *, key: str, rank: int) -> Position:
    position = session.execute(select(Position).where(Position.key == key)).scalar_one_or_none()
    if position is None:
        position = Position(key=key, label=key.upper(), rank=rank, active=True)
        session.add(position)
    session.flush()
    return position


@dataclass
class AttributeApiFixture:
    client: TestClient
    session: Session
    actors: dict[str, CurrentActor]
    mc_membership: Membership


def _actor(session: Session, *, email: str, lc: LC, position_key: str, rank: int) -> CurrentActor:
    person = make_person(session, email=email)
    position = _get_or_create_position(session, key=position_key, rank=rank)
    term = make_term(session, name=f"test-term-{email}")
    membership = make_membership(session, person=person, lc=lc, position=position, term=term)
    return CurrentActor(
        person=person, active_memberships=[membership], acting_membership=membership
    )


@pytest.fixture
def attr_api(db_session: Session) -> Generator[AttributeApiFixture, None, None]:
    mc = make_lc(db_session, name="test-mc", lc_type=LCType.MC)
    usyd = make_lc(db_session, name="test-usyd-lc")

    actors = {
        "mc": _actor(db_session, email="test-mc@aiesec.net", lc=mc, position_key="mcp", rank=7),
        "admin": _actor(
            db_session, email="test-admin@aiesec.net", lc=mc, position_key="admin", rank=8
        ),
        "lcp": _actor(db_session, email="test-lcp@aiesec.net", lc=usyd, position_key="lcp", rank=4),
        "nobody": CurrentActor(
            person=make_person(db_session, email="test-nobody-attr@aiesec.net"),
            active_memberships=[],
            acting_membership=None,
        ),
    }

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_actor] = lambda: actors["mc"]

    with TestClient(app) as client:
        mc_membership = actors["mc"].acting_membership
        assert mc_membership is not None
        yield AttributeApiFixture(client, db_session, actors, mc_membership)

    app.dependency_overrides.clear()


def _act_as(name: str, fixture: AttributeApiFixture) -> None:
    app.dependency_overrides[get_current_actor] = lambda: fixture.actors[name]


def _kpi_body(**overrides: object) -> dict[str, object]:
    return {
        "key": "test_cold_calls",
        "label": "Cold calls",
        "applies_to": "kpi",
        "data_type": "number",
        "unit": "count",
        "validation": {"required": True, "min": 0},
        **overrides,
    }


def _create(client: TestClient, **overrides: object) -> dict[str, object]:
    response = client.post(URL, json=_kpi_body(**overrides))
    assert response.status_code == 201, response.text
    created: dict[str, object] = response.json()
    return created


def _audit_rows(session: Session, action: str, attribute_id: object) -> list[AuditLog]:
    return list(
        session.execute(
            select(AuditLog).where(
                AuditLog.action == action,
                AuditLog.resource_type == "attribute",
                AuditLog.resource_id == attribute_id,
            )
        ).scalars()
    )


def _record_kpi_value(fixture: AttributeApiFixture, attribute: Attribute) -> KpiRecord:
    return record_kpi(
        fixture.session,
        attribute=attribute,
        membership_id=fixture.mc_membership.id,
        value_number=5,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        source=KpiSource.LEADER,
        recorded_by_membership_id=fixture.mc_membership.id,
    )


def _set_person_value(fixture: AttributeApiFixture, attribute: Attribute, value: object) -> None:
    set_attribute_value(
        fixture.session,
        attribute=attribute,
        entity_type=AttributeEntityType.PERSON,
        entity_id=fixture.actors["mc"].person.id,
        raw_value=value,
        recorded_by_membership_id=fixture.mc_membership.id,
    )


# ---------------------------------------------------------------------------
# Who may manage the catalog
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("actor_name", ["mc", "admin"])
def test_mc_and_admin_can_create_attribute(attr_api: AttributeApiFixture, actor_name: str) -> None:
    _act_as(actor_name, attr_api)

    created = _create(attr_api.client)

    assert created["key"] == "test_cold_calls"
    assert created["active"] is True
    assert created["in_use"] is False


@pytest.mark.parametrize("actor_name", ["lcp", "nobody"])
def test_other_actors_cannot_touch_the_catalog(
    attr_api: AttributeApiFixture, actor_name: str
) -> None:
    attribute = make_kpi_attribute(attr_api.session)
    _act_as(actor_name, attr_api)

    assert attr_api.client.get(URL).status_code == 403
    assert attr_api.client.post(URL, json=_kpi_body()).status_code == 403
    patched = attr_api.client.patch(f"{URL}/{attribute.id}", json={"label": "New"})
    assert patched.status_code == 403


def test_unauthenticated_requests_are_rejected(attr_api: AttributeApiFixture) -> None:
    del app.dependency_overrides[get_current_actor]

    assert attr_api.client.get(URL).status_code == 401


def test_there_is_no_delete_endpoint(attr_api: AttributeApiFixture) -> None:
    attribute = make_kpi_attribute(attr_api.session)

    assert attr_api.client.delete(f"{URL}/{attribute.id}").status_code == 405


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def test_list_filters_by_applies_to_and_hides_inactive_by_default(
    attr_api: AttributeApiFixture,
) -> None:
    kpi = make_kpi_attribute(attr_api.session)
    field = make_attribute(attr_api.session, key="test_person_field")
    retired = make_kpi_attribute(attr_api.session, key="test_retired_kpi")
    retired.active = False
    attr_api.session.flush()

    kpi_ids = {row["id"] for row in attr_api.client.get(URL, params={"applies_to": "kpi"}).json()}
    all_ids = {
        row["id"] for row in attr_api.client.get(URL, params={"include_inactive": True}).json()
    }

    assert kpi.id in kpi_ids
    assert field.id not in kpi_ids
    assert retired.id not in kpi_ids
    assert {kpi.id, field.id, retired.id} <= all_ids


def test_list_reports_which_attributes_are_in_use(attr_api: AttributeApiFixture) -> None:
    used = make_kpi_attribute(attr_api.session)
    unused = make_kpi_attribute(attr_api.session, key="test_unused_kpi")
    _record_kpi_value(attr_api, used)

    rows = {row["id"]: row for row in attr_api.client.get(URL).json()}

    assert rows[used.id]["in_use"] is True
    assert rows[unused.id]["in_use"] is False


# ---------------------------------------------------------------------------
# Creating
# ---------------------------------------------------------------------------


def test_create_is_audited_with_the_actor(attr_api: AttributeApiFixture) -> None:
    created = _create(attr_api.client)

    rows = _audit_rows(attr_api.session, "attribute.create", created["id"])
    assert len(rows) == 1
    assert rows[0].actor_membership_id == attr_api.mc_membership.id
    assert rows[0].diff is not None
    assert rows[0].diff["after"]["key"] == "test_cold_calls"


def test_create_custom_field_scoped_to_a_function(attr_api: AttributeApiFixture) -> None:
    function = make_function(attr_api.session)

    created = _create(
        attr_api.client,
        key="test_tshirt",
        label="T-shirt",
        applies_to="membership",
        data_type="enum",
        unit=None,
        enum_options=["S", "M"],
        validation=None,
        function_id=function.id,
    )

    assert created["applies_to"] == "membership"
    assert created["enum_options"] == ["S", "M"]
    assert created["function_id"] == function.id


def test_duplicate_key_is_a_conflict(attr_api: AttributeApiFixture) -> None:
    make_kpi_attribute(attr_api.session, key="test_taken")

    response = attr_api.client.post(URL, json=_kpi_body(key="test_taken"))

    assert response.status_code == 409


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"key": "Has Spaces"}, id="bad-key"),
        pytest.param({"label": "   "}, id="blank-label"),
        pytest.param({"data_type": "text", "validation": None}, id="non-numeric-kpi"),
        pytest.param({"function_id": 999_999}, id="unknown-function"),
        pytest.param({"validation": {"min": 5, "max": 1}}, id="min-above-max"),
        pytest.param({"validation": {"min": "low"}}, id="non-numeric-min"),
        pytest.param({"validation": {"regex": ".*"}}, id="regex-on-number"),
        pytest.param({"validation": {"mystery": 1}}, id="unknown-rule"),
        pytest.param({"validation": {"required": "yes"}}, id="non-boolean-required"),
        pytest.param({"enum_options": ["A"]}, id="options-on-non-enum"),
        pytest.param(
            {"applies_to": "person", "data_type": "text", "validation": {"regex": "("}},
            id="bad-regex",
        ),
        pytest.param(
            {"applies_to": "person", "data_type": "date", "validation": {"min": "soon"}},
            id="non-date-min",
        ),
        pytest.param(
            {"applies_to": "person", "data_type": "enum", "validation": None},
            id="enum-without-options",
        ),
        pytest.param(
            {
                "applies_to": "person",
                "data_type": "enum",
                "validation": None,
                "enum_options": ["A", "A"],
            },
            id="duplicate-options",
        ),
    ],
)
def test_create_rejects_invalid_definitions(
    attr_api: AttributeApiFixture, overrides: dict[str, object]
) -> None:
    response = attr_api.client.post(URL, json=_kpi_body(**overrides))

    assert response.status_code == 400, response.text


# ---------------------------------------------------------------------------
# Editing
# ---------------------------------------------------------------------------


def test_edit_changes_only_the_sent_fields_and_is_audited(attr_api: AttributeApiFixture) -> None:
    created = _create(attr_api.client)

    response = attr_api.client.patch(f"{URL}/{created['id']}", json={"label": "Calls"})

    assert response.status_code == 200, response.text
    assert response.json()["label"] == "Calls"
    assert response.json()["unit"] == "count"
    rows = _audit_rows(attr_api.session, "attribute.edit", created["id"])
    assert len(rows) == 1
    assert rows[0].diff == {"before": {"label": "Cold calls"}, "after": {"label": "Calls"}}


def test_edit_can_clear_unit_and_function(attr_api: AttributeApiFixture) -> None:
    function = make_function(attr_api.session)
    created = _create(attr_api.client, function_id=function.id)

    response = attr_api.client.patch(
        f"{URL}/{created['id']}", json={"unit": None, "function_id": None}
    )

    assert response.status_code == 200, response.text
    assert response.json()["unit"] is None
    assert response.json()["function_id"] is None


def test_edit_that_changes_nothing_writes_no_audit_entry(attr_api: AttributeApiFixture) -> None:
    created = _create(attr_api.client)

    attr_api.client.patch(f"{URL}/{created['id']}", json={"label": "Cold calls"})

    assert _audit_rows(attr_api.session, "attribute.edit", created["id"]) == []


@pytest.mark.parametrize("field", ["key", "applies_to"])
def test_key_and_applies_to_cannot_be_edited(attr_api: AttributeApiFixture, field: str) -> None:
    created = _create(attr_api.client)

    response = attr_api.client.patch(f"{URL}/{created['id']}", json={field: "person"})

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["label", "data_type", "active"])
def test_required_fields_cannot_be_nulled(attr_api: AttributeApiFixture, field: str) -> None:
    created = _create(attr_api.client)

    response = attr_api.client.patch(f"{URL}/{created['id']}", json={field: None})

    assert response.status_code == 422


def test_edit_unknown_attribute_is_404(attr_api: AttributeApiFixture) -> None:
    assert attr_api.client.patch(f"{URL}/999999", json={"label": "x"}).status_code == 404


def test_edit_rejects_invalid_definition(attr_api: AttributeApiFixture) -> None:
    created = _create(attr_api.client)

    response = attr_api.client.patch(
        f"{URL}/{created['id']}", json={"validation": {"min": 9, "max": 1}}
    )

    assert response.status_code == 400


def test_unused_custom_field_can_change_data_type(attr_api: AttributeApiFixture) -> None:
    created = _create(
        attr_api.client,
        key="test_field",
        applies_to="person",
        data_type="text",
        unit=None,
        validation=None,
    )

    response = attr_api.client.patch(f"{URL}/{created['id']}", json={"data_type": "number"})

    assert response.status_code == 200, response.text
    assert response.json()["data_type"] == "number"


def test_kpi_cannot_change_away_from_number(attr_api: AttributeApiFixture) -> None:
    created = _create(attr_api.client, validation=None)

    response = attr_api.client.patch(f"{URL}/{created['id']}", json={"data_type": "text"})

    assert response.status_code == 400


def test_data_type_is_locked_once_an_attribute_value_exists(
    attr_api: AttributeApiFixture,
) -> None:
    attribute = make_attribute(attr_api.session, key="test_locked")
    _set_person_value(attr_api, attribute, "hello")

    response = attr_api.client.patch(f"{URL}/{attribute.id}", json={"data_type": "number"})

    assert response.status_code == 400
    assert "data type" in response.json()["detail"].lower()


def test_data_type_is_locked_once_a_kpi_record_exists(attr_api: AttributeApiFixture) -> None:
    attribute = make_attribute(
        attr_api.session,
        key="test_locked_kpi",
        applies_to=AttributeAppliesTo.KPI,
        data_type=AttributeDataType.NUMBER,
    )
    _record_kpi_value(attr_api, attribute)

    response = attr_api.client.patch(f"{URL}/{attribute.id}", json={"data_type": "text"})

    assert response.status_code == 400


def _enum_field_holding(fixture: AttributeApiFixture, value: str) -> Attribute:
    attribute = make_attribute(
        fixture.session,
        key="test_size",
        data_type=AttributeDataType.ENUM,
        enum_options=["S", "M"],
    )
    _set_person_value(fixture, attribute, value)
    return attribute


def test_enum_option_in_use_cannot_be_removed(attr_api: AttributeApiFixture) -> None:
    attribute = _enum_field_holding(attr_api, "S")

    response = attr_api.client.patch(f"{URL}/{attribute.id}", json={"enum_options": ["M"]})

    assert response.status_code == 400
    assert "S" in response.json()["detail"]


def test_unused_enum_option_can_be_removed_and_new_ones_added(
    attr_api: AttributeApiFixture,
) -> None:
    attribute = _enum_field_holding(attr_api, "S")

    response = attr_api.client.patch(f"{URL}/{attribute.id}", json={"enum_options": ["S", "L"]})

    assert response.status_code == 200, response.text
    assert response.json()["enum_options"] == ["S", "L"]


def test_label_and_validation_stay_editable_while_in_use(attr_api: AttributeApiFixture) -> None:
    attribute = make_kpi_attribute(attr_api.session)
    _record_kpi_value(attr_api, attribute)

    response = attr_api.client.patch(
        f"{URL}/{attribute.id}", json={"label": "Renamed", "validation": {"min": 10}}
    )

    assert response.status_code == 200, response.text
    assert response.json()["validation"] == {"min": 10}


# ---------------------------------------------------------------------------
# Deactivating
# ---------------------------------------------------------------------------


def test_deactivate_then_reactivate_is_audited(attr_api: AttributeApiFixture) -> None:
    created = _create(attr_api.client)

    off = attr_api.client.patch(f"{URL}/{created['id']}", json={"active": False})
    on = attr_api.client.patch(f"{URL}/{created['id']}", json={"active": True})

    assert off.json()["active"] is False
    assert on.json()["active"] is True
    assert len(_audit_rows(attr_api.session, "attribute.deactivate", created["id"])) == 1
    assert len(_audit_rows(attr_api.session, "attribute.activate", created["id"])) == 1


def test_deactivating_twice_is_audited_once(attr_api: AttributeApiFixture) -> None:
    created = _create(attr_api.client)

    attr_api.client.patch(f"{URL}/{created['id']}", json={"active": False})
    attr_api.client.patch(f"{URL}/{created['id']}", json={"active": False})

    assert len(_audit_rows(attr_api.session, "attribute.deactivate", created["id"])) == 1


def test_deactivating_keeps_existing_values(attr_api: AttributeApiFixture) -> None:
    kpi = make_kpi_attribute(attr_api.session)
    record = _record_kpi_value(attr_api, kpi)
    field = make_attribute(attr_api.session, key="test_kept_field")
    _set_person_value(attr_api, field, "kept")

    for attribute in (kpi, field):
        response = attr_api.client.patch(f"{URL}/{attribute.id}", json={"active": False})
        assert response.status_code == 200, response.text

    attr_api.session.expire_all()
    assert attr_api.session.get(KpiRecord, record.id) is not None
    rows = {
        row["id"]: row for row in attr_api.client.get(URL, params={"include_inactive": True}).json()
    }
    assert rows[kpi.id]["in_use"] is True
    assert rows[field.id]["in_use"] is True


# ---------------------------------------------------------------------------
# Homepage defaults (home_chart_default, docs/home-chart.md)
# ---------------------------------------------------------------------------


def _default_kpi(fixture: AttributeApiFixture) -> tuple[Attribute, Function]:
    """A KPI scoped to a function and set as that function's homepage default."""
    function = make_function(fixture.session, key="test_default_fn", label="Test Default Fn")
    kpi = make_kpi_attribute(fixture.session, key="test_default_kpi", function=function)
    set_home_chart_default(fixture.session, function_id=function.id, attribute=kpi)
    return kpi, function


def test_retiring_a_homepage_default_kpi_is_refused(attr_api: AttributeApiFixture) -> None:
    kpi, _ = _default_kpi(attr_api)

    response = attr_api.client.patch(f"{URL}/{kpi.id}", json={"active": False})

    # A 400 rolls the request back, so the KPI stays active. (The rollback also
    # discards this test's own rows, so they can't be re-read here.)
    assert response.status_code == 400
    assert "Test Default Fn" in response.json()["detail"]


def test_moving_a_default_kpi_to_another_function_is_refused(
    attr_api: AttributeApiFixture,
) -> None:
    kpi, _ = _default_kpi(attr_api)
    other = make_function(attr_api.session, key="test_other_fn", label="Test Other Fn")

    response = attr_api.client.patch(f"{URL}/{kpi.id}", json={"function_id": other.id})

    assert response.status_code == 400
    assert "Test Default Fn" in response.json()["detail"]


@pytest.mark.parametrize("target", ["same", "shared"])
def test_rescoping_a_default_kpi_that_keeps_it_valid_is_allowed(
    attr_api: AttributeApiFixture, target: str
) -> None:
    """Same function, or shared by all functions: the default still works."""
    kpi, function = _default_kpi(attr_api)
    new_function_id = function.id if target == "same" else None

    response = attr_api.client.patch(f"{URL}/{kpi.id}", json={"function_id": new_function_id})

    assert response.status_code == 200, response.text


def test_editing_a_default_kpis_label_is_allowed(attr_api: AttributeApiFixture) -> None:
    kpi, _ = _default_kpi(attr_api)

    response = attr_api.client.patch(f"{URL}/{kpi.id}", json={"label": "Renamed"})

    assert response.status_code == 200, response.text
