from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.kpi import KpiRecord, KpiSource
from app.models.membership import Membership, Team, TeamMember
from app.models.org import LCType
from app.models.privacy import AuditLog
from app.repositories.kpi import record_kpi
from app.repositories.lc import (
    LC_DEFAULT_TIMEZONE,
    activate_lc,
    create_lc,
    deactivate_lc,
    get_lc,
    list_lcs,
    merge_lcs,
    refresh_person_timezone,
    rename_lc,
    resolve_timezone,
    set_lc_state,
)
from tests.helpers import (
    TODAY,
    YEAR_AGO,
    YEAR_AHEAD,
    make_function,
    make_kpi_attribute,
    make_lc,
    make_membership,
    make_person,
    make_position,
    make_state_timezone,
    make_team,
    make_term,
)


def test_list_lcs_returns_active_only_by_default(db_session: Session) -> None:
    active = make_lc(db_session, name="Active LC")
    inactive = make_lc(db_session, name="Inactive LC")
    inactive.active = False
    db_session.flush()

    result = list_lcs(db_session)

    ids = [lc.id for lc in result]
    assert active.id in ids
    assert inactive.id not in ids


def test_list_lcs_include_inactive(db_session: Session) -> None:
    active = make_lc(db_session, name="Active LC")
    inactive = make_lc(db_session, name="Inactive LC")
    inactive.active = False
    db_session.flush()

    result = list_lcs(db_session, include_inactive=True)

    ids = [lc.id for lc in result]
    assert active.id in ids
    assert inactive.id in ids


def test_get_lc_returns_lc(db_session: Session) -> None:
    lc = make_lc(db_session)
    assert get_lc(db_session, lc.id) is lc


def test_get_lc_returns_none_for_unknown_id(db_session: Session) -> None:
    assert get_lc(db_session, 999999) is None


def test_resolve_timezone_uses_state_timezone_lookup(db_session: Session) -> None:
    make_state_timezone(db_session, state="NSW", timezone="Australia/Sydney")
    lc = make_lc(db_session)
    lc.state = "NSW"
    db_session.flush()

    assert resolve_timezone(db_session, lc_id=lc.id) == "Australia/Sydney"


def test_resolve_timezone_defaults_when_no_state(db_session: Session) -> None:
    lc = make_lc(db_session)
    # lc.state is None — no state set

    assert resolve_timezone(db_session, lc_id=lc.id) == LC_DEFAULT_TIMEZONE


def test_create_lc_inserts_row(db_session: Session) -> None:
    lc = create_lc(db_session, name="AIESEC in Newtown", lc_type=LCType.LC)
    assert lc.id is not None
    assert lc.name == "AIESEC in Newtown"
    assert lc.active is True
    assert lc.state is None


def test_create_lc_with_state(db_session: Session) -> None:
    lc = create_lc(db_session, name="AIESEC in Sydney", lc_type=LCType.LC, state="NSW")
    assert lc.state == "NSW"


def test_create_lc_writes_audit_entry(db_session: Session) -> None:
    lc = create_lc(db_session, name="AIESEC in Audit City", lc_type=LCType.LC)
    entry = db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "lc.create",
            AuditLog.resource_id == lc.id,
        )
    ).scalar_one()
    assert entry is not None


def test_rename_lc_updates_name(db_session: Session) -> None:
    lc = make_lc(db_session, name="Old Name")
    rename_lc(db_session, lc_id=lc.id, new_name="New Name")
    assert lc.name == "New Name"


def test_rename_lc_writes_audit_entry_with_diff(db_session: Session) -> None:
    lc = make_lc(db_session, name="Before")
    rename_lc(db_session, lc_id=lc.id, new_name="After")
    entry = db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "lc.rename",
            AuditLog.resource_id == lc.id,
        )
    ).scalar_one()
    assert entry.diff == {"before": {"name": "Before"}, "after": {"name": "After"}}


def test_rename_lc_raises_for_unknown_id(db_session: Session) -> None:
    with pytest.raises(ValueError, match="LC 999999 not found"):
        rename_lc(db_session, lc_id=999999, new_name="Anything")


def test_set_lc_state_updates_state(db_session: Session) -> None:
    lc = make_lc(db_session)
    set_lc_state(db_session, lc_id=lc.id, state="VIC")
    assert lc.state == "VIC"


def test_set_lc_state_writes_audit_entry(db_session: Session) -> None:
    lc = make_lc(db_session)
    set_lc_state(db_session, lc_id=lc.id, state="QLD")
    entry = db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "lc.set_state",
            AuditLog.resource_id == lc.id,
        )
    ).scalar_one()
    assert entry.diff == {"before": {"state": None}, "after": {"state": "QLD"}}


def test_set_lc_state_raises_for_unknown_id(db_session: Session) -> None:
    with pytest.raises(ValueError, match="LC 999999 not found"):
        set_lc_state(db_session, lc_id=999999, state="NSW")


def test_deactivate_lc_sets_active_false(db_session: Session) -> None:
    lc = make_lc(db_session, name="To Deactivate")
    deactivate_lc(db_session, lc_id=lc.id)
    assert lc.active is False


def test_deactivate_lc_writes_audit_entry(db_session: Session) -> None:
    lc = make_lc(db_session, name="Audit Deactivate")
    deactivate_lc(db_session, lc_id=lc.id)
    entry = db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "lc.deactivate",
            AuditLog.resource_id == lc.id,
        )
    ).scalar_one()
    assert entry is not None


def test_deactivate_lc_does_not_delete_historical_memberships(db_session: Session) -> None:
    lc = make_lc(db_session, name="Historical LC")
    position = make_position(db_session)
    term = make_term(db_session)
    person = make_person(db_session)
    membership = make_membership(db_session, person=person, lc=lc, position=position, term=term)

    deactivate_lc(db_session, lc_id=lc.id)

    # Membership still exists and still points at the now-inactive LC
    still_there = db_session.get(Membership, membership.id)
    assert still_there is not None
    assert still_there.lc_id == lc.id


def test_deactivate_lc_raises_for_unknown_id(db_session: Session) -> None:
    with pytest.raises(ValueError, match="LC 999999 not found"):
        deactivate_lc(db_session, lc_id=999999)


def test_create_lc_rejects_unknown_state(db_session: Session) -> None:
    with pytest.raises(ValueError, match="Unknown state 'XX'"):
        create_lc(db_session, name="Bad State LC", lc_type=LCType.LC, state="XX")


def test_set_lc_state_rejects_unknown_state(db_session: Session) -> None:
    lc = make_lc(db_session, name="State Test LC")
    with pytest.raises(ValueError, match="Unknown state 'XX'"):
        set_lc_state(db_session, lc_id=lc.id, state="XX")


def test_activate_lc_reverses_deactivate(db_session: Session) -> None:
    lc = make_lc(db_session, name="Reactivate LC")
    deactivate_lc(db_session, lc_id=lc.id)

    activate_lc(db_session, lc_id=lc.id)

    db_session.refresh(lc)
    assert lc.active is True


def test_activate_lc_writes_audit_entry(db_session: Session) -> None:
    lc = make_lc(db_session, name="Reactivate Audit LC")

    activate_lc(db_session, lc_id=lc.id)

    entry = db_session.execute(
        select(AuditLog).where(AuditLog.action == "lc.activate", AuditLog.resource_id == lc.id)
    ).scalar_one()
    assert entry.resource_type == "lc"


# ---------------------------------------------------------------------------
# Person timezone follows the LC of the most recent membership
# ---------------------------------------------------------------------------


def test_refresh_person_timezone_uses_most_recent_membership(db_session: Session) -> None:
    make_state_timezone(db_session, state="NSW", timezone="Australia/Sydney")
    make_state_timezone(db_session, state="WA", timezone="Australia/Perth")
    old_lc = make_lc(db_session, name="Old NSW LC", state="NSW")
    new_lc = make_lc(db_session, name="New WA LC", state="WA")
    position = make_position(db_session)
    term = make_term(db_session)
    person = make_person(db_session, email="test_tz_recent@aiesec.net")
    make_membership(db_session, person=person, lc=old_lc, position=position, term=term)
    make_membership(
        db_session,
        person=person,
        lc=new_lc,
        position=position,
        term=term,
        start=TODAY - timedelta(days=10),
    )

    refresh_person_timezone(db_session, person_id=person.id, as_of=TODAY)

    assert person.timezone == "Australia/Perth"


def test_refresh_person_timezone_keeps_value_without_active_membership(
    db_session: Session,
) -> None:
    person = make_person(db_session, email="test_tz_none@aiesec.net")
    person.timezone = "Australia/Perth"

    refresh_person_timezone(db_session, person_id=person.id, as_of=TODAY)

    assert person.timezone == "Australia/Perth"


def test_set_lc_state_updates_timezone_of_current_members(db_session: Session) -> None:
    make_state_timezone(db_session, state="QLD", timezone="Australia/Brisbane")
    lc = make_lc(db_session, name="Moving State LC")
    position = make_position(db_session)
    term = make_term(db_session)
    person = make_person(db_session, email="test_tz_state@aiesec.net")
    make_membership(db_session, person=person, lc=lc, position=position, term=term)

    set_lc_state(db_session, lc_id=lc.id, state="QLD", as_of=TODAY)

    assert person.timezone == "Australia/Brisbane"


# ---------------------------------------------------------------------------
# Merging LCs: history is never rewritten
# ---------------------------------------------------------------------------


def test_merge_ends_active_membership_and_opens_one_in_target(db_session: Session) -> None:
    source = make_lc(db_session, name="Merge Source A")
    target = make_lc(db_session, name="Merge Target A")
    position = make_position(db_session)
    term = make_term(db_session)
    person = make_person(db_session, email="test_merge_a@aiesec.net")
    old = make_membership(db_session, person=person, lc=source, position=position, term=term)

    summary = merge_lcs(db_session, source_id=source.id, target_id=target.id, as_of=TODAY)

    db_session.refresh(old)
    assert summary.memberships_moved == 1
    assert old.lc_id == source.id
    assert old.end_date == TODAY - timedelta(days=1)

    new = db_session.execute(
        select(Membership).where(Membership.person_id == person.id, Membership.lc_id == target.id)
    ).scalar_one()
    assert new.start_date == TODAY
    assert new.end_date is None
    assert new.position_id == old.position_id
    assert new.term_id == old.term_id


def test_merge_keeps_original_end_date_on_new_membership(db_session: Session) -> None:
    source = make_lc(db_session, name="Merge Source B")
    target = make_lc(db_session, name="Merge Target B")
    position = make_position(db_session)
    term = make_term(db_session)
    person = make_person(db_session, email="test_merge_b@aiesec.net")
    make_membership(
        db_session, person=person, lc=source, position=position, term=term, end=YEAR_AHEAD
    )

    merge_lcs(db_session, source_id=source.id, target_id=target.id, as_of=TODAY)

    new = db_session.execute(
        select(Membership).where(Membership.person_id == person.id, Membership.lc_id == target.id)
    ).scalar_one()
    assert new.end_date == YEAR_AHEAD


def test_merge_keeps_kpi_history_under_source_lc(db_session: Session) -> None:
    source = make_lc(db_session, name="Merge Source KPI")
    target = make_lc(db_session, name="Merge Target KPI")
    position = make_position(db_session)
    term = make_term(db_session)
    person = make_person(db_session, email="test_merge_kpi@aiesec.net")
    old = make_membership(db_session, person=person, lc=source, position=position, term=term)
    attribute = make_kpi_attribute(db_session)
    kpi_before = record_kpi(
        db_session,
        attribute=attribute,
        membership_id=old.id,
        value_number=7,
        period_start=TODAY - timedelta(days=30),
        period_end=TODAY - timedelta(days=1),
        source=KpiSource.SELF,
        recorded_by_membership_id=old.id,
    )

    merge_lcs(db_session, source_id=source.id, target_id=target.id, as_of=TODAY)

    # The old KPI still belongs to the membership in the source LC...
    db_session.refresh(kpi_before)
    assert kpi_before.membership_id == old.id
    old_lc = db_session.execute(
        select(Membership.lc_id).where(Membership.id == kpi_before.membership_id)
    ).scalar_one()
    assert old_lc == source.id

    # ...and a KPI logged afterwards counts towards the target LC.
    new = db_session.execute(
        select(Membership).where(Membership.person_id == person.id, Membership.lc_id == target.id)
    ).scalar_one()
    kpi_after = record_kpi(
        db_session,
        attribute=attribute,
        membership_id=new.id,
        value_number=3,
        period_start=TODAY,
        period_end=TODAY + timedelta(days=30),
        source=KpiSource.SELF,
        recorded_by_membership_id=new.id,
    )
    after_lc = db_session.execute(
        select(Membership.lc_id).where(Membership.id == kpi_after.membership_id)
    ).scalar_one()
    assert after_lc == target.id
    assert db_session.get(KpiRecord, kpi_before.id) is not None


def test_merge_repoints_membership_that_has_not_started(db_session: Session) -> None:
    source = make_lc(db_session, name="Merge Source C")
    target = make_lc(db_session, name="Merge Target C")
    position = make_position(db_session)
    term = make_term(db_session)
    person = make_person(db_session, email="test_merge_c@aiesec.net")
    future = make_membership(
        db_session,
        person=person,
        lc=source,
        position=position,
        term=term,
        start=TODAY + timedelta(days=30),
    )

    summary = merge_lcs(db_session, source_id=source.id, target_id=target.id, as_of=TODAY)

    db_session.refresh(future)
    assert summary.future_memberships_repointed == 1
    assert summary.memberships_moved == 0
    assert future.lc_id == target.id


def test_merge_leaves_ended_membership_under_source(db_session: Session) -> None:
    source = make_lc(db_session, name="Merge Source D")
    target = make_lc(db_session, name="Merge Target D")
    position = make_position(db_session)
    term = make_term(db_session, name="Past Term D", end=YEAR_AGO + timedelta(days=1))
    person = make_person(db_session, email="test_merge_d@aiesec.net")
    past = make_membership(
        db_session,
        person=person,
        lc=source,
        position=position,
        term=term,
        end=YEAR_AGO + timedelta(days=1),
    )

    merge_lcs(db_session, source_id=source.id, target_id=target.id, as_of=TODAY)

    db_session.refresh(past)
    assert past.lc_id == source.id
    assert past.end_date == YEAR_AGO + timedelta(days=1)


def test_merge_creates_matching_team_in_target(db_session: Session) -> None:
    source = make_lc(db_session, name="Merge Source E")
    target = make_lc(db_session, name="Merge Target E")
    function = make_function(db_session, key="test_fn_merge_e")
    term = make_term(db_session)
    source_team = make_team(db_session, lc=source, function=function, term=term, name="Alpha")

    summary = merge_lcs(db_session, source_id=source.id, target_id=target.id, as_of=TODAY)

    db_session.refresh(source_team)
    assert source_team.lc_id == source.id
    assert summary.teams_created == 1
    target_team = db_session.execute(select(Team).where(Team.lc_id == target.id)).scalar_one()
    assert target_team.name == "Alpha"
    assert target_team.function_id == function.id


def test_merge_reuses_existing_team_in_target(db_session: Session) -> None:
    source = make_lc(db_session, name="Merge Source F")
    target = make_lc(db_session, name="Merge Target F")
    function = make_function(db_session, key="test_fn_merge_f")
    term = make_term(db_session)
    make_team(db_session, lc=source, function=function, term=term, name="Alpha")
    existing = make_team(db_session, lc=target, function=function, term=term, name="Alpha")

    summary = merge_lcs(db_session, source_id=source.id, target_id=target.id, as_of=TODAY)

    assert summary.teams_reused == 1
    assert summary.teams_created == 0
    teams_in_target = db_session.execute(select(Team).where(Team.lc_id == target.id)).scalars()
    assert [team.id for team in teams_in_target] == [existing.id]


def test_merge_leaves_past_term_team_under_source(db_session: Session) -> None:
    source = make_lc(db_session, name="Merge Source G")
    target = make_lc(db_session, name="Merge Target G")
    function = make_function(db_session, key="test_fn_merge_g")
    past_term = make_term(
        db_session, name="Past Term G", start=YEAR_AGO, end=TODAY - timedelta(days=1)
    )
    make_team(db_session, lc=source, function=function, term=past_term)

    summary = merge_lcs(db_session, source_id=source.id, target_id=target.id, as_of=TODAY)

    assert summary.teams_created == 0
    assert db_session.execute(select(Team).where(Team.lc_id == target.id)).first() is None


def test_merge_moves_team_assignment_to_new_membership_and_team(db_session: Session) -> None:
    source = make_lc(db_session, name="Merge Source H")
    target = make_lc(db_session, name="Merge Target H")
    position = make_position(db_session)
    function = make_function(db_session, key="test_fn_merge_h")
    term = make_term(db_session)
    person = make_person(db_session, email="test_merge_h@aiesec.net")
    old = make_membership(
        db_session, person=person, lc=source, position=position, term=term, function=function
    )
    source_team = make_team(db_session, lc=source, function=function, term=term)
    assignment = TeamMember(team_id=source_team.id, membership_id=old.id, start_date=YEAR_AGO)
    db_session.add(assignment)
    db_session.flush()

    merge_lcs(db_session, source_id=source.id, target_id=target.id, as_of=TODAY)

    db_session.refresh(assignment)
    assert assignment.team_id == source_team.id
    assert assignment.end_date == TODAY - timedelta(days=1)

    new = db_session.execute(
        select(Membership).where(Membership.person_id == person.id, Membership.lc_id == target.id)
    ).scalar_one()
    new_assignment = db_session.execute(
        select(TeamMember).where(TeamMember.membership_id == new.id)
    ).scalar_one()
    target_team = db_session.execute(select(Team).where(Team.lc_id == target.id)).scalar_one()
    assert new_assignment.team_id == target_team.id
    assert new_assignment.start_date == TODAY


def test_merge_carries_team_leader_when_target_has_none(db_session: Session) -> None:
    source = make_lc(db_session, name="Merge Source I")
    target = make_lc(db_session, name="Merge Target I")
    position = make_position(db_session)
    function = make_function(db_session, key="test_fn_merge_i")
    term = make_term(db_session)
    person = make_person(db_session, email="test_merge_i@aiesec.net")
    leader = make_membership(
        db_session, person=person, lc=source, position=position, term=term, function=function
    )
    source_team = make_team(db_session, lc=source, function=function, term=term)
    source_team.leader_membership_id = leader.id
    db_session.flush()

    summary = merge_lcs(db_session, source_id=source.id, target_id=target.id, as_of=TODAY)

    new_leader = db_session.execute(
        select(Membership).where(Membership.person_id == person.id, Membership.lc_id == target.id)
    ).scalar_one()
    target_team = db_session.execute(select(Team).where(Team.lc_id == target.id)).scalar_one()
    assert target_team.leader_membership_id == new_leader.id
    assert summary.leaders_not_carried == 0


def test_merge_keeps_target_leader_when_target_already_has_one(db_session: Session) -> None:
    source = make_lc(db_session, name="Merge Source J")
    target = make_lc(db_session, name="Merge Target J")
    position = make_position(db_session)
    function = make_function(db_session, key="test_fn_merge_j")
    term = make_term(db_session)
    source_person = make_person(db_session, email="test_merge_j1@aiesec.net")
    target_person = make_person(db_session, full_name="Grace", email="test_merge_j2@aiesec.net")
    source_leader = make_membership(
        db_session, person=source_person, lc=source, position=position, term=term, function=function
    )
    target_leader = make_membership(
        db_session, person=target_person, lc=target, position=position, term=term, function=function
    )
    source_team = make_team(db_session, lc=source, function=function, term=term, name="Alpha")
    source_team.leader_membership_id = source_leader.id
    target_team = make_team(db_session, lc=target, function=function, term=term, name="Alpha")
    target_team.leader_membership_id = target_leader.id
    db_session.flush()

    summary = merge_lcs(db_session, source_id=source.id, target_id=target.id, as_of=TODAY)

    db_session.refresh(target_team)
    assert target_team.leader_membership_id == target_leader.id
    assert summary.leaders_not_carried == 1


def test_merge_updates_person_timezone_to_target_state(db_session: Session) -> None:
    make_state_timezone(db_session, state="NSW", timezone="Australia/Sydney")
    make_state_timezone(db_session, state="WA", timezone="Australia/Perth")
    source = make_lc(db_session, name="Merge Source K", state="NSW")
    target = make_lc(db_session, name="Merge Target K", state="WA")
    position = make_position(db_session)
    term = make_term(db_session)
    person = make_person(db_session, email="test_merge_k@aiesec.net")
    make_membership(db_session, person=person, lc=source, position=position, term=term)
    refresh_person_timezone(db_session, person_id=person.id, as_of=TODAY)
    assert person.timezone == "Australia/Sydney"

    merge_lcs(db_session, source_id=source.id, target_id=target.id, as_of=TODAY)

    assert person.timezone == "Australia/Perth"


def test_merge_marks_source_inactive(db_session: Session) -> None:
    source = make_lc(db_session, name="Merge Source L")
    target = make_lc(db_session, name="Merge Target L")

    merge_lcs(db_session, source_id=source.id, target_id=target.id, as_of=TODAY)

    db_session.refresh(source)
    assert source.active is False


def test_merge_writes_audit_entries(db_session: Session) -> None:
    source = make_lc(db_session, name="Merge Source M")
    target = make_lc(db_session, name="Merge Target M")
    position = make_position(db_session)
    term = make_term(db_session)
    person = make_person(db_session, email="test_merge_m@aiesec.net")
    make_membership(db_session, person=person, lc=source, position=position, term=term)

    merge_lcs(db_session, source_id=source.id, target_id=target.id, as_of=TODAY)

    actions = set(
        db_session.execute(
            select(AuditLog.action).where(
                AuditLog.action.in_(["lc.merge", "membership.end_term", "membership.create"])
            )
        ).scalars()
    )
    assert actions == {"lc.merge", "membership.end_term", "membership.create"}
    merge_entry = db_session.execute(
        select(AuditLog).where(AuditLog.action == "lc.merge", AuditLog.resource_id == source.id)
    ).scalar_one()
    assert merge_entry.diff is not None
    assert merge_entry.diff["target_id"] == target.id
    assert merge_entry.diff["memberships_moved"] == 1


def test_merge_rejects_same_lc(db_session: Session) -> None:
    lc = make_lc(db_session, name="Same LC")
    with pytest.raises(ValueError, match="source and target must differ"):
        merge_lcs(db_session, source_id=lc.id, target_id=lc.id, as_of=TODAY)


def test_merge_rejects_unknown_source(db_session: Session) -> None:
    target = make_lc(db_session, name="Target Only")
    with pytest.raises(ValueError, match="LC 999999 not found"):
        merge_lcs(db_session, source_id=999999, target_id=target.id, as_of=TODAY)


def test_merge_rejects_unknown_target(db_session: Session) -> None:
    source = make_lc(db_session, name="Source Only")
    with pytest.raises(ValueError, match="LC 999999 not found"):
        merge_lcs(db_session, source_id=source.id, target_id=999999, as_of=TODAY)


def test_merge_rejects_inactive_target(db_session: Session) -> None:
    source = make_lc(db_session, name="Merge Source N")
    target = make_lc(db_session, name="Merge Target N")
    deactivate_lc(db_session, lc_id=target.id)
    with pytest.raises(ValueError, match="inactive LC"):
        merge_lcs(db_session, source_id=source.id, target_id=target.id, as_of=TODAY)


def test_merge_rejects_inactive_source(db_session: Session) -> None:
    source = make_lc(db_session, name="Merge Source O")
    target = make_lc(db_session, name="Merge Target O")
    deactivate_lc(db_session, lc_id=source.id)
    with pytest.raises(ValueError, match="already inactive"):
        merge_lcs(db_session, source_id=source.id, target_id=target.id, as_of=TODAY)


def test_merge_rejects_the_mc(db_session: Session) -> None:
    mc = make_lc(db_session, name="Merge MC", lc_type=LCType.MC)
    target = make_lc(db_session, name="Merge Target P")
    with pytest.raises(ValueError, match="MC cannot be merged"):
        merge_lcs(db_session, source_id=target.id, target_id=mc.id, as_of=TODAY)
