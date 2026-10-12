"""The whole sign-in path, end to end (spec §9, §3.2, §8.4).

Each test starts from a signed access token, as the browser would send it after
Google sign-in, and goes through the real API and database:

    token → verify → email → person → active memberships → permissions
                                                        → one audit entry per sign-in
                                                        → feature endpoints allow/deny

Only the token's signing key is a stand-in (see `tests/auth_helpers.py`).
"""

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import BASELINE_PERMISSION_MATRIX
from app.models.membership import Membership, Team, TeamMember
from app.models.org import LC, Function, LCType, Position
from app.models.person import Person
from app.models.privacy import AuditLog
from tests.auth_helpers import bearer, make_token
from tests.helpers import YEAR_AGO, make_function, make_lc, make_membership, make_person, make_term

# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _position(db: Session, key: str, rank: int) -> Position:
    """The position with this key, at the spec §2 rank (higher = more senior).

    Reused if seeds already created it (local dev databases are seeded; CI's isn't).
    The current seeds still use the OLD rank order (lower = more senior, see
    docs/data-model.md "Known differences"), so the rank is set to the spec value
    here. The test transaction is rolled back, so the seed row is left as it was.
    """
    existing = db.execute(select(Position).where(Position.key == key)).scalar_one_or_none()
    if existing is not None:
        existing.rank = rank
        db.flush()
        return existing
    position = Position(key=key, label=key.upper(), rank=rank, active=True)
    db.add(position)
    db.flush()
    return position


def _person_in(
    db: Session,
    *,
    email: str,
    lc: LC,
    position_key: str,
    rank: int,
    function_key: str = "test_flow_ogv",
    end: date | None = None,
) -> tuple[Person, Membership]:
    person = make_person(db, full_name=f"Flow {position_key}", email=email)
    function = _function(db, function_key)
    membership = make_membership(
        db,
        person=person,
        lc=lc,
        position=_position(db, position_key, rank),
        term=make_term(db),
        function=function,
        end=end,
    )
    return person, membership


def _function(db: Session, key: str) -> Function:
    existing = db.execute(select(Function).where(Function.key == key)).scalar_one_or_none()
    return existing if existing is not None else make_function(db, key=key, label=key)


def _expected_permissions(*position_keys: str) -> list[dict[str, str]]:
    """What spec §3.2 says the union should be, worked out independently of the code
    under test: every grant for these positions, widest scope per (resource, action)."""
    order = ["own", "team", "function", "lc", "all"]
    widest: dict[tuple[str, str], str] = {}
    for grant in BASELINE_PERMISSION_MATRIX:
        if grant.position_key in position_keys:
            key = (grant.resource, grant.action)
            if key not in widest or order.index(grant.scope) > order.index(widest[key]):
                widest[key] = grant.scope
    return [
        {"resource": resource, "action": action, "scope": scope}
        for (resource, action), scope in sorted(widest.items())
    ]


def _sign_ins(db: Session) -> list[AuditLog]:
    return list(
        db.execute(select(AuditLog).where(AuditLog.action == "auth.sign_in").order_by(AuditLog.id))
        .scalars()
        .all()
    )


@pytest.fixture
def lc(db_session: Session) -> LC:
    return make_lc(db_session, name="AIESEC in Flowtown")


# ---------------------------------------------------------------------------
# Sign-in → permission resolution
# ---------------------------------------------------------------------------


def test_lcvp_sign_in_returns_the_lcvp_permissions(
    client: TestClient, db_session: Session, lc: LC
) -> None:
    _person_in(db_session, email="test_flow_lcvp@aiesec.net", lc=lc, position_key="lcvp", rank=3)

    body = client.get("/api/v1/me", headers=bearer(make_token(email="test_flow_lcvp@aiesec.net")))

    assert body.status_code == 200
    permissions = body.json()["permissions"]
    assert permissions == _expected_permissions("lcvp")
    # Spot-check against spec §3.1 so a wrong matrix can't pass by agreeing with itself.
    assert {"resource": "membership", "action": "view", "scope": "lc"} in permissions
    assert {"resource": "membership", "action": "edit", "scope": "function"} in permissions


def test_two_memberships_give_the_union_with_the_widest_scope(
    client: TestClient, db_session: Session, lc: LC
) -> None:
    person, _ = _person_in(
        db_session, email="test_flow_both@aiesec.net", lc=lc, position_key="team_leader", rank=2
    )
    make_membership(
        db_session,
        person=person,
        lc=lc,
        position=_position(db_session, "lcvp", 3),
        term=make_term(db_session),
        function=_function(db_session, "test_flow_bd"),
    )

    permissions = client.get(
        "/api/v1/me", headers=bearer(make_token(email="test_flow_both@aiesec.net"))
    ).json()["permissions"]

    assert permissions == _expected_permissions("team_leader", "lcvp")
    scopes = {(p["resource"], p["action"]): p["scope"] for p in permissions}
    # Team Leader grants membership:edit at team, LCVP at function: the wider one wins.
    assert scopes[("membership", "edit")] == "function"
    # Same for kpi_record:edit (Team Leader: team, LCVP: function).
    assert scopes[("kpi_record", "edit")] == "function"


def test_member_gets_own_scope_only(client: TestClient, db_session: Session, lc: LC) -> None:
    _person_in(
        db_session, email="test_flow_member@aiesec.net", lc=lc, position_key="member", rank=1
    )

    permissions = client.get(
        "/api/v1/me", headers=bearer(make_token(email="test_flow_member@aiesec.net"))
    ).json()["permissions"]

    assert permissions == _expected_permissions("member")
    assert {p["scope"] for p in permissions} == {"own"}
    assert not any(p["resource"] == "membership" for p in permissions)


def test_mc_position_gets_national_scope(client: TestClient, db_session: Session) -> None:
    mc = LC(name="Test Flow MC", type=LCType.MC, active=True)
    db_session.add(mc)
    db_session.flush()
    _person_in(db_session, email="test_flow_mcvp@aiesec.net", lc=mc, position_key="mcvp", rank=6)

    permissions = client.get(
        "/api/v1/me", headers=bearer(make_token(email="test_flow_mcvp@aiesec.net"))
    ).json()["permissions"]

    assert permissions == _expected_permissions("mcvp")
    assert {"resource": "membership", "action": "view", "scope": "all"} in permissions


def test_ended_membership_grants_nothing(client: TestClient, db_session: Session, lc: LC) -> None:
    _person_in(
        db_session,
        email="test_flow_ended@aiesec.net",
        lc=lc,
        position_key="lcp",
        rank=4,
        end=date.today() - timedelta(days=1),
    )

    body = client.get(
        "/api/v1/me", headers=bearer(make_token(email="test_flow_ended@aiesec.net"))
    ).json()

    assert body["person"] is not None
    assert body["memberships"] == []
    assert body["permissions"] == []


# ---------------------------------------------------------------------------
# Sign-in → audit_log
# ---------------------------------------------------------------------------


def test_sign_in_is_logged_once_per_session(
    client: TestClient, db_session: Session, lc: LC
) -> None:
    person, _ = _person_in(
        db_session, email="test_flow_audit@aiesec.net", lc=lc, position_key="lcvp", rank=3
    )
    before = len(_sign_ins(db_session))
    first_session = make_token(email="test_flow_audit@aiesec.net", session_id="session-one")

    # Page loads and token refreshes within one sign-in: logged once.
    client.get("/api/v1/me", headers=bearer(first_session))
    client.get("/api/v1/me", headers=bearer(first_session))
    refreshed = make_token(email="test_flow_audit@aiesec.net", session_id="session-one")
    client.get("/api/v1/me", headers=bearer(refreshed))

    entries = _sign_ins(db_session)[before:]
    assert len(entries) == 1
    entry = entries[0]
    assert entry.actor_person_id == person.id
    assert entry.resource_type == "person"
    assert entry.resource_id == person.id
    assert entry.actor_membership_id is None
    assert entry.diff == {"session_id": "session-one", "allocated": True}
    assert entry.summary == "Signed in to the main app"

    # Signing in again (a new Supabase session) is a new entry.
    client.get(
        "/api/v1/me",
        headers=bearer(make_token(email="test_flow_audit@aiesec.net", session_id="session-two")),
    )
    assert len(_sign_ins(db_session)[before:]) == 2


def test_unmatched_email_is_logged_without_any_personal_data(
    client: TestClient, db_session: Session
) -> None:
    before = len(_sign_ins(db_session))

    client.get("/api/v1/me", headers=bearer(make_token(email="test_flow_stranger@aiesec.net")))

    [entry] = _sign_ins(db_session)[before:]
    assert entry.actor_person_id is None
    assert entry.resource_id is None
    assert entry.diff is not None and entry.diff["allocated"] is False
    # Audit rows are permanent: the email must not appear anywhere in them.
    row_text = f"{entry.summary} {entry.diff} {entry.resource_type} {entry.action}"
    assert "stranger" not in row_text
    assert "@" not in row_text


def test_unallocated_person_is_logged_as_not_allocated(
    client: TestClient, db_session: Session, lc: LC
) -> None:
    person = make_person(db_session, email="test_flow_noterm@aiesec.net")
    before = len(_sign_ins(db_session))

    client.get("/api/v1/me", headers=bearer(make_token(email="test_flow_noterm@aiesec.net")))

    [entry] = _sign_ins(db_session)[before:]
    assert entry.actor_person_id == person.id
    assert entry.diff is not None and entry.diff["allocated"] is False
    assert "not allocated" in entry.summary


def test_rejected_sign_in_is_not_logged(client: TestClient, db_session: Session) -> None:
    before = len(_sign_ins(db_session))

    response = client.get("/api/v1/me", headers=bearer(make_token(email="someone@gmail.com")))

    assert response.status_code == 403
    assert len(_sign_ins(db_session)) == before


# ---------------------------------------------------------------------------
# Sign-in → feature endpoints (PR #18's membership API, with real tokens)
# ---------------------------------------------------------------------------


@pytest.fixture
def usyd(db_session: Session) -> dict[str, Any]:
    """An LCVP and a Member in one LC and function, the Member in a team."""
    lc = make_lc(db_session, name="Test Flow USYD")
    lcvp, lcvp_m = _person_in(
        db_session, email="test_flow_u_lcvp@aiesec.net", lc=lc, position_key="lcvp", rank=3
    )
    member, member_m = _person_in(
        db_session, email="test_flow_u_member@aiesec.net", lc=lc, position_key="member", rank=1
    )
    team = Team(
        lc_id=lc.id,
        function_id=member_m.function_id,
        term_id=member_m.term_id,
        name="Test Flow Team",
    )
    db_session.add(team)
    db_session.flush()
    db_session.add(TeamMember(team_id=team.id, membership_id=member_m.id, start_date=YEAR_AGO))
    db_session.flush()
    return {"lc": lc, "lcvp_m": lcvp_m, "member_m": member_m}


def test_lcvp_token_can_list_and_manage_their_lc(client: TestClient, usyd: dict[str, Any]) -> None:
    token = make_token(email="test_flow_u_lcvp@aiesec.net")

    listing = client.post(
        "/api/v1/members/summary", json={"search": "Flow", "pageSize": 50}, headers=bearer(token)
    )
    assert listing.status_code == 200
    assert {row["lc"]["name"] for row in listing.json()["items"]} == {"Test Flow USYD"}

    extend = client.post(
        f"/api/v1/members/{usyd['member_m'].id}/extend-term",
        json={"newEndDate": (date.today() + timedelta(days=400)).isoformat()},
        headers=bearer(token),
    )
    assert extend.status_code == 200
    assert extend.json()["status"] == "ok"


def test_member_token_cannot_manage_someone_above_them(
    client: TestClient, usyd: dict[str, Any]
) -> None:
    token = make_token(email="test_flow_u_member@aiesec.net")

    extend = client.post(
        f"/api/v1/members/{usyd['lcvp_m'].id}/extend-term",
        json={"newEndDate": (date.today() + timedelta(days=400)).isoformat()},
        headers=bearer(token),
    )

    assert extend.status_code == 200
    assert extend.json()["status"] == "rejected"


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        pytest.param({}, 401, id="no-token"),
        pytest.param(bearer("not-a-jwt"), 401, id="bad-token"),
        pytest.param(bearer(make_token(email="test_flow_nobody@aiesec.net")), 401, id="no-person"),
        pytest.param(bearer(make_token(email="someone@gmail.com")), 403, id="wrong-domain"),
    ],
)
def test_feature_endpoints_refuse_without_a_valid_signed_in_person(
    client: TestClient, headers: dict[str, str], status: int
) -> None:
    response = client.post("/api/v1/members/summary", json={}, headers=headers)

    assert response.status_code == status


def test_the_old_header_stub_no_longer_signs_anyone_in(
    client: TestClient, usyd: dict[str, Any]
) -> None:
    """PR #18's development stub trusted an `X-Actor-Email` header. It is gone:
    the header alone must not get anyone in (spec §2A.3)."""
    response = client.post(
        "/api/v1/members/summary", json={}, headers={"X-Actor-Email": "test_flow_u_lcvp@aiesec.net"}
    )

    assert response.status_code == 401
