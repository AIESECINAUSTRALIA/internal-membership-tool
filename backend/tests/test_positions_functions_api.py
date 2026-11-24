"""Tests for the positions & functions endpoints (spec §1.5, §2A.2, DEV-0049).

Authentication is replaced with test-double actors, as in `test_lc_api.py`.
Error-path tests only check the response: the endpoint rolls back on an error,
which also discards the fixture's own rows.

Ranks follow spec §2: a higher number is a higher position (MCD 5, MCP 7). The
admin position is 8.
"""

from collections.abc import Generator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.main import app
from app.models.org import LC, LCType, Position
from app.models.privacy import AuditLog
from tests.helpers import (
    api_client_options,
    make_function,
    make_lc,
    make_membership,
    make_person,
    make_position,
    make_term,
)


def _get_or_create_position(session: Session, *, key: str, rank: int) -> Position:
    """The seeded position with this key if there is one, else a new one."""
    position = session.execute(select(Position).where(Position.key == key)).scalar_one_or_none()
    if position is None:
        position = Position(key=key, label=f"Test {key}", rank=rank, active=True)
        session.add(position)
    session.flush()
    return position


@dataclass
class PositionsApiFixture:
    client: TestClient
    session: Session
    actors: dict[str, CurrentActor]
    positions: dict[str, Position]


def _actor(session: Session, *, lc: LC, position: Position) -> CurrentActor:
    email = f"test-{position.key}-pf@aiesec.net"
    person = make_person(session, email=email)
    term = make_term(session, name=f"test-term-{email}")
    membership = make_membership(session, person=person, lc=lc, position=position, term=term)
    return CurrentActor(
        person=person, active_memberships=[membership], acting_membership=membership
    )


@pytest.fixture
def pf_api(db_session: Session) -> Generator[PositionsApiFixture, None, None]:
    mc = make_lc(db_session, name="test-mc", lc_type=LCType.MC)
    usyd = make_lc(db_session, name="test-usyd-lc")

    positions = {
        "mcp": _get_or_create_position(db_session, key="mcp", rank=7),
        "mcd": _get_or_create_position(db_session, key="mcd", rank=5),
        "admin": _get_or_create_position(db_session, key="admin", rank=8),
        "lcp": _get_or_create_position(db_session, key="lcp", rank=4),
    }
    actors = {
        "mcp": _actor(db_session, lc=mc, position=positions["mcp"]),
        "mcd": _actor(db_session, lc=mc, position=positions["mcd"]),
        "admin": _actor(db_session, lc=mc, position=positions["admin"]),
        "lcp": _actor(db_session, lc=usyd, position=positions["lcp"]),
        "nobody": CurrentActor(
            person=make_person(db_session, email="test-nobody-pf@aiesec.net"),
            active_memberships=[],
            acting_membership=None,
        ),
    }

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_actor] = lambda: actors["mcp"]

    with TestClient(app, **api_client_options()) as client:
        yield PositionsApiFixture(client, db_session, actors, positions)

    app.dependency_overrides.clear()


def _act_as(name: str, fixture: PositionsApiFixture) -> None:
    app.dependency_overrides[get_current_actor] = lambda: fixture.actors[name]


NEW_POSITION = {"label": "Test Coordinator", "level": "lc", "rank": 2}


def _audit_actions(session: Session, resource_type: str, resource_id: int) -> list[str]:
    rows = session.execute(
        select(AuditLog)
        .where(AuditLog.resource_type == resource_type, AuditLog.resource_id == resource_id)
        .order_by(AuditLog.id)
    ).scalars()
    return [row.action for row in rows]


# ---------------------------------------------------------------------------
# Who may manage positions and functions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("actor_name", ["lcp", "nobody"])
def test_only_managers_can_create_positions(pf_api: PositionsApiFixture, actor_name: str) -> None:
    _act_as(actor_name, pf_api)

    response = pf_api.client.post("/api/v1/positions", json=NEW_POSITION)

    assert response.status_code == 403


@pytest.mark.parametrize("actor_name", ["lcp", "nobody"])
def test_only_managers_can_create_functions(pf_api: PositionsApiFixture, actor_name: str) -> None:
    _act_as(actor_name, pf_api)

    response = pf_api.client.post("/api/v1/functions", json={"label": "Test Fn"})

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# The hierarchy rule: only positions ranked below your own (spec §3.4)
# ---------------------------------------------------------------------------


def test_mcd_cannot_rename_mcp(pf_api: PositionsApiFixture) -> None:
    _act_as("mcd", pf_api)
    mcp = pf_api.positions["mcp"]

    response = pf_api.client.patch(f"/api/v1/positions/{mcp.id}", json={"label": "Test Boss"})

    assert response.status_code == 403


def test_mcd_cannot_rename_mcp_even_when_its_rank_is_not_stored(
    pf_api: PositionsApiFixture,
) -> None:
    # An MCP row with no rank still ranks 7 for permissions (key fallback), so the
    # edit rule must use that same effective rank, not treat it as "below everyone".
    mcp = pf_api.positions["mcp"]
    mcp.rank = None
    pf_api.session.flush()
    _act_as("mcd", pf_api)

    response = pf_api.client.patch(f"/api/v1/positions/{mcp.id}", json={"rank": 1})

    assert response.status_code == 403


def test_mcd_cannot_lift_a_position_to_their_own_rank(pf_api: PositionsApiFixture) -> None:
    _act_as("mcd", pf_api)
    lower = make_position(pf_api.session, key="test_lower", label="Test Lower", rank=2)

    response = pf_api.client.patch(f"/api/v1/positions/{lower.id}", json={"rank": 5})

    assert response.status_code == 403


def test_mcd_cannot_create_position_at_own_rank(pf_api: PositionsApiFixture) -> None:
    _act_as("mcd", pf_api)

    response = pf_api.client.post("/api/v1/positions", json={**NEW_POSITION, "rank": 5})

    assert response.status_code == 403


def test_mcd_can_create_position_below_own_rank(pf_api: PositionsApiFixture) -> None:
    _act_as("mcd", pf_api)

    response = pf_api.client.post("/api/v1/positions", json=NEW_POSITION)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["label"] == "Test Coordinator"
    assert body["key"] == "test_coordinator"
    assert body["level"] == "lc"
    assert body["rank"] == 2
    assert body["can_add_same_rank"] is False
    assert body["active"] is True
    assert _audit_actions(pf_api.session, "position", body["id"]) == ["position.create"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["level", "rank"])
def test_create_position_requires_level_and_rank(pf_api: PositionsApiFixture, missing: str) -> None:
    body = {k: v for k, v in NEW_POSITION.items() if k != missing}

    response = pf_api.client.post("/api/v1/positions", json=body)

    assert response.status_code == 422


def test_unknown_level_is_rejected(pf_api: PositionsApiFixture) -> None:
    response = pf_api.client.post("/api/v1/positions", json={**NEW_POSITION, "level": "xx"})

    assert response.status_code == 422


@pytest.mark.parametrize("path", ["/api/v1/positions", "/api/v1/functions"])
def test_whitespace_label_is_rejected(pf_api: PositionsApiFixture, path: str) -> None:
    response = pf_api.client.post(path, json={**NEW_POSITION, "label": "   "})

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["level", "rank"])
def test_level_and_rank_cannot_be_cleared(pf_api: PositionsApiFixture, field: str) -> None:
    position = make_position(pf_api.session, key="test_clear", label="Test Clear", rank=2)

    response = pf_api.client.patch(f"/api/v1/positions/{position.id}", json={field: None})

    assert response.status_code == 422


def test_duplicate_position_label_ignoring_case_is_409(pf_api: PositionsApiFixture) -> None:
    make_position(pf_api.session, key="test_taken", label="Test Taken", rank=2)

    response = pf_api.client.post("/api/v1/positions", json={**NEW_POSITION, "label": "test TAKEN"})

    assert response.status_code == 409
    assert response.json()["detail"] == "A position with that name already exists"


def test_renaming_position_to_a_taken_label_is_409(pf_api: PositionsApiFixture) -> None:
    make_position(pf_api.session, key="test_taken", label="Test Taken", rank=2)
    other = make_position(pf_api.session, key="test_other", label="Test Other", rank=2)

    response = pf_api.client.patch(f"/api/v1/positions/{other.id}", json={"label": "TEST taken"})

    assert response.status_code == 409


def test_duplicate_function_label_ignoring_case_is_409(pf_api: PositionsApiFixture) -> None:
    make_function(pf_api.session, key="test_taken_fn", label="Test Taken Fn")

    response = pf_api.client.post("/api/v1/functions", json={"label": "test taken FN"})

    assert response.status_code == 409
    assert response.json()["detail"] == "A function with that name already exists"


def test_renaming_function_to_a_taken_label_is_409(pf_api: PositionsApiFixture) -> None:
    make_function(pf_api.session, key="test_taken_fn", label="Test Taken Fn")
    other = make_function(pf_api.session, key="test_other_fn", label="Test Other Fn")

    response = pf_api.client.patch(f"/api/v1/functions/{other.id}", json={"label": "TEST TAKEN FN"})

    assert response.status_code == 409


@pytest.mark.parametrize("path", ["/api/v1/positions/999999", "/api/v1/functions/999999"])
def test_unknown_id_is_404(pf_api: PositionsApiFixture, path: str) -> None:
    response = pf_api.client.patch(path, json={"label": "Test Anything"})

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Partial updates and the audit trail
# ---------------------------------------------------------------------------


def test_patch_only_label_leaves_other_fields_alone(pf_api: PositionsApiFixture) -> None:
    position = make_position(pf_api.session, key="test_partial", label="Test Partial", rank=2)

    response = pf_api.client.patch(
        f"/api/v1/positions/{position.id}", json={"label": "Test Renamed"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["label"] == "Test Renamed"
    assert response.json()["rank"] == 2
    assert _audit_actions(pf_api.session, "position", position.id) == ["position.rename"]


def test_editing_details_is_audited_as_edit(pf_api: PositionsApiFixture) -> None:
    position = make_position(pf_api.session, key="test_details", label="Test Details", rank=2)

    response = pf_api.client.patch(
        f"/api/v1/positions/{position.id}",
        json={"rank": 3, "level": "lc", "can_add_same_rank": True},
    )

    assert response.status_code == 200, response.text
    assert response.json()["rank"] == 3
    assert response.json()["can_add_same_rank"] is True
    assert _audit_actions(pf_api.session, "position", position.id) == ["position.edit"]


def test_rename_and_deactivate_in_one_patch_writes_two_audit_rows(
    pf_api: PositionsApiFixture,
) -> None:
    position = make_position(pf_api.session, key="test_both", label="Test Both", rank=2)

    response = pf_api.client.patch(
        f"/api/v1/positions/{position.id}", json={"label": "Test Both Renamed", "active": False}
    )

    assert response.status_code == 200, response.text
    assert response.json()["active"] is False
    assert _audit_actions(pf_api.session, "position", position.id) == [
        "position.rename",
        "position.deactivate",
    ]


def test_function_deactivate_and_activate_are_audited(pf_api: PositionsApiFixture) -> None:
    function = make_function(pf_api.session, key="test_toggle_fn", label="Test Toggle Fn")

    pf_api.client.patch(f"/api/v1/functions/{function.id}", json={"active": False})
    response = pf_api.client.patch(f"/api/v1/functions/{function.id}", json={"active": True})

    assert response.status_code == 200, response.text
    assert _audit_actions(pf_api.session, "function", function.id) == [
        "function.deactivate",
        "function.activate",
    ]


# ---------------------------------------------------------------------------
# Lockout protection (docs/admin-lockout-recovery.md)
# ---------------------------------------------------------------------------


def test_positions_that_give_admin_access_cannot_be_deactivated(
    pf_api: PositionsApiFixture,
) -> None:
    _act_as("admin", pf_api)
    mcd = pf_api.positions["mcd"]

    response = pf_api.client.patch(f"/api/v1/positions/{mcd.id}", json={"active": False})

    assert response.status_code == 400
    assert "admin access" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def test_list_positions_highest_rank_first(pf_api: PositionsApiFixture) -> None:
    response = pf_api.client.get("/api/v1/positions", params={"include_inactive": True})

    ranks = [row["rank"] for row in response.json() if row["rank"] is not None]
    assert ranks == sorted(ranks, reverse=True)


def test_list_functions_alphabetical_ignoring_case(pf_api: PositionsApiFixture) -> None:
    make_function(pf_api.session, key="test_zz_fn", label="Test ZZ")
    make_function(pf_api.session, key="test_mm_fn", label="test mm")
    make_function(pf_api.session, key="test_aa_fn", label="Test AA")

    response = pf_api.client.get("/api/v1/functions")

    labels = [row["label"] for row in response.json() if row["label"].lower().startswith("test ")]
    assert labels == ["Test AA", "test mm", "Test ZZ"]
