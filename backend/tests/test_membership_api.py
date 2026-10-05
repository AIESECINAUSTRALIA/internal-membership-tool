"""Tests for Membership Summary API endpoints (Spec §2A.5).

Covers all ticket acceptance criteria:
- Endpoints matching frontend/src/api/types.ts
- Dual check enforcement (matrix grant + rank outranking)
- LC isolation for non-MC users
- Transfer: existing email links person and ends active memberships in other LCs
- Every write writes to audit_log
- Test double authentication (no real Google sign-in needed)
"""

from collections.abc import Generator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.main import app
from app.models.membership import Membership, Team, TeamMember
from app.models.org import LC, Function, LCType, Position, Term
from app.models.person import Person, PersonStatus
from app.models.privacy import AuditLog

# ---------------------------------------------------------------------------
# Test Fixtures & In-Memory / Isolated DB Setup
# ---------------------------------------------------------------------------


@pytest.fixture
def client_with_actor(
    db_session: Session,
) -> Generator[tuple[TestClient, dict[str, CurrentActor]], None, None]:
    """Test client with test-double actors configured in dependency_overrides."""
    # Seed minimal reference data
    term = Term(
        id=1,
        name="26.1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    db_session.add(term)

    lc_usyd = LC(id=1, name="USYD", type=LCType.LC, active=True)
    lc_mu = LC(id=2, name="MU", type=LCType.LC, active=True)
    lc_mc = LC(id=3, name="MC", type=LCType.MC, active=True)
    db_session.add_all([lc_usyd, lc_mu, lc_mc])

    fn_ogv = Function(id=1, key="ogv", label="Outgoing Global Volunteer", active=True)
    fn_bnm = Function(id=2, key="bnm", label="Brand and Marketing", active=True)
    db_session.add_all([fn_ogv, fn_bnm])

    pos_member = Position(id=1, key="member", label="Member", rank=1, active=True)
    pos_tl = Position(id=2, key="team_leader", label="Team Leader", rank=2, active=True)
    pos_lcvp = Position(id=3, key="lcvp", label="LCVP", rank=3, active=True)
    pos_lcp = Position(id=4, key="lcp", label="LCP", rank=4, active=True)
    pos_mcvp = Position(id=6, key="mcvp", label="MCVP", rank=6, active=True)
    db_session.add_all([pos_member, pos_tl, pos_lcvp, pos_lcp, pos_mcvp])
    db_session.flush()

    # Seed Teams
    team1 = Team(id=1, lc_id=1, function_id=1, term_id=1, name="oGV Team A")
    team2 = Team(id=2, lc_id=1, function_id=1, term_id=1, name="oGV Team B")
    db_session.add_all([team1, team2])

    # Seed Persons
    p_lcvp = Person(
        id=1,
        full_name="LCVP Person",
        aiesec_email="lcvp@aiesec.net",
        join_date=date(2026, 1, 1),
        status=PersonStatus.ACTIVE,
    )
    p_member_usyd = Person(
        id=2,
        full_name="USYD Member",
        aiesec_email="member_usyd@aiesec.net",
        join_date=date(2026, 1, 1),
        status=PersonStatus.ACTIVE,
    )
    p_member_mu = Person(
        id=3,
        full_name="MU Member",
        aiesec_email="member_mu@aiesec.net",
        join_date=date(2026, 1, 1),
        status=PersonStatus.ACTIVE,
    )
    p_tl = Person(
        id=4,
        full_name="TL Person",
        aiesec_email="tl@aiesec.net",
        join_date=date(2026, 1, 1),
        status=PersonStatus.ACTIVE,
    )
    db_session.add_all([p_lcvp, p_member_usyd, p_member_mu, p_tl])
    db_session.flush()

    # Seed Memberships
    m_lcvp = Membership(
        id=1,
        person_id=1,
        lc_id=1,
        position_id=3,
        function_id=1,
        term_id=1,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    m_member_usyd = Membership(
        id=2,
        person_id=2,
        lc_id=1,
        position_id=1,
        function_id=1,
        term_id=1,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    m_member_mu = Membership(
        id=3,
        person_id=3,
        lc_id=2,
        position_id=1,
        function_id=1,
        term_id=1,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    m_tl = Membership(
        id=4,
        person_id=4,
        lc_id=1,
        position_id=2,
        function_id=1,
        term_id=1,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    db_session.add_all([m_lcvp, m_member_usyd, m_member_mu, m_tl])
    db_session.flush()

    # Team membership for member_usyd
    tm1 = TeamMember(
        id=1,
        team_id=1,
        membership_id=2,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    db_session.add(tm1)
    db_session.flush()

    actor_map = {
        "lcvp": CurrentActor(
            person=p_lcvp, active_memberships=[m_lcvp], acting_membership=m_lcvp
        ),
        "tl": CurrentActor(
            person=p_tl, active_memberships=[m_tl], acting_membership=m_tl
        ),
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
        yield test_client, actor_map

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: LC Isolation & PII Protection (Spec §2A.5)
# ---------------------------------------------------------------------------


def test_list_members_lc_isolation_and_no_email(
    client_with_actor: tuple[TestClient, dict[str, CurrentActor]],
) -> None:
    client, _ = client_with_actor
    resp = client.post(
        "/api/v1/members/summary",
        json={"search": "", "page": 0, "pageSize": 15},
    )
    assert resp.status_code == 200
    data = resp.json()

    # Total must only contain USYD members (LCVP is in USYD). MU members are isolated.
    assert any("USYD" in item["lc"]["name"] for item in data["items"])
    assert not any("MU" in item["lc"]["name"] for item in data["items"])

    # Personal contact data (email) is never exposed in summary rows
    for item in data["items"]:
        assert "email" not in item
        assert "phone" not in item


# ---------------------------------------------------------------------------
# Test: Hierarchy Rule Enforcement (Allowed vs Denied per Action)
# ---------------------------------------------------------------------------


def test_extend_term_allowed_for_superior_rank(
    client_with_actor: tuple[TestClient, dict[str, CurrentActor]],
    db_session: Session,
) -> None:
    client, actor_map = client_with_actor
    # LCVP (rank 3) extending Member (rank 1) -> Allowed
    app.dependency_overrides[get_current_actor] = lambda: actor_map["lcvp"]

    resp = client.post(
        "/api/v1/members/2/extend-term",
        json={"newEndDate": "2027-06-30"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify audit log was recorded
    audit_entry = db_session.execute(
        select(AuditLog).where(
            AuditLog.resource_id == 2, AuditLog.action == "membership.extend_term"
        )
    ).scalar_one_or_none()
    assert audit_entry is not None
    assert audit_entry.diff is not None
    assert audit_entry.diff["after"] == "2027-06-30"


def test_extend_term_denied_for_self(
    client_with_actor: tuple[TestClient, dict[str, CurrentActor]],
) -> None:
    client, actor_map = client_with_actor
    # LCVP trying to extend their own membership (id=1) -> Denied
    app.dependency_overrides[get_current_actor] = lambda: actor_map["lcvp"]

    resp = client.post(
        "/api/v1/members/1/extend-term",
        json={"newEndDate": "2027-06-30"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_move_to_team_allowed_for_lcvp(
    client_with_actor: tuple[TestClient, dict[str, CurrentActor]],
    db_session: Session,
) -> None:
    client, actor_map = client_with_actor
    # LCVP moving Member from team 1 to team 2 -> Allowed
    app.dependency_overrides[get_current_actor] = lambda: actor_map["lcvp"]

    resp = client.post(
        "/api/v1/members/2/move-to-team",
        json={"teamId": 2},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify audit log
    audit_entry = db_session.execute(
        select(AuditLog).where(AuditLog.action == "team_member.move")
    ).scalar_one_or_none()
    assert audit_entry is not None
    assert audit_entry.diff is not None
    assert audit_entry.diff["after"]["team_id"] == 2


def test_move_to_team_denied_for_team_leader(
    client_with_actor: tuple[TestClient, dict[str, CurrentActor]],
) -> None:
    client, actor_map = client_with_actor
    # Team Leader trying to move member to team -> Denied (TL has no team_member:edit grant)
    app.dependency_overrides[get_current_actor] = lambda: actor_map["tl"]

    resp = client.post(
        "/api/v1/members/2/move-to-team",
        json={"teamId": 2},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


# ---------------------------------------------------------------------------
# Test: Transfer Between LCs (Spec §5.1)
# ---------------------------------------------------------------------------


def test_add_member_with_existing_email_ends_other_lc_memberships(
    client_with_actor: tuple[TestClient, dict[str, CurrentActor]],
    db_session: Session,
) -> None:
    client, actor_map = client_with_actor
    # LCVP (USYD) adds a person whose email belongs to MU Member (id=3)
    app.dependency_overrides[get_current_actor] = lambda: actor_map["lcvp"]

    start = date(2026, 7, 1)
    end = date(2026, 12, 31)

    # 1. First call without confirmedExisting -> returns confirm_existing
    resp = client.post(
        "/api/v1/members",
        json={
            "email": "member_mu@aiesec.net",
            "lcId": 1,  # USYD
            "positionKey": "member",
            "functionKey": "ogv",
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
            "email": "member_mu@aiesec.net",
            "lcId": 1,  # USYD
            "positionKey": "member",
            "functionKey": "ogv",
            "startDate": str(start),
            "endDate": str(end),
            "confirmedExisting": True,
        },
    )
    assert resp_confirmed.status_code == 200
    assert resp_confirmed.json()["status"] == "created"

    # Verify MU membership (id=3) was ended to the day before the new start date
    mu_membership = db_session.get(Membership, 3)
    assert mu_membership is not None
    assert mu_membership.end_date == start - timedelta(days=1)

    # Verify audit log recorded the transfer termination
    audit_end = db_session.execute(
        select(AuditLog).where(
            AuditLog.resource_id == 3, AuditLog.action == "membership.end_term"
        )
    ).scalar_one_or_none()
    assert audit_end is not None


# ---------------------------------------------------------------------------
# Test: Get Membership Detail
# ---------------------------------------------------------------------------


def test_get_membership_detail(
    client_with_actor: tuple[TestClient, dict[str, CurrentActor]],
) -> None:
    client, _ = client_with_actor
    resp = client.get("/api/v1/members/2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["membershipId"] == "2"
    assert data["personName"] == "USYD Member"
    assert data["position"]["key"] == "member"
    assert data["currentTeam"]["name"] == "oGV Team A"
    # teamOptions should offer team 2 (oGV Team B) in the same function and LC
    assert len(data["teamOptions"]) == 1
    assert data["teamOptions"][0]["name"] == "oGV Team B"
