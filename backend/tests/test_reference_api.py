"""Tests for `GET /api/v1/reference/membership-options` (DEV-0043).

The endpoint gives the frontend real database ids for the LCs, terms and teams that
the Add member and Membership pages offer. Before it existed those came from the
browser-side mock, so their ids were slugs the backend could not accept.

Who may call it: a signed-in caller who matches a `person` here (`CurrentActor`).
Any aiesec.net account worldwide can sign in, so someone who isn't one of our people
must not see our teams or their leaders' names. Signing in does not depend on this
endpoint (the frontend takes positions from elsewhere), so an unallocated person
still reaches the "not allocated" page (spec §9).

Like the other API tests, these never hard-code primary keys and use `test_`-prefixed
rows, so they pass on an empty CI database and on a seeded local one.
"""

from collections.abc import Generator
from dataclasses import dataclass
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import (
    CurrentActor,
    get_current_actor,
    get_current_user,
    get_db,
    get_token_verifier,
)
from app.core.auth import AuthenticatedUser
from app.main import app
from app.models.membership import Membership, Team
from app.models.org import LC, Function, LCType, Term
from app.models.person import Person
from tests.helpers import (
    make_function,
    make_lc,
    make_membership,
    make_person,
    make_position,
    make_team,
    make_term,
)

URL = "/api/v1/reference/membership-options"


@dataclass
class Seeded:
    lc: LC
    mc: LC
    inactive_lc: LC
    term: Term
    led_team: Team
    unled_team: Team
    leader: Membership
    leader_person: Person


@pytest.fixture
def seeded(db_session: Session) -> Seeded:
    lc = make_lc(db_session, name="test_ref_usyd", state="NSW")
    mc = make_lc(db_session, name="test_ref_mc", lc_type=LCType.MC)
    inactive_lc = make_lc(db_session, name="test_ref_closed")
    inactive_lc.active = False
    term = make_term(db_session, name="test_ref_term")
    ogv = make_function(db_session, key="test_ref_ogv", label="oGV")
    bnm = make_function(db_session, key="test_ref_bnm", label="BnM")
    leader_person = make_person(db_session, full_name="Jane Leader", email="test_ref_tl@aiesec.net")
    position = make_position(db_session, key="test_ref_tl", label="Team Leader", rank=3)
    leader = make_membership(
        db_session, person=leader_person, lc=lc, position=position, term=term, function=ogv
    )
    led_team = make_team(db_session, lc=lc, function=ogv, term=term, name="test_ref_ogv_a")
    led_team.leader_membership_id = leader.id
    unled_team = make_team(db_session, lc=lc, function=bnm, term=term, name="test_ref_bnm_a")
    make_team(db_session, lc=inactive_lc, function=ogv, term=term, name="test_ref_closed_team")
    db_session.flush()
    return Seeded(lc, mc, inactive_lc, term, led_team, unled_team, leader, leader_person)


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    # Signed in as one of our people (the actor's own memberships don't matter here).
    actor = CurrentActor(
        person=make_person(db_session, email="test_ref_actor@aiesec.net"),
        active_memberships=[],
        acting_membership=None,
    )
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_actor] = lambda: actor
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_options_are_open_to_any_of_our_people(client: TestClient) -> None:
    assert client.get(URL).status_code == 200


def test_options_reject_a_signed_in_account_that_is_not_one_of_our_people(
    client: TestClient,
) -> None:
    # A valid aiesec.net token whose email matches no `person` row.
    del app.dependency_overrides[get_current_actor]
    user = AuthenticatedUser(subject="test-sub", email="test_ref_outsider@aiesec.net")
    app.dependency_overrides[get_current_user] = lambda: user

    assert client.get(URL).status_code == 401


def test_options_reject_anonymous(client: TestClient) -> None:
    del app.dependency_overrides[get_current_actor]

    def no_verification_expected() -> object:
        class Verifier:
            def verify(self, token: str) -> AuthenticatedUser:
                raise AssertionError("Verifier should not run without credentials")

        return Verifier()

    app.dependency_overrides[get_token_verifier] = no_verification_expected

    assert client.get(URL).status_code == 401


def test_options_return_ids_as_strings_in_frontend_shape(
    client: TestClient, seeded: Seeded
) -> None:
    body = client.get(URL).json()

    team = next(t for t in body["teams"] if t["name"] == "test_ref_ogv_a")
    assert team == {
        "id": str(seeded.led_team.id),
        "name": "test_ref_ogv_a",
        "lcId": str(seeded.lc.id),
        "functionKey": "test_ref_ogv",
        "leader": {"membershipId": str(seeded.leader.id), "name": "Jane Leader"},
    }
    lc = next(item for item in body["lcs"] if item["id"] == str(seeded.lc.id))
    assert lc == {
        "id": str(seeded.lc.id),
        "name": "test_ref_usyd",
        "type": "lc",
        "state": "NSW",
        "active": True,
    }
    mc = next(item for item in body["lcs"] if item["id"] == str(seeded.mc.id))
    assert mc["type"] == "mc"
    term = next(t for t in body["terms"] if t["id"] == str(seeded.term.id))
    assert term == {
        "id": str(seeded.term.id),
        "name": "test_ref_term",
        "startDate": seeded.term.start_date.isoformat(),
        "endDate": seeded.term.end_date.isoformat(),
    }


def test_options_exclude_inactive_lcs_and_their_teams(client: TestClient, seeded: Seeded) -> None:
    body = client.get(URL).json()

    assert str(seeded.inactive_lc.id) not in {lc["id"] for lc in body["lcs"]}
    assert str(seeded.inactive_lc.id) not in {t["lcId"] for t in body["teams"]}


def test_team_without_leader_has_null_leader(client: TestClient, seeded: Seeded) -> None:
    body = client.get(URL).json()

    assert next(t for t in body["teams"] if t["name"] == "test_ref_bnm_a")["leader"] is None


def test_options_leave_out_teams_whose_term_has_ended(
    client: TestClient, seeded: Seeded, db_session: Session
) -> None:
    # After a term rollover the old "oGV Team A" still exists. Offering it next to the
    # new one (same name) would let someone add a member to last term's team.
    past = make_term(
        db_session,
        name="test_ref_past_term",
        start=date.today() - timedelta(days=400),
        end=date.today() - timedelta(days=1),
    )
    ogv = db_session.get(Function, seeded.led_team.function_id)
    assert ogv is not None
    old_team = make_team(db_session, lc=seeded.lc, function=ogv, term=past, name="test_ref_ogv_old")

    body = client.get(URL).json()

    team_ids = {t["id"] for t in body["teams"]}
    assert str(old_team.id) not in team_ids
    assert str(seeded.led_team.id) in team_ids
