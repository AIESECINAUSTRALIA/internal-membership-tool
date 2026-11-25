"""The whole sign-in path, end to end (spec §9, §3.2, §8.4).

Each test starts from a signed access token, as the browser would send it after
Google sign-in, and goes through the real API and database:

    token → verify → email → person → active memberships → permissions
                                                        → one audit entry per sign-in

Only the token's signing key is a stand-in (see `tests/auth/helpers.py`).
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import BASELINE_PERMISSION_MATRIX
from app.models.membership import Membership
from app.models.org import LC, Function, LCType, Position
from app.models.person import Person, PersonStatus
from tests.auth.helpers import sign_in_as
from tests.helpers import make_function, make_lc, make_membership, make_person, make_term

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


@pytest.fixture
def lc(db_session: Session) -> LC:
    return make_lc(db_session, name="AIESEC in Flowtown")


# ---------------------------------------------------------------------------
# Sign-in → permission resolution
# ---------------------------------------------------------------------------


def test_lcvp_sign_in_returns_the_lcvp_permissions(
    client: TestClient, db_session: Session, lc: LC
) -> None:
    person, _ = _person_in(
        db_session,
        email="test_flow_lcvp@aiesec.net",
        lc=lc,
        position_key="lcvp",
        rank=3,
    )

    sign_in_as(client, db_session, person)

    response = client.get("/api/v1/me")

    assert response.status_code == 200
    permissions = response.json()["permissions"]
    assert permissions == _expected_permissions("lcvp")
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

    sign_in_as(client, db_session, person)
    permissions = client.get("/api/v1/me").json()["permissions"]

    assert permissions == _expected_permissions("team_leader", "lcvp")
    scopes = {(p["resource"], p["action"]): p["scope"] for p in permissions}
    # Team Leader grants membership:edit at team, LCVP at function: the wider one wins.
    assert scopes[("membership", "edit")] == "function"
    # Same for kpi_record:edit (Team Leader: team, LCVP: function).
    assert scopes[("kpi_record", "edit")] == "function"


def test_member_gets_own_scope_only(client: TestClient, db_session: Session, lc: LC) -> None:
    person, _ = _person_in(
        db_session, email="test_flow_member@aiesec.net", lc=lc, position_key="member", rank=1
    )

    sign_in_as(client, db_session, person)
    permissions = client.get("/api/v1/me").json()["permissions"]

    assert permissions == _expected_permissions("member")
    assert {p["scope"] for p in permissions} == {"own"}
    assert not any(p["resource"] == "membership" for p in permissions)


def test_mc_position_gets_national_scope(client: TestClient, db_session: Session) -> None:
    mc = LC(name="Test Flow MC", type=LCType.MC, active=True)
    db_session.add(mc)
    db_session.flush()
    person, _ = _person_in(
        db_session,
        email="test_flow_mcvp@aiesec.net",
        lc=mc,
        position_key="mcvp",
        rank=6,
    )

    sign_in_as(client, db_session, person)
    permissions = client.get("/api/v1/me").json()["permissions"]

    assert permissions == _expected_permissions("mcvp")
    assert {"resource": "membership", "action": "view", "scope": "all"} in permissions


def test_ended_membership_grants_nothing(client: TestClient, db_session: Session, lc: LC) -> None:
    person, _ = _person_in(
        db_session,
        email="test_flow_ended@aiesec.net",
        lc=lc,
        position_key="lcp",
        rank=4,
        end=date.today() - timedelta(days=1),
    )

    sign_in_as(client, db_session, person)
    body = client.get("/api/v1/me").json()

    assert body["person"] is not None
    assert body["memberships"] == []
    assert body["permissions"] == []


def test_a_bare_email_header_does_not_sign_anyone_in(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/me",
        headers={"X-Actor-Email": "test_flow_lcvp@aiesec.net"},
    )

    assert response.status_code == 401


def test_inactive_person_session_gets_401(client: TestClient, db_session: Session, lc: LC) -> None:
    """A deactivated person's existing session stops working at once."""
    person, _ = _person_in(
        db_session,
        email="test_flow_inactive@aiesec.net",
        lc=lc,
        position_key="lcvp",
        rank=3,
    )
    sign_in_as(client, db_session, person)
    assert client.get("/api/v1/me").status_code == 200

    person.status = PersonStatus.INACTIVE
    db_session.flush()

    response = client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Account is unavailable"
