"""Tests for Membership Summary API endpoints (Spec §2A.5).

Covers all ticket acceptance criteria:
- Endpoints matching frontend/src/api/types.ts
- Dual check enforcement (matrix grant + rank outranking)
- LC isolation for non-MC users
- Transfer: existing email links person and ends active memberships in other LCs
- Every write writes to audit_log
- Test double authentication (no real Google sign-in needed)

The fixture never hard-codes primary keys: lookup rows (functions, positions)
that the baseline seeds also create are fetched by `key`, and everything else
uses `test-`-prefixed names, so the tests pass on both an empty CI database and
a seeded `make bootstrap` one.
"""

from collections.abc import Generator
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.main import app
from app.models.membership import Membership, Team, TeamMember
from app.models.org import LC, Function, LCType, Position, Term
from app.models.person import Person, PersonStatus
from app.models.privacy import AuditLog
from tests.helpers import make_state_timezone

# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


def _get_or_create[T: (Function, Position)](
    session: Session, model: type[T], *, key: str, **defaults: Any
) -> T:
    """Fetch a lookup row by `key` (creating it if absent) and pin `defaults` on it.

    The baseline seed still carries the pre-spec `position.rank` values (ticket 2
    realigns them), so the fixture sets the spec ranks itself. This only changes
    the test's own transaction, which is rolled back.
    """
    row = session.execute(select(model).where(model.key == key)).scalar_one_or_none()
    if row is None:
        row = model(key=key, **defaults)
        session.add(row)
    else:
        for field, value in defaults.items():
            setattr(row, field, value)
    session.flush()
    return row


def _person(session: Session, name: str, email: str) -> Person:
    person = Person(
        full_name=name,
        aiesec_email=email,
        join_date=date(2026, 1, 1),
        status=PersonStatus.ACTIVE,
    )
    session.add(person)
    session.flush()
    return person


def _membership(
    session: Session,
    person: Person,
    lc: LC,
    position: Position,
    function: Function,
    term: Term,
) -> Membership:
    membership = Membership(
        person_id=person.id,
        lc_id=lc.id,
        position_id=position.id,
        function_id=function.id,
        term_id=term.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    session.add(membership)
    session.flush()
    return membership


@dataclass
class Seed:
    """The flushed ORM rows the fixture created, so tests can use `.id`s."""

    term: Term
    lc_usyd: LC
    lc_mu: LC
    fn_ogv: Function
    fn_bnm: Function
    pos_member: Position
    pos_tl: Position
    pos_lcvp: Position
    pos_lcp: Position
    pos_mcvp: Position
    team_a: Team
    team_b: Team
    p_lcvp: Person
    p_member_usyd: Person
    p_member_mu: Person
    p_tl: Person
    m_lcvp: Membership
    m_member_usyd: Membership
    m_member_mu: Membership
    m_tl: Membership


@pytest.fixture
def client_with_actor(
    db_session: Session,
) -> Generator[tuple[TestClient, dict[str, CurrentActor], Seed], None, None]:
    """Test client with test-double actors configured in dependency_overrides."""
    term = Term(
        name="test-26.1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    lc_usyd = LC(name="test-usyd", type=LCType.LC, active=True)
    lc_mu = LC(name="test-mu", type=LCType.LC, active=True)
    db_session.add_all([term, lc_usyd, lc_mu])
    db_session.flush()

    fn_ogv = _get_or_create(db_session, Function, key="ogv", label="oGV", active=True)
    fn_bnm = _get_or_create(db_session, Function, key="bnm", label="BnM", active=True)
    pos_member = _get_or_create(db_session, Position, key="member", label="Member", rank=1)
    pos_tl = _get_or_create(db_session, Position, key="team_leader", label="Team Leader", rank=2)
    pos_lcvp = _get_or_create(db_session, Position, key="lcvp", label="LCVP", rank=3)
    pos_lcp = _get_or_create(db_session, Position, key="lcp", label="LCP", rank=4)
    pos_mcvp = _get_or_create(db_session, Position, key="mcvp", label="MCVP", rank=6)

    team_a = Team(lc_id=lc_usyd.id, function_id=fn_ogv.id, term_id=term.id, name="test-oGV A")
    team_b = Team(lc_id=lc_usyd.id, function_id=fn_ogv.id, term_id=term.id, name="test-oGV B")
    db_session.add_all([team_a, team_b])

    p_lcvp = _person(db_session, "LCVP Person", "test-lcvp@aiesec.net")
    p_member_usyd = _person(db_session, "USYD Member", "test-member-usyd@aiesec.net")
    p_member_mu = _person(db_session, "MU Member", "test-member-mu@aiesec.net")
    p_tl = _person(db_session, "TL Person", "test-tl@aiesec.net")

    m_lcvp = _membership(db_session, p_lcvp, lc_usyd, pos_lcvp, fn_ogv, term)
    m_member_usyd = _membership(db_session, p_member_usyd, lc_usyd, pos_member, fn_ogv, term)
    m_member_mu = _membership(db_session, p_member_mu, lc_mu, pos_member, fn_ogv, term)
    m_tl = _membership(db_session, p_tl, lc_usyd, pos_tl, fn_ogv, term)

    db_session.add(
        TeamMember(
            team_id=team_a.id,
            membership_id=m_member_usyd.id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
    )
    db_session.flush()

    seed = Seed(
        term=term,
        lc_usyd=lc_usyd,
        lc_mu=lc_mu,
        fn_ogv=fn_ogv,
        fn_bnm=fn_bnm,
        pos_member=pos_member,
        pos_tl=pos_tl,
        pos_lcvp=pos_lcvp,
        pos_lcp=pos_lcp,
        pos_mcvp=pos_mcvp,
        team_a=team_a,
        team_b=team_b,
        p_lcvp=p_lcvp,
        p_member_usyd=p_member_usyd,
        p_member_mu=p_member_mu,
        p_tl=p_tl,
        m_lcvp=m_lcvp,
        m_member_usyd=m_member_usyd,
        m_member_mu=m_member_mu,
        m_tl=m_tl,
    )
    actor_map = {
        "lcvp": CurrentActor(person=p_lcvp, active_memberships=[m_lcvp], acting_membership=m_lcvp),
        "tl": CurrentActor(person=p_tl, active_memberships=[m_tl], acting_membership=m_tl),
        "member": CurrentActor(
            person=p_member_usyd,
            active_memberships=[m_member_usyd],
            acting_membership=m_member_usyd,
        ),
    }

    app.dependency_overrides[get_db] = lambda: db_session
    # Default actor is LCVP
    app.dependency_overrides[get_current_actor] = lambda: actor_map["lcvp"]

    with TestClient(app) as test_client:
        yield test_client, actor_map, seed

    app.dependency_overrides.clear()


Fixture = tuple[TestClient, dict[str, CurrentActor], Seed]


# ---------------------------------------------------------------------------
# Test: LC Isolation & PII Protection (Spec §2A.5)
# ---------------------------------------------------------------------------


def test_list_members_lc_isolation_and_no_email(
    client_with_actor: Fixture,
) -> None:
    client, _, seed = client_with_actor
    resp = client.post(
        "/api/v1/members/summary",
        json={"search": "", "page": 0, "pageSize": 15},
    )
    assert resp.status_code == 200
    data = resp.json()

    # Total must only contain USYD members (LCVP is in USYD). MU members are isolated.
    assert any("test-usyd" in item["lc"]["name"] for item in data["rows"])
    assert not any("test-mu" in item["lc"]["name"] for item in data["rows"])

    # Personal contact data (email) is never exposed in summary rows
    for item in data["rows"]:
        assert "email" not in item
        assert "phone" not in item


# ---------------------------------------------------------------------------
# Test: Hierarchy Rule Enforcement (Allowed vs Denied per Action)
# ---------------------------------------------------------------------------


def test_extend_term_allowed_for_superior_rank(
    client_with_actor: Fixture,
    db_session: Session,
) -> None:
    client, actor_map, seed = client_with_actor
    # LCVP (rank 3) extending Member (rank 1) -> Allowed
    app.dependency_overrides[get_current_actor] = lambda: actor_map["lcvp"]

    resp = client.post(
        f"/api/v1/members/{seed.m_member_usyd.id}/extend-term",
        json={"newEndDate": "2027-06-30"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify audit log was recorded
    audit_entry = db_session.execute(
        select(AuditLog).where(
            AuditLog.resource_id == seed.m_member_usyd.id,
            AuditLog.action == "membership.extend_term",
        )
    ).scalar_one_or_none()
    assert audit_entry is not None
    assert audit_entry.diff is not None
    assert audit_entry.diff["after"] == "2027-06-30"


def test_extend_term_denied_for_self(
    client_with_actor: Fixture,
) -> None:
    client, actor_map, seed = client_with_actor
    # LCVP trying to extend their own membership -> Denied
    app.dependency_overrides[get_current_actor] = lambda: actor_map["lcvp"]

    resp = client.post(
        f"/api/v1/members/{seed.m_lcvp.id}/extend-term",
        json={"newEndDate": "2027-06-30"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_move_to_team_allowed_for_lcvp(
    client_with_actor: Fixture,
    db_session: Session,
) -> None:
    client, actor_map, seed = client_with_actor
    # LCVP moving Member from team 1 to team 2 -> Allowed
    app.dependency_overrides[get_current_actor] = lambda: actor_map["lcvp"]

    resp = client.post(
        f"/api/v1/members/{seed.m_member_usyd.id}/move-to-team",
        json={"teamId": seed.team_b.id},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify audit log
    audit_entry = db_session.execute(
        select(AuditLog).where(AuditLog.action == "team_member.move")
    ).scalar_one_or_none()
    assert audit_entry is not None
    assert audit_entry.diff is not None
    assert audit_entry.diff["after"]["team_id"] == seed.team_b.id


def test_move_to_team_denied_for_team_leader(
    client_with_actor: Fixture,
) -> None:
    client, actor_map, seed = client_with_actor
    # Team Leader trying to move member to team -> Denied (TL has no team_member:edit grant)
    app.dependency_overrides[get_current_actor] = lambda: actor_map["tl"]

    resp = client.post(
        f"/api/v1/members/{seed.m_member_usyd.id}/move-to-team",
        json={"teamId": seed.team_b.id},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


# ---------------------------------------------------------------------------
# Test: Transfer Between LCs (Spec §5.1)
# ---------------------------------------------------------------------------


def test_add_member_with_existing_email_ends_other_lc_memberships(
    client_with_actor: Fixture,
    db_session: Session,
) -> None:
    client, actor_map, seed = client_with_actor
    # LCVP (USYD) adds a person whose email belongs to MU Member
    app.dependency_overrides[get_current_actor] = lambda: actor_map["lcvp"]

    start = date(2026, 7, 1)
    end = date(2026, 12, 31)

    # 1. First call without confirmedExisting -> returns confirm_existing
    resp = client.post(
        "/api/v1/members",
        json={
            "email": seed.p_member_mu.aiesec_email,
            "lcId": seed.lc_usyd.id,
            "positionKey": "member",
            "functionKey": "ogv",
            "termId": seed.term.id,
            "startDate": str(start),
            "endDate": str(end),
            "confirmedExisting": False,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirm_existing"

    # 2. Confirmed transfer call -> attaches person and ends MU membership
    resp_confirmed = client.post(
        "/api/v1/members",
        json={
            "email": seed.p_member_mu.aiesec_email,
            "lcId": seed.lc_usyd.id,
            "positionKey": "member",
            "functionKey": "ogv",
            "termId": seed.term.id,
            "startDate": str(start),
            "endDate": str(end),
            "confirmedExisting": True,
        },
    )
    assert resp_confirmed.status_code == 200
    assert resp_confirmed.json()["status"] == "created"

    # Verify MU membership was ended to the day before the new start date
    mu_membership = db_session.get(Membership, seed.m_member_mu.id)
    assert mu_membership is not None
    assert mu_membership.end_date == start - timedelta(days=1)

    # Verify audit log recorded the transfer termination
    audit_end = db_session.execute(
        select(AuditLog).where(
            AuditLog.resource_id == seed.m_member_mu.id, AuditLog.action == "membership.end_term"
        )
    ).scalar_one_or_none()
    assert audit_end is not None


# ---------------------------------------------------------------------------
# Test: Get Membership Detail
# ---------------------------------------------------------------------------


def test_get_membership_detail(
    client_with_actor: Fixture,
) -> None:
    client, _, seed = client_with_actor
    resp = client.get(f"/api/v1/members/{seed.m_member_usyd.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["membershipId"] == str(seed.m_member_usyd.id)
    assert data["personName"] == "USYD Member"
    assert data["position"]["key"] == "member"
    assert data["currentTeam"]["name"] == "test-oGV A"
    # teamOptions should offer team 2 (oGV Team B) in the same function and LC
    assert len(data["teamOptions"]) == 1
    assert data["teamOptions"][0]["name"] == "test-oGV B"


# ---------------------------------------------------------------------------
# Test: addMember enforces both §3.4 checks before anything else
# ---------------------------------------------------------------------------


def _add_payload(seed: Seed, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "email": "test-new-person@aiesec.net",
        "firstName": "New",
        "lastName": "Person",
        "lcId": seed.lc_usyd.id,
        "positionKey": "member",
        "functionKey": "ogv",
        "termId": seed.term.id,
        "startDate": "2026-07-01",
        "endDate": "2026-12-31",
        "confirmedExisting": False,
    }
    payload.update(overrides)
    return payload


def _create_audit_count(db_session: Session) -> int:
    return (
        db_session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "membership.create")
        )
        or 0
    )


def test_add_member_denied_for_plain_member(
    client_with_actor: Fixture, db_session: Session
) -> None:
    client, actor_map, seed = client_with_actor
    app.dependency_overrides[get_current_actor] = lambda: actor_map["member"]

    # The email belongs to an existing person: a denied actor must not learn that.
    resp = client.post(
        "/api/v1/members",
        json=_add_payload(seed, email=seed.p_member_mu.aiesec_email),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert _create_audit_count(db_session) == 0


def test_add_member_denied_outside_lc(client_with_actor: Fixture) -> None:
    client, _, seed = client_with_actor
    resp = client.post("/api/v1/members", json=_add_payload(seed, lcId=seed.lc_mu.id))
    assert resp.json() == {
        "status": "rejected",
        "message": "You cannot add people outside your scope.",
    }


def test_add_member_denied_equal_rank(client_with_actor: Fixture) -> None:
    client, _, seed = client_with_actor
    resp = client.post("/api/v1/members", json=_add_payload(seed, positionKey="lcvp"))
    assert resp.json() == {
        "status": "rejected",
        "message": "You cannot add someone of equal or higher rank.",
    }


def test_add_member_denied_mc_position_in_lc(client_with_actor: Fixture) -> None:
    client, _, seed = client_with_actor
    resp = client.post("/api/v1/members", json=_add_payload(seed, positionKey="mcvp"))
    assert resp.json() == {
        "status": "rejected",
        "message": "Position level does not match LC type.",
    }


def test_add_member_unknown_function_rejected(client_with_actor: Fixture) -> None:
    client, _, seed = client_with_actor
    resp = client.post("/api/v1/members", json=_add_payload(seed, functionKey="nope"))
    assert resp.json() == {"status": "rejected", "message": "Function not found."}


def test_add_member_allowed_new_person(client_with_actor: Fixture, db_session: Session) -> None:
    client, _, seed = client_with_actor
    resp = client.post("/api/v1/members", json=_add_payload(seed))
    assert resp.json()["status"] == "created"
    created = db_session.execute(
        select(Person).where(Person.aiesec_email == "test-new-person@aiesec.net")
    ).scalar_one_or_none()
    assert created is not None
    assert _create_audit_count(db_session) == 1


def test_add_member_sets_timezone_from_lc_state(
    client_with_actor: Fixture, db_session: Session
) -> None:
    client, _, seed = client_with_actor
    make_state_timezone(db_session, state="WA", timezone="Australia/Perth")
    seed.lc_usyd.state = "WA"
    db_session.flush()

    resp = client.post("/api/v1/members", json=_add_payload(seed))

    assert resp.json()["status"] == "created"
    created = db_session.execute(
        select(Person).where(Person.aiesec_email == "test-new-person@aiesec.net")
    ).scalar_one()
    assert created.timezone == "Australia/Perth"


def test_add_member_defaults_timezone_when_lc_has_no_state(
    client_with_actor: Fixture, db_session: Session
) -> None:
    client, _, seed = client_with_actor

    resp = client.post("/api/v1/members", json=_add_payload(seed))

    assert resp.json()["status"] == "created"
    created = db_session.execute(
        select(Person).where(Person.aiesec_email == "test-new-person@aiesec.net")
    ).scalar_one()
    assert created.timezone == "Australia/Melbourne"


def test_add_member_rejects_inactive_lc(client_with_actor: Fixture, db_session: Session) -> None:
    client, _, seed = client_with_actor
    seed.lc_usyd.active = False
    db_session.flush()

    resp = client.post("/api/v1/members", json=_add_payload(seed))

    assert resp.json() == {"status": "rejected", "message": "That LC is inactive."}
    assert _create_audit_count(db_session) == 0


# ---------------------------------------------------------------------------
# Test: detail endpoint respects LC isolation; unallocated actors get nothing
# ---------------------------------------------------------------------------


def test_get_membership_detail_other_lc_is_404(client_with_actor: Fixture) -> None:
    client, _, seed = client_with_actor
    resp = client.get(f"/api/v1/members/{seed.m_member_mu.id}")
    assert resp.status_code == 404


def test_get_membership_detail_denied_for_member(client_with_actor: Fixture) -> None:
    client, actor_map, seed = client_with_actor
    app.dependency_overrides[get_current_actor] = lambda: actor_map["member"]
    resp = client.get(f"/api/v1/members/{seed.m_tl.id}")
    assert resp.status_code == 404


def test_actor_without_membership_gets_nothing(
    client_with_actor: Fixture, db_session: Session
) -> None:
    client, _, seed = client_with_actor
    nobody = CurrentActor(
        person=_person(db_session, "Unallocated", "test-nobody@aiesec.net"),
        active_memberships=[],
        acting_membership=None,
    )
    app.dependency_overrides[get_current_actor] = lambda: nobody
    target = seed.m_member_usyd.id

    listed = client.post("/api/v1/members/summary", json={})
    assert listed.status_code == 200
    assert listed.json()["rows"] == []
    assert listed.json()["total"] == 0

    assert client.get(f"/api/v1/members/{target}").status_code == 404

    extend = client.post(f"/api/v1/members/{target}/extend-term", json={"newEndDate": "2027-06-30"})
    assert extend.json()["status"] == "rejected"

    move = client.post(f"/api/v1/members/{target}/move-to-team", json={"teamId": seed.team_b.id})
    assert move.json()["status"] == "rejected"

    added = client.post("/api/v1/members", json=_add_payload(seed))
    assert added.json()["status"] == "rejected"


# ---------------------------------------------------------------------------
# Test: term resolution and audit actor
# ---------------------------------------------------------------------------


def test_add_member_resolves_term_from_start_date(
    client_with_actor: Fixture, db_session: Session
) -> None:
    client, _, seed = client_with_actor
    payload = _add_payload(seed, startDate="2026-11-01")
    del payload["termId"]

    resp = client.post("/api/v1/members", json=payload)

    assert resp.json()["status"] == "created"
    created = db_session.execute(
        select(Membership).join(Person).where(Person.aiesec_email == payload["email"])
    ).scalar_one()
    assert created.term_id == seed.term.id


def test_add_member_rejects_date_outside_any_term(client_with_actor: Fixture) -> None:
    client, _, seed = client_with_actor
    payload = _add_payload(seed, startDate="2099-01-01", endDate="2099-06-30")
    del payload["termId"]

    resp = client.post("/api/v1/members", json=payload)

    assert resp.json() == {"status": "rejected", "message": "No term covers that start date."}


def test_add_member_rejects_unknown_term_id(client_with_actor: Fixture) -> None:
    client, _, seed = client_with_actor
    resp = client.post("/api/v1/members", json=_add_payload(seed, termId=999_999_999))
    assert resp.json() == {"status": "rejected", "message": "No term covers that start date."}


def test_audit_records_acting_membership_and_person(
    client_with_actor: Fixture, db_session: Session
) -> None:
    client, _, seed = client_with_actor
    # Two hats, lower-ranked listed first: the audit row must name the LCVP one.
    low = _membership(
        db_session, seed.p_lcvp, seed.lc_usyd, seed.pos_member, seed.fn_ogv, seed.term
    )
    two_hats = CurrentActor(
        person=seed.p_lcvp,
        active_memberships=[low, seed.m_lcvp],
        acting_membership=seed.m_lcvp,
    )
    app.dependency_overrides[get_current_actor] = lambda: two_hats

    resp = client.post(
        f"/api/v1/members/{seed.m_member_usyd.id}/extend-term",
        json={"newEndDate": "2027-06-30"},
    )
    assert resp.json()["status"] == "ok"

    entry = db_session.execute(
        select(AuditLog).where(
            AuditLog.resource_id == seed.m_member_usyd.id,
            AuditLog.action == "membership.extend_term",
        )
    ).scalar_one()
    assert entry.actor_membership_id == seed.m_lcvp.id
    assert entry.actor_person_id == seed.p_lcvp.id


def test_add_member_rejects_team_from_another_lc(
    client_with_actor: Fixture, db_session: Session
) -> None:
    client, _, seed = client_with_actor
    foreign_team = Team(
        lc_id=seed.lc_mu.id, function_id=seed.fn_ogv.id, term_id=seed.term.id, name="test-mu team"
    )
    db_session.add(foreign_team)
    db_session.flush()

    resp = client.post("/api/v1/members", json=_add_payload(seed, teamId=foreign_team.id))

    assert resp.json() == {
        "status": "rejected",
        "message": "Choose a team in the same LC and function.",
    }
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(TeamMember)
            .where(TeamMember.team_id == foreign_team.id)
        )
        == 0
    )


def test_add_member_rejects_unknown_team(client_with_actor: Fixture) -> None:
    client, _, seed = client_with_actor
    resp = client.post("/api/v1/members", json=_add_payload(seed, teamId=999_999_999))
    assert resp.json() == {
        "status": "rejected",
        "message": "Choose a team in the same LC and function.",
    }


# ---------------------------------------------------------------------------
# Test: Team Leaders see their whole LC; multi-LC people show their latest LC
# ---------------------------------------------------------------------------


def test_team_leader_sees_whole_lc_in_list_and_detail(client_with_actor: Fixture) -> None:
    client, actor_map, seed = client_with_actor
    app.dependency_overrides[get_current_actor] = lambda: actor_map["tl"]

    listed = client.post("/api/v1/members/summary", json={})
    names = {item["lc"]["name"] for item in listed.json()["rows"]}
    assert names == {"test-usyd"}

    # A member of another team in the same LC is viewable, another LC's is not.
    assert client.get(f"/api/v1/members/{seed.m_member_usyd.id}").status_code == 200
    assert client.get(f"/api/v1/members/{seed.m_member_mu.id}").status_code == 404


def test_list_uses_most_recent_membership_for_lc_and_roles(
    client_with_actor: Fixture, db_session: Session
) -> None:
    client, _, seed = client_with_actor
    mc = LC(name="test-mc", type=LCType.MC, active=True)
    db_session.add(mc)
    db_session.flush()
    mc_person = _person(db_session, "MC Person", "test-mcvp@aiesec.net")
    m_mc = _membership(db_session, mc_person, mc, seed.pos_mcvp, seed.fn_ogv, seed.term)
    app.dependency_overrides[get_current_actor] = lambda: CurrentActor(
        person=mc_person, active_memberships=[m_mc], acting_membership=m_mc
    )

    mover = _person(db_session, "Mover Person", "test-mover@aiesec.net")
    older = _membership(db_session, mover, seed.lc_mu, seed.pos_member, seed.fn_ogv, seed.term)
    older.start_date = date(2026, 1, 1)
    newer = _membership(db_session, mover, seed.lc_usyd, seed.pos_tl, seed.fn_ogv, seed.term)
    newer.start_date = date(2026, 6, 1)
    db_session.flush()

    resp = client.post("/api/v1/members/summary", json={"search": "Mover"})

    (row,) = resp.json()["rows"]
    assert row["lc"]["name"] == "test-usyd"
    assert [r["membershipId"] for r in row["roles"]] == [str(newer.id)]
    assert row["roles"][0]["position"]["key"] == "team_leader"


# ---------------------------------------------------------------------------
# Test: request/response shapes match frontend/src/api/types.ts exactly
# ---------------------------------------------------------------------------


def test_list_response_is_rows_and_total_only(client_with_actor: Fixture) -> None:
    client, _, _ = client_with_actor
    resp = client.post("/api/v1/members/summary", json={})
    assert set(resp.json()) == {"rows", "total"}


def test_list_honours_nested_sort_object(client_with_actor: Fixture) -> None:
    client, _, _ = client_with_actor

    def first_names(direction: str) -> list[str]:
        resp = client.post(
            "/api/v1/members/summary",
            json={
                "search": "",
                "sort": {"field": "firstName", "direction": direction},
                "page": 0,
                "pageSize": 15,
                "lcId": None,
            },
        )
        assert resp.status_code == 200
        return [row["firstName"] for row in resp.json()["rows"]]

    assert first_names("asc") == ["LCVP", "TL", "USYD"]
    assert first_names("desc") == ["USYD", "TL", "LCVP"]


def test_list_accepts_null_sort(client_with_actor: Fixture) -> None:
    client, _, _ = client_with_actor
    resp = client.post("/api/v1/members/summary", json={"sort": None})
    assert resp.status_code == 200
    assert resp.json()["total"] == 3


def test_add_and_move_accept_string_ids_like_the_frontend_sends(
    client_with_actor: Fixture,
) -> None:
    client, _, seed = client_with_actor
    added = client.post(
        "/api/v1/members",
        json=_add_payload(
            seed,
            lcId=str(seed.lc_usyd.id),
            termId=str(seed.term.id),
            teamId=str(seed.team_a.id),
        ),
    )
    assert added.json()["status"] == "created"

    moved = client.post(
        f"/api/v1/members/{seed.m_member_usyd.id}/move-to-team",
        json={"teamId": str(seed.team_b.id)},
    )
    assert moved.json()["status"] == "ok"
