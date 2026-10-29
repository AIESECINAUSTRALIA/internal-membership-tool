"""Tests for the LC management endpoints (spec §1.5, §2A.2).

Authentication is replaced with test-double actors, as in
`test_membership_api.py`. Error-path tests only check the response: the
endpoint rolls back on an error, which also discards the fixture's own rows.
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
from app.models.membership import Membership
from app.models.org import LC, LCType, Position
from app.models.person import Person
from app.models.privacy import AuditLog
from tests.helpers import (
    make_lc,
    make_membership,
    make_person,
    make_state_timezone,
    make_term,
)


def _get_or_create_position(session: Session, *, key: str, rank: int) -> Position:
    position = session.execute(select(Position).where(Position.key == key)).scalar_one_or_none()
    if position is None:
        position = Position(key=key, label=key.upper(), rank=rank, active=True)
        session.add(position)
    session.flush()
    return position


@dataclass
class LcApiFixture:
    client: TestClient
    session: Session
    actors: dict[str, CurrentActor]
    mc_membership: Membership


def _actor(session: Session, *, email: str, lc: LC, position_key: str, rank: int) -> CurrentActor:
    person: Person = make_person(session, email=email)
    position = _get_or_create_position(session, key=position_key, rank=rank)
    term = make_term(session, name=f"test-term-{email}")
    membership = make_membership(session, person=person, lc=lc, position=position, term=term)
    return CurrentActor(
        person=person, active_memberships=[membership], acting_membership=membership
    )


@pytest.fixture
def lc_api(db_session: Session) -> Generator[LcApiFixture, None, None]:
    mc = make_lc(db_session, name="test-mc", lc_type=LCType.MC)
    usyd = make_lc(db_session, name="test-usyd-lc")
    make_state_timezone(db_session, state="NSW", timezone="Australia/Sydney")

    actors = {
        "mc": _actor(db_session, email="test-mc@aiesec.net", lc=mc, position_key="mcp", rank=7),
        "admin": _actor(
            db_session, email="test-admin@aiesec.net", lc=mc, position_key="admin", rank=8
        ),
        "lcp": _actor(db_session, email="test-lcp@aiesec.net", lc=usyd, position_key="lcp", rank=4),
    }
    nobody = CurrentActor(
        person=make_person(db_session, email="test-nobody-lc@aiesec.net"),
        active_memberships=[],
        acting_membership=None,
    )
    actors["nobody"] = nobody

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_actor] = lambda: actors["mc"]

    with TestClient(app) as client:
        mc_membership = actors["mc"].acting_membership
        assert mc_membership is not None
        yield LcApiFixture(client, db_session, actors, mc_membership)

    app.dependency_overrides.clear()


def _act_as(name: str, fixture: LcApiFixture) -> None:
    app.dependency_overrides[get_current_actor] = lambda: fixture.actors[name]


def _create(client: TestClient, name: str, **extra: object) -> dict[str, object]:
    response = client.post("/api/v1/lcs", json={"name": name, "lc_type": "LC", **extra})
    assert response.status_code == 201, response.text
    created: dict[str, object] = response.json()
    return created


# ---------------------------------------------------------------------------
# Who may manage LCs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("actor_name", ["mc", "admin"])
def test_mc_and_admin_can_create_lc(lc_api: LcApiFixture, actor_name: str) -> None:
    _act_as(actor_name, lc_api)

    created = _create(lc_api.client, f"test-new-lc-{actor_name}", state="NSW")

    assert created["name"] == f"test-new-lc-{actor_name}"
    assert created["state"] == "NSW"
    assert created["active"] is True


@pytest.mark.parametrize("actor_name", ["lcp", "nobody"])
def test_other_actors_cannot_manage_lcs(lc_api: LcApiFixture, actor_name: str) -> None:
    target = make_lc(lc_api.session, name="test-protected-lc")
    other = make_lc(lc_api.session, name="test-protected-lc-2")
    _act_as(actor_name, lc_api)
    client = lc_api.client

    assert client.post("/api/v1/lcs", json={"name": "x", "lc_type": "LC"}).status_code == 403
    assert client.patch(f"/api/v1/lcs/{target.id}", json={"name": "y"}).status_code == 403
    merge = client.post(f"/api/v1/lcs/{target.id}/merge", json={"target_id": other.id})
    assert merge.status_code == 403


def test_unauthenticated_requests_are_rejected(lc_api: LcApiFixture) -> None:
    del app.dependency_overrides[get_current_actor]

    assert lc_api.client.get("/api/v1/lcs").status_code == 401
    assert lc_api.client.post("/api/v1/lcs", json={"name": "x", "lc_type": "LC"}).status_code == 401


def test_any_signed_in_actor_can_list_lcs_and_state_timezones(lc_api: LcApiFixture) -> None:
    _act_as("lcp", lc_api)

    listed = lc_api.client.get("/api/v1/lcs")
    timezones = lc_api.client.get("/api/v1/lcs/state-timezones")

    assert listed.status_code == 200
    assert timezones.status_code == 200
    assert {"state": "NSW", "timezone": "Australia/Sydney"} in timezones.json()


# ---------------------------------------------------------------------------
# Create / update
# ---------------------------------------------------------------------------


def test_create_lc_rejects_unknown_state(lc_api: LcApiFixture) -> None:
    response = lc_api.client.post(
        "/api/v1/lcs", json={"name": "test-bad-state", "lc_type": "LC", "state": "XX"}
    )

    assert response.status_code == 400
    assert "Unknown state" in response.json()["detail"]


def test_patch_renames_sets_state_and_is_audited_with_the_actor(lc_api: LcApiFixture) -> None:
    lc = make_lc(lc_api.session, name="test-patch-lc")

    response = lc_api.client.patch(
        f"/api/v1/lcs/{lc.id}", json={"name": "test-patched-lc", "state": "NSW"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "test-patched-lc"
    assert response.json()["state"] == "NSW"
    audits = lc_api.session.execute(
        select(AuditLog).where(AuditLog.resource_id == lc.id, AuditLog.resource_type == "lc")
    ).scalars()
    actions = {entry.action: entry.actor_membership_id for entry in audits}
    assert actions == {
        "lc.rename": lc_api.mc_membership.id,
        "lc.set_state": lc_api.mc_membership.id,
    }


def test_patch_deactivates_then_reactivates(lc_api: LcApiFixture) -> None:
    lc = make_lc(lc_api.session, name="test-toggle-lc")

    deactivated = lc_api.client.patch(f"/api/v1/lcs/{lc.id}", json={"active": False})
    assert deactivated.json()["active"] is False

    reactivated = lc_api.client.patch(f"/api/v1/lcs/{lc.id}", json={"active": True})
    assert reactivated.json()["active"] is True


def test_patch_rejects_unknown_state(lc_api: LcApiFixture) -> None:
    lc = make_lc(lc_api.session, name="test-patch-bad-state")

    response = lc_api.client.patch(f"/api/v1/lcs/{lc.id}", json={"state": "XX"})

    assert response.status_code == 400


def test_patch_unknown_lc_is_404(lc_api: LcApiFixture) -> None:
    assert lc_api.client.patch("/api/v1/lcs/999999", json={"name": "x"}).status_code == 404


def test_there_is_no_delete_endpoint(lc_api: LcApiFixture) -> None:
    lc = make_lc(lc_api.session, name="test-undeletable-lc")

    assert lc_api.client.delete(f"/api/v1/lcs/{lc.id}").status_code == 405


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


def test_merge_endpoint_reports_what_changed(lc_api: LcApiFixture) -> None:
    session = lc_api.session
    source = make_lc(session, name="test-merge-source")
    target = make_lc(session, name="test-merge-target")
    position = _get_or_create_position(session, key="member", rank=1)
    term = make_term(session, name="test-merge-term")
    person = make_person(session, email="test-merge-person@aiesec.net")
    make_membership(
        session, person=person, lc=source, position=position, term=term, start=date(2026, 1, 1)
    )

    response = lc_api.client.post(f"/api/v1/lcs/{source.id}/merge", json={"target_id": target.id})

    assert response.status_code == 200
    assert response.json() == {
        "memberships_moved": 1,
        "future_memberships_repointed": 0,
        "teams_created": 0,
        "teams_reused": 0,
        "leaders_not_carried": 0,
    }
    session.refresh(source)
    assert source.active is False


def test_merge_endpoint_unknown_lc_is_404(lc_api: LcApiFixture) -> None:
    lc = make_lc(lc_api.session, name="test-merge-known")

    missing_target = lc_api.client.post(f"/api/v1/lcs/{lc.id}/merge", json={"target_id": 999999})
    missing_source = lc_api.client.post("/api/v1/lcs/999999/merge", json={"target_id": lc.id})

    assert missing_target.status_code == 404
    assert missing_source.status_code == 404


def test_merge_endpoint_rejects_merging_into_itself(lc_api: LcApiFixture) -> None:
    lc = make_lc(lc_api.session, name="test-merge-self")

    response = lc_api.client.post(f"/api/v1/lcs/{lc.id}/merge", json={"target_id": lc.id})

    assert response.status_code == 400
