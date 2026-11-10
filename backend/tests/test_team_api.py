"""Tests for the team management endpoints (spec §1.5, §2A.2).

Authentication is replaced with test-double actors, following the same pattern
as test_lc_api.py. Error-path tests only check the response: the endpoint rolls
back on error, which also discards fixture rows.
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
from app.models.membership import Team, TeamMember
from app.models.org import LC, LCType, Position
from app.models.person import Person
from app.models.privacy import AuditLog
from tests.helpers import (
    make_function,
    make_lc,
    make_membership,
    make_person,
    make_team,
    make_term,
)

URL = "/api/v1/teams"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _get_or_create_position(session: Session, *, key: str, rank: int) -> Position:
    pos = session.execute(select(Position).where(Position.key == key)).scalar_one_or_none()
    if pos is None:
        pos = Position(key=key, label=key.upper(), rank=rank, active=True)
        session.add(pos)
    session.flush()
    return pos


def _actor(session: Session, *, email: str, lc: LC, position_key: str, rank: int) -> CurrentActor:
    person: Person = make_person(session, email=email)
    position = _get_or_create_position(session, key=position_key, rank=rank)
    term = make_term(session, name=f"term-{email}")
    membership = make_membership(session, person=person, lc=lc, position=position, term=term)
    return CurrentActor(person=person, active_memberships=[membership], acting_membership=membership)


@dataclass
class TeamApiFixture:
    client: TestClient
    session: Session
    actors: dict[str, CurrentActor]
    lc: LC
    mc: LC


@pytest.fixture
def team_api(db_session: Session) -> Generator[TeamApiFixture, None, None]:
    mc = make_lc(db_session, name="test-mc", lc_type=LCType.MC)
    lc = make_lc(db_session, name="test-usyd-lc")

    actors = {
        "mc": _actor(db_session, email="mc@aiesec.net", lc=mc, position_key="mcp", rank=7),
        "admin": _actor(db_session, email="admin@aiesec.net", lc=mc, position_key="admin", rank=8),
        "lcp": _actor(db_session, email="lcp@aiesec.net", lc=lc, position_key="lcp", rank=4),
        "lcvp": _actor(db_session, email="lcvp@aiesec.net", lc=lc, position_key="lcvp", rank=3),
        "nobody": CurrentActor(
            person=make_person(db_session, email="nobody@aiesec.net"),
            active_memberships=[],
            acting_membership=None,
        ),
    }

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_actor] = lambda: actors["mc"]

    with TestClient(app) as client:
        yield TeamApiFixture(client, db_session, actors, lc, mc)

    app.dependency_overrides.clear()


def _act_as(name: str, fixture: TeamApiFixture) -> None:
    app.dependency_overrides[get_current_actor] = lambda: fixture.actors[name]


def _create(fixture: TeamApiFixture, **overrides: object) -> dict[str, object]:
    fn = make_function(fixture.session)
    term = make_term(fixture.session, name="create-term")
    body = {"name": "Alpha Team", "function_id": fn.id, "term_id": term.id, **overrides}
    r = fixture.client.post(URL, params={"lc_id": fixture.lc.id}, json=body)
    assert r.status_code == 201, r.text
    result: dict[str, object] = r.json()
    return result


# ---------------------------------------------------------------------------
# Permission checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("actor_name", ["lcp", "mc", "admin"])
def test_managers_can_create_team(team_api: TeamApiFixture, actor_name: str) -> None:
    _act_as(actor_name, team_api)
    lc_id = team_api.lc.id if actor_name == "lcp" else team_api.mc.id
    fn = make_function(team_api.session, key=f"fn-{actor_name}")
    term = make_term(team_api.session, name=f"term-create-{actor_name}")
    r = team_api.client.post(
        URL,
        params={"lc_id": lc_id},
        json={"name": f"Team {actor_name}", "function_id": fn.id, "term_id": term.id},
    )
    assert r.status_code == 201, r.text


def test_lcvp_cannot_manage_teams(team_api: TeamApiFixture) -> None:
    _act_as("lcvp", team_api)
    fn = make_function(team_api.session, key="fn-lcvp-block")
    term = make_term(team_api.session, name="term-lcvp-block")
    r = team_api.client.post(
        URL,
        params={"lc_id": team_api.lc.id},
        json={"name": "Blocked", "function_id": fn.id, "term_id": term.id},
    )
    assert r.status_code == 403


def test_nobody_cannot_manage_teams(team_api: TeamApiFixture) -> None:
    _act_as("nobody", team_api)
    fn = make_function(team_api.session, key="fn-nobody-block")
    term = make_term(team_api.session, name="term-nobody-block")
    r = team_api.client.post(
        URL,
        params={"lc_id": team_api.lc.id},
        json={"name": "Blocked", "function_id": fn.id, "term_id": term.id},
    )
    assert r.status_code == 403


def test_lcp_cannot_manage_teams_in_other_lc(team_api: TeamApiFixture) -> None:
    """LCP scope is `lc` — they cannot manage teams in the MC's LC."""
    _act_as("lcp", team_api)
    fn = make_function(team_api.session, key="fn-lcp-other")
    term = make_term(team_api.session, name="term-lcp-other")
    r = team_api.client.post(
        URL,
        params={"lc_id": team_api.mc.id},
        json={"name": "Blocked", "function_id": fn.id, "term_id": term.id},
    )
    assert r.status_code == 403


def test_unauthenticated_requests_are_rejected(team_api: TeamApiFixture) -> None:
    del app.dependency_overrides[get_current_actor]
    r = team_api.client.get(URL, params={"lc_id": team_api.lc.id})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def test_any_signed_in_actor_can_list_teams(team_api: TeamApiFixture) -> None:
    _act_as("lcvp", team_api)
    fn = make_function(team_api.session, key="fn-list")
    term = make_term(team_api.session, name="term-list")
    make_team(team_api.session, lc=team_api.lc, function=fn, term=term, name="Listed Team")

    r = team_api.client.get(URL, params={"lc_id": team_api.lc.id})
    assert r.status_code == 200
    names = [t["name"] for t in r.json()]
    assert "Listed Team" in names


def test_inactive_teams_excluded_by_default(team_api: TeamApiFixture) -> None:
    fn = make_function(team_api.session, key="fn-inactive")
    term = make_term(team_api.session, name="term-inactive")
    team = make_team(team_api.session, lc=team_api.lc, function=fn, term=term, name="Dead Team")
    team.active = False
    team_api.session.flush()

    r = team_api.client.get(URL, params={"lc_id": team_api.lc.id})
    names = [t["name"] for t in r.json()]
    assert "Dead Team" not in names


def test_include_inactive_flag_shows_disbanded_teams(team_api: TeamApiFixture) -> None:
    fn = make_function(team_api.session, key="fn-inc2")
    term = make_term(team_api.session, name="term-inc2")
    team = make_team(team_api.session, lc=team_api.lc, function=fn, term=term, name="Dead Team 2")
    team.active = False
    team_api.session.flush()

    r = team_api.client.get(URL, params={"lc_id": team_api.lc.id, "include_inactive": "true"})
    names = [t["name"] for t in r.json()]
    assert "Dead Team 2" in names


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_team_returns_full_response(team_api: TeamApiFixture) -> None:
    created = _create(team_api)
    assert created["name"] == "Alpha Team"
    assert created["active"] is True
    assert created["lc_id"] == team_api.lc.id


def test_create_team_is_audit_logged(team_api: TeamApiFixture) -> None:
    _create(team_api)
    log = team_api.session.execute(
        select(AuditLog).where(AuditLog.action == "team.create")
    ).scalars().first()
    assert log is not None


def test_create_team_with_unknown_function_returns_400(team_api: TeamApiFixture) -> None:
    term = make_term(team_api.session, name="term-bad-fn")
    r = team_api.client.post(
        URL,
        params={"lc_id": team_api.lc.id},
        json={"name": "Bad", "function_id": 99999, "term_id": term.id},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------


def test_rename_team(team_api: TeamApiFixture) -> None:
    created = _create(team_api)
    r = team_api.client.patch(f"{URL}/{created['id']}", json={"name": "Beta Team"})
    assert r.status_code == 200
    assert r.json()["name"] == "Beta Team"


def test_rename_is_audit_logged(team_api: TeamApiFixture) -> None:
    created = _create(team_api)
    team_api.client.patch(f"{URL}/{created['id']}", json={"name": "Gamma"})
    log = team_api.session.execute(
        select(AuditLog).where(AuditLog.action == "team.rename")
    ).scalars().first()
    assert log is not None


# ---------------------------------------------------------------------------
# Disband
# ---------------------------------------------------------------------------


def test_disband_team_sets_active_false(team_api: TeamApiFixture) -> None:
    created = _create(team_api)
    r = team_api.client.patch(f"{URL}/{created['id']}", json={"active": False})
    assert r.status_code == 200
    assert r.json()["active"] is False


def test_disband_twice_returns_400(team_api: TeamApiFixture) -> None:
    created = _create(team_api)
    team_api.client.patch(f"{URL}/{created['id']}", json={"active": False})
    r = team_api.client.patch(f"{URL}/{created['id']}", json={"active": False})
    assert r.status_code == 400


def test_reactivating_disbanded_team_returns_400(team_api: TeamApiFixture) -> None:
    created = _create(team_api)
    team_api.client.patch(f"{URL}/{created['id']}", json={"active": False})
    r = team_api.client.patch(f"{URL}/{created['id']}", json={"active": True})
    assert r.status_code == 400


def test_disband_preserves_team_member_rows(team_api: TeamApiFixture) -> None:
    """Historical team_member rows must survive a disband (spec §1.5)."""
    fn = make_function(team_api.session, key="fn-disband-hist")
    term = make_term(team_api.session, name="term-disband-hist")
    team = make_team(team_api.session, lc=team_api.lc, function=fn, term=term)
    person = make_person(team_api.session, email="hist-member@aiesec.net")
    pos = _get_or_create_position(team_api.session, key="member", rank=1)
    m = make_membership(team_api.session, person=person, lc=team_api.lc, position=pos, term=term)
    tm = TeamMember(team_id=team.id, membership_id=m.id, start_date=date.today())
    team_api.session.add(tm)
    team_api.session.flush()

    team_api.client.patch(f"{URL}/{team.id}", json={"active": False})

    rows = team_api.session.execute(
        select(TeamMember).where(TeamMember.team_id == team.id)
    ).scalars().all()
    assert len(rows) == 1


def test_disband_is_audit_logged(team_api: TeamApiFixture) -> None:
    created = _create(team_api)
    team_api.client.patch(f"{URL}/{created['id']}", json={"active": False})
    log = team_api.session.execute(
        select(AuditLog).where(AuditLog.action == "team.disband")
    ).scalars().first()
    assert log is not None


# ---------------------------------------------------------------------------
# Reparent
# ---------------------------------------------------------------------------


def test_reparent_team(team_api: TeamApiFixture) -> None:
    created = _create(team_api)
    new_fn = make_function(team_api.session, key="fn-reparent-new")
    r = team_api.client.patch(f"{URL}/{created['id']}", json={"function_id": new_fn.id})
    assert r.status_code == 200
    assert r.json()["function_id"] == new_fn.id


def test_reparent_to_unknown_function_returns_400(team_api: TeamApiFixture) -> None:
    created = _create(team_api)
    r = team_api.client.patch(f"{URL}/{created['id']}", json={"function_id": 99999})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Reassign leader
# ---------------------------------------------------------------------------


def test_reassign_leader(team_api: TeamApiFixture) -> None:
    fn = make_function(team_api.session, key="fn-leader")
    term = make_term(team_api.session, name="term-leader")
    team = make_team(team_api.session, lc=team_api.lc, function=fn, term=term)
    person = make_person(team_api.session, email="new-leader@aiesec.net")
    pos = _get_or_create_position(team_api.session, key="team_leader", rank=2)
    m = make_membership(team_api.session, person=person, lc=team_api.lc, position=pos, term=term)

    r = team_api.client.patch(
        f"{URL}/{team.id}", json={"leader_membership_id": m.id}
    )
    assert r.status_code == 200
    assert r.json()["leader_membership_id"] == m.id


def test_clear_leader(team_api: TeamApiFixture) -> None:
    fn = make_function(team_api.session, key="fn-clear-leader")
    term = make_term(team_api.session, name="term-clear-leader")
    person = make_person(team_api.session, email="leader-clear@aiesec.net")
    pos = _get_or_create_position(team_api.session, key="team_leader2", rank=2)
    m = make_membership(team_api.session, person=person, lc=team_api.lc, position=pos, term=term)
    team = make_team(team_api.session, lc=team_api.lc, function=fn, term=term)
    team.leader_membership_id = m.id
    team_api.session.flush()

    r = team_api.client.patch(
        f"{URL}/{team.id}", json={"leader_membership_id": None}
    )
    assert r.status_code == 200
    assert r.json()["leader_membership_id"] is None


# ---------------------------------------------------------------------------
# Move member
# ---------------------------------------------------------------------------


def test_move_member_to_team(team_api: TeamApiFixture) -> None:
    fn = make_function(team_api.session, key="fn-move")
    term = make_term(team_api.session, name="term-move")
    source = make_team(team_api.session, lc=team_api.lc, function=fn, term=term, name="Source")
    dest = make_team(team_api.session, lc=team_api.lc, function=fn, term=term, name="Dest")
    person = make_person(team_api.session, email="mover@aiesec.net")
    pos = _get_or_create_position(team_api.session, key="member-mv", rank=1)
    m = make_membership(team_api.session, person=person, lc=team_api.lc, position=pos, term=term)
    tm = TeamMember(team_id=source.id, membership_id=m.id, start_date=date.today())
    team_api.session.add(tm)
    team_api.session.flush()

    r = team_api.client.post(
        f"{URL}/{dest.id}/move-member", json={"membership_id": m.id}
    )
    assert r.status_code == 200

    # Old row should be ended
    old_row = team_api.session.get(TeamMember, tm.id)
    assert old_row is not None
    assert old_row.end_date == date.today()

    # New row should exist for dest team
    new_row = team_api.session.execute(
        select(TeamMember).where(
            TeamMember.team_id == dest.id,
            TeamMember.membership_id == m.id,
            TeamMember.end_date.is_(None),
        )
    ).scalar_one_or_none()
    assert new_row is not None


def test_move_member_is_audit_logged(team_api: TeamApiFixture) -> None:
    fn = make_function(team_api.session, key="fn-move-log")
    term = make_term(team_api.session, name="term-move-log")
    dest = make_team(team_api.session, lc=team_api.lc, function=fn, term=term)
    person = make_person(team_api.session, email="mover-log@aiesec.net")
    pos = _get_or_create_position(team_api.session, key="member-mvl", rank=1)
    m = make_membership(team_api.session, person=person, lc=team_api.lc, position=pos, term=term)

    team_api.client.post(f"{URL}/{dest.id}/move-member", json={"membership_id": m.id})

    log = team_api.session.execute(
        select(AuditLog).where(AuditLog.action == "team.move_member")
    ).scalars().first()
    assert log is not None


# ---------------------------------------------------------------------------
# 404 paths
# ---------------------------------------------------------------------------


def test_patch_nonexistent_team_returns_404(team_api: TeamApiFixture) -> None:
    r = team_api.client.patch(f"{URL}/99999", json={"name": "Ghost"})
    assert r.status_code == 404


def test_move_member_nonexistent_team_returns_404(team_api: TeamApiFixture) -> None:
    r = team_api.client.post(f"{URL}/99999/move-member", json={"membership_id": 1})
    assert r.status_code == 404
