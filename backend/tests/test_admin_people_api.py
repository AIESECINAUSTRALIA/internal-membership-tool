"""Tests for the Admin console's People and Memberships endpoints (DEV-47).

Spec §1.5, §2A.2: add, edit and deactivate people; assign, correct and end
memberships. Authentication is replaced with test-double actors, as in
`test_lc_api.py`, and everything runs against the real migrated database.

What the acceptance criteria need, and where it's tested:

- gated by `manage` on `person` / `membership`: "Who may use the screens"
- edit / deactivate a person, correct a membership: the sections of the same names
- every change is audit-logged, with no names or emails: `_assert_no_personal_data`
- deactivating deletes nothing and leaves history intact:
  `test_deactivate_keeps_membership_and_kpi_history`
"""

from collections.abc import Generator
from dataclasses import dataclass
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_current_person, get_db
from app.core.auth import AuthenticatedUser
from app.core.sessions import activate_session, create_pending_session, get_valid_session
from app.main import app
from app.models.kpi import KpiRecord, KpiSource
from app.models.membership import Membership, Team, TeamMember
from app.models.org import LC, Function, LCType, Position, Term
from app.models.person import Person, PersonStatus
from app.models.privacy import AuditLog
from app.repositories import admin_people as admin_people_repo
from app.repositories import membership as membership_repo
from app.repositories.kpi import record_kpi
from tests.helpers import (
    api_client_options,
    make_function,
    make_kpi_attribute,
    make_lc,
    make_membership,
    make_person,
    make_term,
)

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


def _position(session: Session, *, key: str, rank: int) -> Position:
    """Get or create a position, and set its rank for this test.

    A local database may already hold seeded positions, whose `rank` still runs the
    old way (docs/data-model.md, "Known differences"). Setting it here is rolled back
    with the rest of the test.
    """
    position = session.execute(select(Position).where(Position.key == key)).scalar_one_or_none()
    if position is None:
        position = Position(key=key, label=key.upper(), active=True)
        session.add(position)
    position.rank = rank
    position.active = True
    # Seeded rows may carry admin-edited values (DEV-0049), and a new row defaults to
    # "no president exception". Set what these tests assume: only the presidents may
    # add another holder of their own position.
    position.can_add_same_rank = key in {"lcp", "mcp"}
    position.level = None  # None: decided by key
    session.flush()
    return position


@dataclass
class Fixture:
    client: TestClient
    session: Session
    actors: dict[str, CurrentActor]
    mc: LC
    lc_a: LC
    lc_b: LC
    fn_a: Function
    fn_b: Function
    term: Term
    positions: dict[str, Position]
    target: Person
    target_membership: Membership


def _actor(session: Session, *, email: str, lc: LC, position: Position, term: Term) -> CurrentActor:
    person = make_person(session, full_name="Actor Person", email=email)
    membership = make_membership(session, person=person, lc=lc, position=position, term=term)
    return CurrentActor(
        person=person, active_memberships=[membership], acting_membership=membership
    )


@pytest.fixture
def admin(db_session: Session) -> Generator[Fixture, None, None]:
    mc = make_lc(db_session, name="test-admin-mc", lc_type=LCType.MC)
    lc_a = make_lc(db_session, name="test-admin-lc-a")
    lc_b = make_lc(db_session, name="test-admin-lc-b")
    fn_a = make_function(db_session, key="test_admin_fn_a", label="Function A")
    fn_b = make_function(db_session, key="test_admin_fn_b", label="Function B")
    term = make_term(db_session, name="test-admin-term", start=TODAY - timedelta(days=200))

    positions = {
        key: _position(db_session, key=key, rank=rank)
        for key, rank in [
            ("member", 1),
            ("team_leader", 2),
            ("lcvp", 3),
            ("lcp", 4),
            ("mcd", 5),
            ("mcvp", 6),
            ("mcp", 7),
            ("admin", 8),
        ]
    }

    actors = {
        "mcp": _actor(
            db_session, email="test-adm-mcp@aiesec.net", lc=mc, position=positions["mcp"], term=term
        ),
        "mcd": _actor(
            db_session, email="test-adm-mcd@aiesec.net", lc=mc, position=positions["mcd"], term=term
        ),
        "admin": _actor(
            db_session,
            email="test-adm-admin@aiesec.net",
            lc=mc,
            position=positions["admin"],
            term=term,
        ),
        "lcp": _actor(
            db_session,
            email="test-adm-lcp@aiesec.net",
            lc=lc_a,
            position=positions["lcp"],
            term=term,
        ),
    }
    actors["nobody"] = CurrentActor(
        person=make_person(db_session, email="test-adm-nobody@aiesec.net"),
        active_memberships=[],
        acting_membership=None,
    )

    target = make_person(db_session, full_name="Tess Target", email="test-adm-target@aiesec.net")
    # EXPA sign-in finds people by this id, so the sign-in tests need it set.
    target.expa_id = "test-expa-target"
    db_session.flush()
    target_membership = make_membership(
        db_session,
        person=target,
        lc=lc_a,
        position=positions["member"],
        function=fn_a,
        term=term,
        start=TODAY - timedelta(days=100),
        end=TODAY + timedelta(days=100),
    )

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_actor] = lambda: actors["mcp"]
    with TestClient(app, **api_client_options()) as client:
        yield Fixture(
            client=client,
            session=db_session,
            actors=actors,
            mc=mc,
            lc_a=lc_a,
            lc_b=lc_b,
            fn_a=fn_a,
            fn_b=fn_b,
            term=term,
            positions=positions,
            target=target,
            target_membership=target_membership,
        )
    app.dependency_overrides.clear()


def _act_as(name: str, fx: Fixture) -> None:
    app.dependency_overrides[get_current_actor] = lambda: fx.actors[name]


def _audit(session: Session, action: str, resource_id: int) -> list[AuditLog]:
    return list(
        session.execute(
            select(AuditLog)
            .where(AuditLog.action == action, AuditLog.resource_id == resource_id)
            .order_by(AuditLog.id)
        ).scalars()
    )


def _assert_no_personal_data(entries: list[AuditLog], *texts: str) -> None:
    """Audit entries can never be edited or deleted, so they must not hold names or
    emails (spec §8.4). Checks the summary and the diff."""
    assert entries, "expected at least one audit entry"
    for entry in entries:
        blob = f"{entry.summary} {entry.diff}".lower()
        for text in texts:
            assert text.lower() not in blob, f"{text!r} leaked into audit entry {entry.action}"


def _assign(fx: Fixture, person_id: int, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "lcId": fx.lc_b.id,
        "positionKey": "member",
        "functionKey": fx.fn_b.key,
        "startDate": TODAY.isoformat(),
        "endDate": (TODAY + timedelta(days=90)).isoformat(),
    }
    body.update(overrides)
    response = fx.client.post(f"/api/v1/people/{person_id}/memberships", json=body)
    assert response.status_code == 200, response.text
    result: dict[str, object] = response.json()
    return result


# ---------------------------------------------------------------------------
# Who may use the screens (spec §3: matrix, not role checks)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("actor_name", ["mcp", "mcd", "admin"])
def test_mc_and_admin_positions_can_list_people(admin: Fixture, actor_name: str) -> None:
    _act_as(actor_name, admin)
    response = admin.client.get("/api/v1/people", params={"search": "test-adm-target"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["rows"][0] == {
        "id": str(admin.target.id),
        "firstName": "Tess",
        "lastName": "Target",
        "email": "test-adm-target@aiesec.net",
        "active": True,
        "status": "active",
        "expaLinked": True,
    }


@pytest.mark.parametrize("actor_name", ["lcp", "nobody"])
def test_everyone_else_is_refused_on_every_endpoint(admin: Fixture, actor_name: str) -> None:
    _act_as(actor_name, admin)
    client = admin.client
    pid = admin.target.id
    mid = admin.target_membership.id
    calls = [
        client.get("/api/v1/people"),
        client.post("/api/v1/people", json={"firstName": "A", "lastName": "B", "email": "x"}),
        client.patch(f"/api/v1/people/{pid}", json={"firstName": "X"}),
        client.post(f"/api/v1/people/{pid}/deactivate"),
        client.post(f"/api/v1/people/{pid}/reactivate"),
        client.post(f"/api/v1/people/{pid}/unlink-expa"),
        client.get(f"/api/v1/people/{pid}/memberships"),
        client.post(f"/api/v1/people/{pid}/memberships", json={}),
        client.patch(f"/api/v1/memberships/{mid}", json={"endDate": TODAY.isoformat()}),
        client.post(f"/api/v1/memberships/{mid}/end", json={"endDate": TODAY.isoformat()}),
    ]
    assert [r.status_code for r in calls] == [403] * len(calls)


def test_list_hides_anonymised_people_and_pages_in_the_query(admin: Fixture) -> None:
    for i in range(3):
        make_person(admin.session, full_name=f"Zed Paged{i}", email=f"test-adm-page{i}@aiesec.net")
    gone = make_person(admin.session, full_name="Gone Person", email="test-adm-gone@aiesec.net")
    gone.status = PersonStatus.ANONYMISED
    admin.session.flush()

    first = admin.client.get(
        "/api/v1/people", params={"search": "test-adm-page", "page": 0, "pageSize": 2}
    ).json()
    second = admin.client.get(
        "/api/v1/people", params={"search": "test-adm-page", "page": 1, "pageSize": 2}
    ).json()
    assert first["total"] == 3
    assert [r["lastName"] for r in first["rows"]] == ["Paged0", "Paged1"]
    assert [r["lastName"] for r in second["rows"]] == ["Paged2"]

    hidden = admin.client.get("/api/v1/people", params={"search": "test-adm-gone"}).json()
    assert hidden["total"] == 0


def test_search_treats_like_wildcards_as_plain_text(admin: Fixture) -> None:
    body = admin.client.get("/api/v1/people", params={"search": "%"}).json()
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# Add a person
# ---------------------------------------------------------------------------


def test_add_person(admin: Fixture) -> None:
    response = admin.client.post(
        "/api/v1/people",
        json={"firstName": " Nina ", "lastName": "New", "email": " Test-Adm-Nina@AIESEC.net "},
    )
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["firstName"] == "Nina"
    assert row["email"] == "test-adm-nina@aiesec.net"
    assert row["active"] is False  # no membership yet
    assert row["status"] == "active"

    entries = _audit(admin.session, "person.create", int(row["id"]))
    assert entries[0].actor_membership_id == admin.actors["mcp"].acting_membership.id  # type: ignore[union-attr]
    _assert_no_personal_data(entries, "Nina", "New", "test-adm-nina")


@pytest.mark.parametrize(
    ("body", "status_code"),
    [
        ({"firstName": "A", "lastName": "B", "email": "TEST-ADM-TARGET@aiesec.net"}, 409),
        ({"firstName": "A", "lastName": "B", "email": "test-adm-x@gmail.com"}, 400),
        ({"firstName": "A", "lastName": "B", "email": "not-an-email"}, 400),
        ({"firstName": " ", "lastName": "B", "email": "test-adm-y@aiesec.net"}, 400),
    ],
)
def test_add_person_refuses_bad_input(
    admin: Fixture, body: dict[str, str], status_code: int
) -> None:
    response = admin.client.post("/api/v1/people", json=body)
    assert response.status_code == status_code, response.text
    assert response.json()["detail"]


# ---------------------------------------------------------------------------
# Edit a person
# ---------------------------------------------------------------------------


def test_edit_person_name_and_email(admin: Fixture) -> None:
    response = admin.client.patch(
        f"/api/v1/people/{admin.target.id}",
        json={"lastName": "Renamed", "email": "test-adm-renamed@aiesec.net"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["firstName"] == "Tess"
    assert response.json()["lastName"] == "Renamed"
    assert admin.target.full_name == "Tess Renamed"
    assert admin.target.aiesec_email == "test-adm-renamed@aiesec.net"

    entries = _audit(admin.session, "person.edit", admin.target.id)
    assert entries[0].diff == {"changed_keys": ["name", "aiesec_email"]}
    _assert_no_personal_data(entries, "Tess", "Renamed", "Target", "test-adm-renamed")


def test_edit_with_no_real_change_writes_no_audit(admin: Fixture) -> None:
    response = admin.client.patch(
        f"/api/v1/people/{admin.target.id}", json={"email": "TEST-ADM-TARGET@aiesec.net"}
    )
    assert response.status_code == 200
    assert _audit(admin.session, "person.edit", admin.target.id) == []


def test_edit_name_keeps_an_email_on_a_retired_domain(admin: Fixture) -> None:
    # An email on a domain that is no longer allowed must not block a name edit.
    admin.target.aiesec_email = "x@old-domain.org"
    admin.session.flush()

    renamed = admin.client.patch(f"/api/v1/people/{admin.target.id}", json={"firstName": "Tessa"})
    assert renamed.status_code == 200, renamed.text
    assert admin.target.aiesec_email == "x@old-domain.org"

    # Sending the same email back in another case is not a change either.
    same = admin.client.patch(
        f"/api/v1/people/{admin.target.id}", json={"email": " X@Old-Domain.org "}
    )
    assert same.status_code == 200, same.text
    assert admin.target.aiesec_email == "x@old-domain.org"
    entries = _audit(admin.session, "person.edit", admin.target.id)
    assert [entry.diff for entry in entries] == [{"changed_keys": ["name"]}]


def test_edit_refuses_an_email_someone_else_has(admin: Fixture) -> None:
    response = admin.client.patch(
        f"/api/v1/people/{admin.target.id}", json={"email": "test-adm-lcp@aiesec.net"}
    )
    assert response.status_code == 409


def test_cannot_edit_someone_who_outranks_you(admin: Fixture) -> None:
    """The email decides who can sign in as someone, so an MCD changing the MCP's
    email would be a takeover. The hierarchy rule (§3.4) refuses it."""
    _act_as("mcd", admin)
    mcp = admin.actors["mcp"].person
    response = admin.client.patch(
        f"/api/v1/people/{mcp.id}", json={"email": "test-adm-takeover@aiesec.net"}
    )
    assert response.status_code == 403
    assert "at or above your own" in response.json()["detail"]
    admin.session.refresh(mcp)
    assert mcp.aiesec_email == "test-adm-mcp@aiesec.net"


def test_a_refused_edit_changes_nothing(admin: Fixture) -> None:
    """All or nothing: the email is taken, so the new last name isn't saved either."""
    response = admin.client.patch(
        f"/api/v1/people/{admin.target.id}",
        json={"lastName": "Halfway", "email": "test-adm-lcp@aiesec.net"},
    )
    assert response.status_code == 409
    admin.session.refresh(admin.target)
    assert admin.target.full_name == "Tess Target"
    assert _audit(admin.session, "person.edit", admin.target.id) == []


def test_an_admin_can_fix_their_own_name(admin: Fixture) -> None:
    me = admin.actors["mcp"].person
    response = admin.client.patch(f"/api/v1/people/{me.id}", json={"lastName": "Fixed"})
    assert response.status_code == 200
    assert me.full_name == "Actor Fixed"


def test_unknown_person_is_404(admin: Fixture) -> None:
    assert admin.client.patch("/api/v1/people/999999", json={"firstName": "X"}).status_code == 404


# ---------------------------------------------------------------------------
# Deactivate / reactivate a person
# ---------------------------------------------------------------------------


def test_deactivate_ends_current_memberships_and_blocks_sign_in(admin: Fixture) -> None:
    response = admin.client.post(f"/api/v1/people/{admin.target.id}/deactivate")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "inactive"
    assert response.json()["active"] is False

    assert admin.target.status == PersonStatus.INACTIVE
    assert admin.target_membership.end_date == YESTERDAY

    # They can't sign in any more: `/me` and every endpoint see "no person".
    user = AuthenticatedUser(subject="test-expa-target", email="test-adm-target@aiesec.net")
    assert get_current_person(user=user, db=admin.session) is None

    person_entries = _audit(admin.session, "person.deactivate", admin.target.id)
    assert person_entries[0].diff == {
        "before": {"status": "ACTIVE"},
        "after": {"status": "INACTIVE"},
        "memberships_ended": [admin.target_membership.id],
        "sessions_revoked": 0,
    }
    end_entries = _audit(admin.session, "membership.end_term", admin.target_membership.id)
    _assert_no_personal_data(person_entries + end_entries, "Tess", "Target", "test-adm-target")


def test_deactivate_revokes_open_sessions(admin: Fixture) -> None:
    # Sign the target in, the way the callback does: pending row, then activate.
    pending, _, _ = create_pending_session(admin.session, ttl_hours=12)
    token = activate_session(
        admin.session, session=pending, person_id=admin.target.id, ttl_hours=12
    )
    admin.session.flush()
    assert get_valid_session(admin.session, token) is not None

    response = admin.client.post(f"/api/v1/people/{admin.target.id}/deactivate")
    assert response.status_code == 200, response.text

    assert get_valid_session(admin.session, token) is None
    entries = _audit(admin.session, "person.deactivate", admin.target.id)
    assert entries[0].diff["sessions_revoked"] == 1


def test_deactivate_keeps_membership_and_kpi_history(admin: Fixture) -> None:
    """Spec §1.5: deactivating never deletes or breaks rows pointing at the person."""
    team = Team(lc_id=admin.lc_a.id, function_id=admin.fn_a.id, term_id=admin.term.id, name="T")
    admin.session.add(team)
    admin.session.flush()
    team_row = TeamMember(
        team_id=team.id,
        membership_id=admin.target_membership.id,
        start_date=admin.target_membership.start_date,
        end_date=None,
    )
    admin.session.add(team_row)
    kpi = make_kpi_attribute(admin.session, key="test_adm_kpi")
    record = record_kpi(
        admin.session,
        attribute=kpi,
        membership_id=admin.target_membership.id,
        value_number=5,
        period_start=TODAY - timedelta(days=30),
        period_end=TODAY - timedelta(days=1),
        source=KpiSource.LEADER,
        recorded_by_membership_id=admin.target_membership.id,
    )
    past = make_membership(
        admin.session,
        person=admin.target,
        lc=admin.lc_a,
        position=admin.positions["member"],
        function=admin.fn_b,
        term=admin.term,
        start=TODAY - timedelta(days=190),
        end=TODAY - timedelta(days=150),
    )

    def count(model: type[Membership] | type[KpiRecord]) -> int:
        return admin.session.execute(select(func.count()).select_from(model)).scalar_one()

    before = (count(Membership), count(KpiRecord))
    assert admin.client.post(f"/api/v1/people/{admin.target.id}/deactivate").status_code == 200

    assert (count(Membership), count(KpiRecord)) == before
    assert admin.session.get(KpiRecord, record.id) is not None
    assert record.membership_id == admin.target_membership.id
    assert record.value_number == 5
    # A membership that had already ended is history: untouched.
    assert past.end_date == TODAY - timedelta(days=150)
    # The team row ends with the membership, rather than outliving it.
    assert team_row.end_date == YESTERDAY


def test_deactivate_a_membership_that_started_today_ends_it_today(admin: Fixture) -> None:
    new = make_person(admin.session, email="test-adm-starter@aiesec.net")
    m = make_membership(
        admin.session,
        person=new,
        lc=admin.lc_a,
        position=admin.positions["member"],
        term=admin.term,
        start=TODAY,
        end=TODAY + timedelta(days=30),
    )
    assert admin.client.post(f"/api/v1/people/{new.id}/deactivate").status_code == 200
    assert m.end_date == TODAY  # can't end before it began


def _future_membership_for_target(fx: Fixture) -> Membership:
    """A membership in LC B that starts in 30 days (the target's other one is in LC A)."""
    return make_membership(
        fx.session,
        person=fx.target,
        lc=fx.lc_b,
        position=fx.positions["member"],
        term=fx.term,
        start=TODAY + timedelta(days=30),
        end=TODAY + timedelta(days=120),
    )


def _counts_as_member(fx: Fixture, ref_date: date) -> tuple[bool, bool, bool]:
    """Ask the three "who is a member now" questions on `ref_date`."""
    contexts = [
        membership_repo.build_membership_context(fx.session, m)
        for m in fx.actors["mcp"].active_memberships
    ]
    summary = membership_repo.list_members_summary(fx.session, contexts, as_of=ref_date)
    in_directory = any(row["personId"] == str(fx.target.id) for row in summary["rows"])
    has_active = bool(
        membership_repo.get_active_memberships_for_person(fx.session, fx.target.id, as_of=ref_date)
    )
    row = admin_people_repo.get_person_row(fx.session, fx.target.id, today=ref_date)
    return has_active, in_directory, row["active"]


def test_deactivated_persons_future_membership_never_counts(admin: Fixture) -> None:
    _future_membership_for_target(admin)
    assert admin.client.post(f"/api/v1/people/{admin.target.id}/deactivate").status_code == 200

    # The future membership is kept, but once its start date arrives it must not count.
    assert _counts_as_member(admin, TODAY + timedelta(days=31)) == (False, False, False)


def test_reactivation_makes_a_kept_future_membership_count_again(admin: Fixture) -> None:
    _future_membership_for_target(admin)
    assert admin.client.post(f"/api/v1/people/{admin.target.id}/deactivate").status_code == 200
    assert admin.client.post(f"/api/v1/people/{admin.target.id}/reactivate").status_code == 200

    assert _counts_as_member(admin, TODAY + timedelta(days=31)) == (True, True, True)


def test_membership_that_started_today_does_not_count_after_deactivation(
    admin: Fixture,
) -> None:
    new = make_person(admin.session, email="test-adm-today@aiesec.net")
    make_membership(
        admin.session,
        person=new,
        lc=admin.lc_a,
        position=admin.positions["member"],
        term=admin.term,
        start=TODAY,
        end=TODAY + timedelta(days=30),
    )
    assert admin.client.post(f"/api/v1/people/{new.id}/deactivate").status_code == 200

    assert (
        membership_repo.get_active_memberships_for_person(admin.session, new.id, as_of=TODAY) == []
    )
    assert admin_people_repo.get_person_row(admin.session, new.id, today=TODAY)["active"] is False


def test_membership_list_does_not_mark_a_deactivated_persons_membership_current(
    admin: Fixture,
) -> None:
    _future_membership_for_target(admin)
    assert admin.client.post(f"/api/v1/people/{admin.target.id}/deactivate").status_code == 200

    # 31 days on, the kept membership's dates cover the day, but the person is deactivated.
    rows = admin_people_repo.list_person_memberships(
        admin.session, admin.target.id, today=TODAY + timedelta(days=31)
    )
    assert [r["current"] for r in rows] == [False, False]

    assert admin.client.post(f"/api/v1/people/{admin.target.id}/reactivate").status_code == 200
    rows = admin_people_repo.list_person_memberships(
        admin.session, admin.target.id, today=TODAY + timedelta(days=31)
    )
    assert rows[0]["current"] is True  # newest first: the kept future one


def test_alumnus_with_a_current_membership_counts(admin: Fixture) -> None:
    admin.target.status = PersonStatus.ALUMNUS
    admin.session.flush()

    assert _counts_as_member(admin, TODAY) == (True, True, True)


def test_cannot_deactivate_yourself_or_someone_who_outranks_you(admin: Fixture) -> None:
    me = admin.actors["mcd"].person
    _act_as("mcd", admin)
    own = admin.client.post(f"/api/v1/people/{me.id}/deactivate")
    assert own.status_code == 403
    assert "your own record" in own.json()["detail"]

    mcp = admin.actors["mcp"].person
    higher = admin.client.post(f"/api/v1/people/{mcp.id}/deactivate")
    assert higher.status_code == 403
    assert "at or above your own" in higher.json()["detail"]
    admin.session.refresh(mcp)
    assert mcp.status == PersonStatus.ACTIVE


def test_deactivate_twice_is_refused(admin: Fixture) -> None:
    assert admin.client.post(f"/api/v1/people/{admin.target.id}/deactivate").status_code == 200
    second = admin.client.post(f"/api/v1/people/{admin.target.id}/deactivate")
    assert second.status_code == 400
    assert "already" in second.json()["detail"]


def test_reactivate_restores_status_but_not_memberships(admin: Fixture) -> None:
    admin.client.post(f"/api/v1/people/{admin.target.id}/deactivate")
    response = admin.client.post(f"/api/v1/people/{admin.target.id}/reactivate")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"
    assert response.json()["active"] is False
    assert admin.target_membership.end_date == YESTERDAY
    assert _audit(admin.session, "person.reactivate", admin.target.id)


def test_reactivate_an_active_person_is_refused(admin: Fixture) -> None:
    assert admin.client.post(f"/api/v1/people/{admin.target.id}/reactivate").status_code == 400


def test_main_app_add_member_cannot_bring_back_a_deactivated_person(admin: Fixture) -> None:
    """Only Reactivate undoes a deactivation, so the Membership summary's Add member
    (an LCP adding by email) is refused."""
    admin.target.status = PersonStatus.INACTIVE
    admin.session.flush()
    lcp = admin.actors["lcp"]
    contexts = [
        membership_repo.build_membership_context(admin.session, m) for m in lcp.active_memberships
    ]
    result = membership_repo.add_member(
        admin.session,
        contexts,
        email="test-adm-target@aiesec.net",
        lc_id=admin.lc_a.id,
        position_key="member",
        function_key=admin.fn_b.key,
        start_date=TODAY,
        end_date=TODAY + timedelta(days=30),
        confirmed_existing=True,
    )
    assert result == {
        "status": "rejected",
        "message": "This person can't be added. Contact your MC.",
    }


# ---------------------------------------------------------------------------
# Memberships: list and assign
# ---------------------------------------------------------------------------


def test_list_person_memberships(admin: Fixture) -> None:
    old = make_membership(
        admin.session,
        person=admin.target,
        lc=admin.lc_a,
        position=admin.positions["member"],
        function=admin.fn_b,
        term=admin.term,
        start=TODAY - timedelta(days=190),
        end=TODAY - timedelta(days=150),
    )
    rows = admin.client.get(f"/api/v1/people/{admin.target.id}/memberships").json()
    assert [r["id"] for r in rows] == [str(admin.target_membership.id), str(old.id)]
    assert rows[0]["current"] is True
    assert rows[1]["current"] is False
    assert rows[0]["lc"] == {"id": str(admin.lc_a.id), "name": "test-admin-lc-a", "type": "lc"}
    assert rows[0]["position"]["key"] == "member"
    assert rows[0]["function"] == {"key": "test_admin_fn_a", "label": "Function A"}


def test_assign_in_any_lc_and_transfer_ends_the_old_lc(admin: Fixture) -> None:
    """An admin isn't limited to their own LC (DEV-47). Assigning to another LC is a
    transfer: the old LC's membership ends the day before (§5.1)."""
    start = TODAY + timedelta(days=10)
    result = _assign(admin, admin.target.id, startDate=start.isoformat())
    assert result["status"] == "ok", result

    # A fresh select proves the row was saved, not just returned.
    new = admin.session.scalars(
        select(Membership).where(Membership.id == int(str(result["membershipId"])))
    ).one()
    assert (new.lc_id, new.function_id, new.start_date) == (admin.lc_b.id, admin.fn_b.id, start)
    assert admin.target_membership.end_date == start - timedelta(days=1)

    created = _audit(admin.session, "membership.create", new.id)
    ended = _audit(admin.session, "membership.end_term", admin.target_membership.id)
    assert ended[0].diff == {
        "before": str(TODAY + timedelta(days=100)),
        "after": str(start - timedelta(days=1)),
    }
    _assert_no_personal_data(created + ended, "Tess", "Target", "test-adm-target")


def test_assign_another_function_in_the_same_lc_ends_nothing(admin: Fixture) -> None:
    result = _assign(admin, admin.target.id, lcId=admin.lc_a.id)
    assert result["status"] == "ok", result
    assert admin.target_membership.end_date == TODAY + timedelta(days=100)


def test_transfer_ends_old_team_rows(admin: Fixture) -> None:
    """A transfer ends the old membership, so its open team row must end with it."""
    team = Team(lc_id=admin.lc_a.id, function_id=admin.fn_a.id, term_id=admin.term.id, name="T")
    admin.session.add(team)
    admin.session.flush()
    team_row = TeamMember(
        team_id=team.id,
        membership_id=admin.target_membership.id,
        start_date=admin.target_membership.start_date,
        end_date=None,
    )
    admin.session.add(team_row)
    admin.session.flush()

    start = TODAY + timedelta(days=10)
    result = _assign(admin, admin.target.id, startDate=start.isoformat())
    assert result["status"] == "ok", result
    assert team_row.end_date == TODAY + timedelta(days=9)


def test_end_team_rows_never_leaves_a_future_row_outside(admin: Fixture) -> None:
    """A team row that starts after the new end date ends on its own start date."""
    team = Team(lc_id=admin.lc_a.id, function_id=admin.fn_a.id, term_id=admin.term.id, name="T")
    admin.session.add(team)
    admin.session.flush()
    row_start = TODAY + timedelta(days=20)
    team_row = TeamMember(
        team_id=team.id,
        membership_id=admin.target_membership.id,
        start_date=row_start,
        end_date=None,
    )
    admin.session.add(team_row)
    admin.session.flush()

    membership_repo.end_team_rows(
        admin.session,
        membership_id=admin.target_membership.id,
        end_date=TODAY + timedelta(days=10),
    )
    assert team_row.end_date == row_start


def test_assign_allowed_when_it_ends_before_another_lc_membership_starts(admin: Fixture) -> None:
    """A back-to-back transfer doesn't overlap, so it is valid and touches nothing else."""
    later_start = TODAY + timedelta(days=200)
    later = make_membership(
        admin.session,
        person=admin.target,
        lc=admin.lc_b,
        position=admin.positions["member"],
        function=admin.fn_b,
        term=admin.term,
        start=later_start,
        end=later_start + timedelta(days=100),
    )
    target_end = admin.target_membership.end_date

    result = _assign(
        admin,
        admin.target.id,
        lcId=admin.lc_a.id,
        functionKey=admin.fn_b.key,
        startDate=(TODAY + timedelta(days=110)).isoformat(),
        endDate=(later_start - timedelta(days=1)).isoformat(),
    )

    assert result["status"] == "ok", result
    assert (later.start_date, later.end_date) == (later_start, later_start + timedelta(days=100))
    assert admin.target_membership.end_date == target_end
    assert _audit(admin.session, "membership.end_term", later.id) == []


def test_correct_still_works_after_a_transfer(admin: Fixture) -> None:
    """After a transfer, the old LC's membership can still be corrected."""
    start = TODAY + timedelta(days=10)
    assert _assign(admin, admin.target.id, startDate=start.isoformat())["status"] == "ok"
    old = admin.target_membership
    assert old.end_date == start - timedelta(days=1)

    result = _correct(
        admin,
        old.id,
        startDate=(TODAY - timedelta(days=120)).isoformat(),
        endDate=old.end_date.isoformat() if old.end_date else None,
    )
    assert result["status"] == "ok", result
    assert old.start_date == TODAY - timedelta(days=120)


def test_assign_refused_when_another_lc_membership_has_not_started(admin: Fixture) -> None:
    make_membership(
        admin.session,
        person=admin.target,
        lc=admin.lc_b,
        position=admin.positions["member"],
        function=admin.fn_b,
        term=admin.term,
        start=TODAY + timedelta(days=20),
        end=TODAY + timedelta(days=120),
    )
    memberships_before = admin.session.execute(
        select(func.count()).select_from(Membership)
    ).scalar_one()
    audits_before = admin.session.execute(select(func.count()).select_from(AuditLog)).scalar_one()

    result = _assign(
        admin,
        admin.target.id,
        lcId=admin.lc_a.id,
        functionKey=admin.fn_b.key,
        startDate=(TODAY + timedelta(days=5)).isoformat(),
    )

    assert result["status"] == "rejected", result
    message = str(result["message"])
    assert "test-admin-lc-b" in message
    assert (TODAY + timedelta(days=20)).strftime("%d %b %Y") in message
    assert (
        admin.session.execute(select(func.count()).select_from(Membership)).scalar_one()
        == memberships_before
    )
    assert (
        admin.session.execute(select(func.count()).select_from(AuditLog)).scalar_one()
        == audits_before
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"positionKey": "mcd"}, "can't be used in an LC"),  # §3.6 level match
        ({"lcId": -1}, "LC not found"),
        ({"positionKey": "no_such_position"}, "position"),
        ({"functionKey": "no_such_function"}, "function"),
        ({"endDate": (TODAY - timedelta(days=5)).isoformat()}, "end date"),
    ],
)
def test_assign_refuses_bad_input(
    admin: Fixture, overrides: dict[str, object], message: str
) -> None:
    result = _assign(admin, admin.target.id, **overrides)
    assert result["status"] == "rejected"
    assert message in str(result["message"])


def test_assign_refuses_a_term_that_does_not_cover_the_start(admin: Fixture) -> None:
    old_term = make_term(
        admin.session,
        name="test-admin-old-term",
        start=TODAY - timedelta(days=400),
        end=TODAY - timedelta(days=300),
    )
    result = _assign(admin, admin.target.id, termId=old_term.id)
    assert result["status"] == "rejected"
    assert result["message"] == "The start date isn't inside the chosen term."


def test_assign_refuses_an_lc_position_in_the_mc(admin: Fixture) -> None:
    result = _assign(admin, admin.target.id, lcId=admin.mc.id, positionKey="member")
    assert result["status"] == "rejected"
    assert "can't be used in the MC" in str(result["message"])


def test_assign_refuses_same_function_twice_in_one_lc(admin: Fixture) -> None:
    result = _assign(admin, admin.target.id, lcId=admin.lc_a.id, functionKey=admin.fn_a.key)
    assert result["status"] == "rejected"
    assert "already holds that function" in str(result["message"])


def test_assign_refuses_an_lc_membership_while_an_mc_one_overlaps(admin: Fixture) -> None:
    mcd = admin.actors["mcd"].person
    result = _assign(admin, mcd.id)
    assert result == {
        "status": "rejected",
        "message": "This person can't be added. Contact your MC.",
        "membershipId": None,
    }


def test_assign_follows_the_hierarchy_rule(admin: Fixture) -> None:
    _act_as("mcd", admin)
    # Below your rank: fine.
    assert _assign(admin, admin.target.id)["status"] == "ok"
    # At or above your rank: refused.
    other = make_person(admin.session, email="test-adm-promote@aiesec.net")
    higher = _assign(admin, other.id, lcId=admin.mc.id, positionKey="mcvp", functionKey=None)
    assert higher["status"] == "rejected"
    assert "at or above your own" in str(higher["message"])
    # Yourself: refused.
    me = admin.actors["mcd"].person
    own = _assign(admin, me.id, lcId=admin.mc.id, positionKey="mcd", functionKey=None)
    assert own["status"] == "rejected"


def test_president_exception_lets_an_mcp_add_another_mcp(admin: Fixture) -> None:
    successor = make_person(admin.session, email="test-adm-successor@aiesec.net")
    result = _assign(admin, successor.id, lcId=admin.mc.id, positionKey="mcp", functionKey=None)
    assert result["status"] == "ok", result


def test_assign_refuses_a_deactivated_person(admin: Fixture) -> None:
    admin.target.status = PersonStatus.INACTIVE
    admin.session.flush()
    result = _assign(admin, admin.target.id)
    assert result["status"] == "rejected"
    assert "Reactivate" in str(result["message"])


def test_correct_refuses_a_deactivated_person(admin: Fixture) -> None:
    ended = admin.target_membership
    assert admin.client.post(f"/api/v1/people/{admin.target.id}/deactivate").status_code == 200
    result = _correct(admin, ended.id, endDate=(TODAY + timedelta(days=60)).isoformat())
    assert result["status"] == "rejected"
    assert "Reactivate" in str(result["message"])
    admin.session.refresh(ended)
    assert ended.end_date != TODAY + timedelta(days=60)  # ended memberships stay ended


def test_assign_to_unknown_person_is_404(admin: Fixture) -> None:
    body = {
        "lcId": admin.lc_b.id,
        "positionKey": "member",
        "startDate": TODAY.isoformat(),
        "endDate": TODAY.isoformat(),
    }
    assert admin.client.post("/api/v1/people/999999/memberships", json=body).status_code == 404


# ---------------------------------------------------------------------------
# Memberships: correct
# ---------------------------------------------------------------------------


def _correct(fx: Fixture, membership_id: int, **body: object) -> dict[str, object]:
    response = fx.client.patch(f"/api/v1/memberships/{membership_id}", json=body)
    assert response.status_code == 200, response.text
    result: dict[str, object] = response.json()
    return result


def test_correct_position_function_and_dates(admin: Fixture) -> None:
    m = admin.target_membership
    new_start = TODAY - timedelta(days=90)
    new_end = TODAY + timedelta(days=120)
    result = _correct(
        admin,
        m.id,
        positionKey="lcvp",
        functionKey=admin.fn_b.key,
        startDate=new_start.isoformat(),
        endDate=new_end.isoformat(),
    )
    assert result["status"] == "ok", result
    assert (m.position_id, m.function_id) == (admin.positions["lcvp"].id, admin.fn_b.id)
    assert (m.start_date, m.end_date) == (new_start, new_end)

    entries = _audit(admin.session, "membership.correct", m.id)
    assert entries[0].diff == {
        "before": {
            "position_id": admin.positions["member"].id,
            "function_id": admin.fn_a.id,
            "start_date": str(TODAY - timedelta(days=100)),
            "end_date": str(TODAY + timedelta(days=100)),
        },
        "after": {
            "position_id": admin.positions["lcvp"].id,
            "function_id": admin.fn_b.id,
            "start_date": str(new_start),
            "end_date": str(new_end),
        },
    }
    _assert_no_personal_data(entries, "Tess", "Target", "test-adm-target")


def test_correct_with_nothing_changed_writes_no_audit(admin: Fixture) -> None:
    assert _correct(admin, admin.target_membership.id, positionKey="member")["status"] == "ok"
    assert _audit(admin.session, "membership.correct", admin.target_membership.id) == []


def test_correct_can_remove_the_function_but_leaving_it_out_keeps_it(admin: Fixture) -> None:
    m = admin.target_membership
    _correct(admin, m.id, endDate=(TODAY + timedelta(days=50)).isoformat())
    assert m.function_id == admin.fn_a.id
    _correct(admin, m.id, functionKey=None)
    assert m.function_id is None


def test_correct_refuses_a_position_at_or_above_your_own(admin: Fixture) -> None:
    _act_as("mcd", admin)
    result = _correct(admin, admin.target_membership.id, positionKey="lcp")
    assert result["status"] == "ok"  # LCP (4) is below MCD (5)
    mcp_membership = admin.actors["mcp"].acting_membership
    assert mcp_membership is not None
    refused = _correct(admin, mcp_membership.id, endDate=TODAY.isoformat())
    assert refused["status"] == "rejected"


def test_correct_keeps_the_level_rule(admin: Fixture) -> None:
    result = _correct(admin, admin.target_membership.id, positionKey="mcvp")
    assert result["status"] == "rejected"
    assert "can't be used in an LC" in str(result["message"])


def test_correct_refuses_a_function_change_once_the_membership_had_a_team(admin: Fixture) -> None:
    team = Team(lc_id=admin.lc_a.id, function_id=admin.fn_a.id, term_id=admin.term.id, name="T")
    admin.session.add(team)
    admin.session.flush()
    admin.session.add(
        TeamMember(team_id=team.id, membership_id=admin.target_membership.id, start_date=TODAY)
    )
    admin.session.flush()
    result = _correct(admin, admin.target_membership.id, functionKey=admin.fn_b.key)
    assert result["status"] == "rejected"
    assert "team" in str(result["message"])


def test_correct_refuses_dates_that_overlap_another_lc(admin: Fixture) -> None:
    make_membership(
        admin.session,
        person=admin.target,
        lc=admin.lc_b,
        position=admin.positions["member"],
        term=admin.term,
        start=TODAY + timedelta(days=101),
        end=TODAY + timedelta(days=150),
    )
    result = _correct(
        admin, admin.target_membership.id, endDate=(TODAY + timedelta(days=120)).isoformat()
    )
    assert result["status"] == "rejected"
    assert "another LC" in str(result["message"])


def _add_team_row(admin: Fixture, *, start: date, end: date | None) -> TeamMember:
    team = Team(lc_id=admin.lc_a.id, function_id=admin.fn_a.id, term_id=admin.term.id, name="T")
    admin.session.add(team)
    admin.session.flush()
    row = TeamMember(
        team_id=team.id,
        membership_id=admin.target_membership.id,
        start_date=start,
        end_date=end,
    )
    admin.session.add(row)
    admin.session.flush()
    return row


def test_correct_start_later_moves_team_row_start(admin: Fixture) -> None:
    m = admin.target_membership
    row = _add_team_row(admin, start=m.start_date, end=None)
    new_start = TODAY + timedelta(days=30)
    result = _correct(admin, m.id, startDate=new_start.isoformat())
    assert result["status"] == "ok", result
    assert m.start_date == new_start
    assert row.start_date == new_start


def test_correct_start_after_a_team_row_ended_is_refused(admin: Fixture) -> None:
    m = admin.target_membership
    old_start = m.start_date
    row = _add_team_row(admin, start=m.start_date, end=TODAY + timedelta(days=10))
    result = _correct(admin, m.id, startDate=(TODAY + timedelta(days=30)).isoformat())
    assert result["status"] == "rejected"
    assert "team" in str(result["message"])
    # Refused before anything was written.
    assert m.start_date == old_start
    assert row.start_date == old_start


def test_correct_refuses_an_end_before_the_start(admin: Fixture) -> None:
    result = _correct(
        admin, admin.target_membership.id, endDate=(TODAY - timedelta(days=150)).isoformat()
    )
    assert result["status"] == "rejected"


def test_correct_unknown_membership(admin: Fixture) -> None:
    result = _correct(admin, 999999, endDate=TODAY.isoformat())
    assert result == {
        "status": "rejected",
        "message": "Membership not found.",
        "membershipId": None,
    }


# ---------------------------------------------------------------------------
# Memberships: end
# ---------------------------------------------------------------------------


def _end(fx: Fixture, membership_id: int, end_date: date) -> dict[str, object]:
    response = fx.client.post(
        f"/api/v1/memberships/{membership_id}/end", json={"endDate": end_date.isoformat()}
    )
    assert response.status_code == 200, response.text
    result: dict[str, object] = response.json()
    return result


def test_end_a_membership_early(admin: Fixture) -> None:
    m = admin.target_membership
    assert _end(admin, m.id, TODAY)["status"] == "ok"
    assert m.end_date == TODAY
    entries = _audit(admin.session, "membership.end_term", m.id)
    assert entries[0].diff == {"before": str(TODAY + timedelta(days=100)), "after": str(TODAY)}


@pytest.mark.parametrize(
    ("days", "message"),
    [
        (-150, "before it started"),
        (100, "before the current end date"),
        (200, "before the current"),
    ],
)
def test_end_refuses_dates_outside_the_membership(admin: Fixture, days: int, message: str) -> None:
    result = _end(admin, admin.target_membership.id, TODAY + timedelta(days=days))
    assert result["status"] == "rejected"
    assert message in str(result["message"])


# ---------------------------------------------------------------------------
# EXPA link status and unlink
# ---------------------------------------------------------------------------


def test_person_row_shows_expa_link(admin: Fixture) -> None:
    linked = admin.client.get(f"/api/v1/people?search={admin.target.aiesec_email}").json()
    assert linked["rows"][0]["expaLinked"] is True

    admin.target.expa_id = None
    admin.session.flush()
    unlinked = admin.client.get(f"/api/v1/people?search={admin.target.aiesec_email}").json()
    assert unlinked["rows"][0]["expaLinked"] is False


def test_unlink_expa_clears_id_revokes_sessions_and_audits(admin: Fixture) -> None:
    pending, _, _ = create_pending_session(admin.session, ttl_hours=12)
    token = activate_session(
        admin.session, session=pending, person_id=admin.target.id, ttl_hours=12
    )
    admin.session.flush()
    expa_id = admin.target.expa_id
    assert expa_id

    response = admin.client.post(f"/api/v1/people/{admin.target.id}/unlink-expa")
    assert response.status_code == 200, response.text
    assert response.json()["expaLinked"] is False

    admin.session.refresh(admin.target)
    assert admin.target.expa_id is None
    assert get_valid_session(admin.session, token) is None

    entries = _audit(admin.session, "person.unlink_expa", admin.target.id)
    assert len(entries) == 1
    assert entries[0].diff == {
        "before": {"expaLinked": True},
        "after": {"expaLinked": False},
        "sessions_revoked": 1,
    }
    _assert_no_personal_data(entries, "Tess", "Target", "test-adm-target", expa_id)


def test_unlink_expa_refuses_unlinked_self_and_outranking(admin: Fixture) -> None:
    # Not linked.
    admin.target.expa_id = None
    admin.session.flush()
    unlinked = admin.client.post(f"/api/v1/people/{admin.target.id}/unlink-expa")
    assert unlinked.status_code == 400
    assert unlinked.json()["detail"] == "This person isn't linked to EXPA."

    # Yourself, and someone who outranks you.
    _act_as("mcd", admin)
    me = admin.actors["mcd"].person
    mcp = admin.actors["mcp"].person
    me.expa_id = "test-expa-me"
    mcp.expa_id = "test-expa-mcp"
    admin.session.flush()

    own = admin.client.post(f"/api/v1/people/{me.id}/unlink-expa")
    assert own.status_code == 403
    assert "your own record" in own.json()["detail"]

    higher = admin.client.post(f"/api/v1/people/{mcp.id}/unlink-expa")
    assert higher.status_code == 403
    assert "at or above your own" in higher.json()["detail"]
    admin.session.refresh(mcp)
    assert mcp.expa_id == "test-expa-mcp"

    missing = admin.client.post("/api/v1/people/999999999/unlink-expa")
    assert missing.status_code == 404


def test_create_and_patch_cannot_set_expa_id(admin: Fixture) -> None:
    created = admin.client.post(
        "/api/v1/people",
        json={"firstName": "A", "lastName": "B", "email": "test-adm-x@aiesec.net", "expaId": "9"},
    )
    assert created.status_code == 422

    patched = admin.client.patch(
        f"/api/v1/people/{admin.target.id}", json={"firstName": "X", "expaId": "9"}
    )
    assert patched.status_code == 422
    admin.session.refresh(admin.target)
    assert admin.target.expa_id == "test-expa-target"
