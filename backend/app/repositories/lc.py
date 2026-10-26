"""Queries and mutations for the `lc` table.

Every mutating function calls `record_audit` in the same session so the
audit entry is saved if and only if the change is saved.

LCs are never hard-deleted. "Delete" means `deactivate_lc`: the row stays so
memberships, teams and KPI history that point at it keep making sense.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.models.membership import Membership, Team, TeamMember
from app.models.org import LC, LCType, StateTimezone, Term
from app.models.person import Person

LC_DEFAULT_TIMEZONE = "Australia/Melbourne"


@dataclass(frozen=True)
class MergeSummary:
    """What a merge changed. Shown to the admin after the merge."""

    memberships_moved: int
    future_memberships_repointed: int
    teams_created: int
    teams_reused: int
    leaders_not_carried: int


def list_lcs(session: Session, *, include_inactive: bool = False) -> Sequence[LC]:
    """Return all LCs. Active-only by default."""
    stmt = select(LC)
    if not include_inactive:
        stmt = stmt.where(LC.active.is_(True))
    return session.execute(stmt).scalars().all()


def get_lc(session: Session, lc_id: int) -> LC | None:
    """Return the LC with `lc_id`, or None if it doesn't exist."""
    return session.get(LC, lc_id)


def resolve_timezone(session: Session, *, lc_id: int) -> str:
    """Return the IANA timezone for `lc_id`.

    Looks up `lc.state` → `state_timezone.timezone`. Falls back to
    LC_DEFAULT_TIMEZONE when the LC has no state (e.g. the MC row).
    """
    lc = session.get(LC, lc_id)
    if lc is None or lc.state is None:
        return LC_DEFAULT_TIMEZONE
    row = session.get(StateTimezone, lc.state)
    if row is None:
        return LC_DEFAULT_TIMEZONE
    return row.timezone


def refresh_person_timezone(
    session: Session,
    *,
    person_id: int,
    as_of: date | None = None,
) -> None:
    """Set a person's timezone from the LC of their most recent active membership.

    "Most recent" means the latest `start_date` among memberships active on
    `as_of`. A person with no active membership keeps their current timezone.
    """
    today = as_of if as_of is not None else date.today()

    most_recent = session.execute(
        select(Membership)
        .where(
            Membership.person_id == person_id,
            Membership.start_date <= today,
            or_(Membership.end_date.is_(None), Membership.end_date >= today),
        )
        .order_by(Membership.start_date.desc(), Membership.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if most_recent is None:
        return

    person = session.get(Person, person_id)
    if person is None:
        return
    person.timezone = resolve_timezone(session, lc_id=most_recent.lc_id)
    session.flush()


def _require_known_state(session: Session, state: str) -> None:
    """Raise ValueError unless `state` exists in the `state_timezone` lookup."""
    if session.get(StateTimezone, state) is None:
        raise ValueError(f"Unknown state '{state}'")


def _refresh_timezones_for_lc(session: Session, *, lc_id: int, as_of: date) -> None:
    """Refresh the timezone of everyone with an active membership in `lc_id`."""
    person_ids = session.execute(
        select(Membership.person_id)
        .where(
            Membership.lc_id == lc_id,
            Membership.start_date <= as_of,
            or_(Membership.end_date.is_(None), Membership.end_date >= as_of),
        )
        .distinct()
    ).scalars()
    for person_id in list(person_ids):
        refresh_person_timezone(session, person_id=person_id, as_of=as_of)


def create_lc(
    session: Session,
    *,
    name: str,
    lc_type: LCType,
    state: str | None = None,
    actor_membership_id: int | None = None,
) -> LC:
    """Insert a new LC row and audit-log the creation."""
    if state is not None:
        _require_known_state(session, state)

    lc = LC(name=name, type=lc_type, state=state, active=True)
    session.add(lc)
    session.flush()
    record_audit(
        session,
        action="lc.create",
        resource_type="lc",
        resource_id=lc.id,
        summary=f"LC {lc.id} created with name '{name}'",
        actor_membership_id=actor_membership_id,
    )
    return lc


def rename_lc(
    session: Session,
    *,
    lc_id: int,
    new_name: str,
    actor_membership_id: int | None = None,
) -> LC:
    """Rename an LC and audit-log the old and new name."""
    lc = session.get(LC, lc_id)
    if lc is None:
        raise ValueError(f"LC {lc_id} not found")
    old_name = lc.name
    lc.name = new_name
    session.flush()
    record_audit(
        session,
        action="lc.rename",
        resource_type="lc",
        resource_id=lc_id,
        summary=f"LC {lc_id} renamed",
        actor_membership_id=actor_membership_id,
        diff={"before": {"name": old_name}, "after": {"name": new_name}},
    )
    return lc


def set_lc_state(
    session: Session,
    *,
    lc_id: int,
    state: str,
    actor_membership_id: int | None = None,
    as_of: date | None = None,
) -> LC:
    """Set the Australian state for an LC and audit-log the change.

    Members whose most recent membership is in this LC get their timezone
    refreshed, so it follows the LC's new state.
    """
    lc = session.get(LC, lc_id)
    if lc is None:
        raise ValueError(f"LC {lc_id} not found")
    _require_known_state(session, state)

    old_state = lc.state
    lc.state = state
    session.flush()
    record_audit(
        session,
        action="lc.set_state",
        resource_type="lc",
        resource_id=lc_id,
        summary=f"LC {lc_id} state set to {state}",
        actor_membership_id=actor_membership_id,
        diff={"before": {"state": old_state}, "after": {"state": state}},
    )

    today = as_of if as_of is not None else date.today()
    _refresh_timezones_for_lc(session, lc_id=lc_id, as_of=today)
    return lc


def deactivate_lc(
    session: Session,
    *,
    lc_id: int,
    actor_membership_id: int | None = None,
) -> LC:
    """Mark an LC inactive. Historical records pointing at it are preserved.

    This is the only way to remove an LC (spec §1.5): there is no hard delete.
    """
    lc = session.get(LC, lc_id)
    if lc is None:
        raise ValueError(f"LC {lc_id} not found")
    lc.active = False
    session.flush()
    record_audit(
        session,
        action="lc.deactivate",
        resource_type="lc",
        resource_id=lc_id,
        summary=f"LC {lc_id} marked inactive",
        actor_membership_id=actor_membership_id,
    )
    return lc


def activate_lc(
    session: Session,
    *,
    lc_id: int,
    actor_membership_id: int | None = None,
) -> LC:
    """Mark an inactive LC active again (undo for a mistaken deactivation)."""
    lc = session.get(LC, lc_id)
    if lc is None:
        raise ValueError(f"LC {lc_id} not found")
    lc.active = True
    session.flush()
    record_audit(
        session,
        action="lc.activate",
        resource_type="lc",
        resource_id=lc_id,
        summary=f"LC {lc_id} marked active",
        actor_membership_id=actor_membership_id,
    )
    return lc


def _validate_merge(session: Session, *, source_id: int, target_id: int) -> tuple[LC, LC]:
    """Return (source, target), or raise ValueError if they can't be merged."""
    if source_id == target_id:
        raise ValueError("source and target must differ")

    source = session.get(LC, source_id)
    if source is None:
        raise ValueError(f"LC {source_id} not found")
    target = session.get(LC, target_id)
    if target is None:
        raise ValueError(f"LC {target_id} not found")

    if not source.active:
        raise ValueError("The LC being merged is already inactive")
    if not target.active:
        raise ValueError("Cannot merge into an inactive LC")
    if source.type == LCType.MC or target.type == LCType.MC:
        raise ValueError("The MC cannot be merged")
    return source, target


def _copy_teams_to_target(
    session: Session,
    *,
    source_id: int,
    target_id: int,
    merge_date: date,
) -> tuple[dict[int, Team], int, int]:
    """Make sure the target LC has a team for each current/future source team.

    A target team with the same function, term and name is reused; otherwise a
    new one is created. The source team itself is left alone (it keeps its
    history under the source LC).

    Returns ({source_team_id: target_team}, teams_created, teams_reused).
    """
    source_teams = (
        session.execute(
            select(Team)
            .join(Term, Team.term_id == Term.id)
            .where(Team.lc_id == source_id, Term.end_date >= merge_date)
        )
        .scalars()
        .all()
    )

    target_team_for: dict[int, Team] = {}
    created = 0
    reused = 0
    for source_team in source_teams:
        existing = session.execute(
            select(Team).where(
                Team.lc_id == target_id,
                Team.function_id == source_team.function_id,
                Team.term_id == source_team.term_id,
                Team.name == source_team.name,
            )
        ).scalar_one_or_none()

        if existing is not None:
            target_team_for[source_team.id] = existing
            reused += 1
            continue

        new_team = Team(
            lc_id=target_id,
            function_id=source_team.function_id,
            term_id=source_team.term_id,
            name=source_team.name,
        )
        session.add(new_team)
        session.flush()
        target_team_for[source_team.id] = new_team
        created += 1

    return target_team_for, created, reused


def _move_team_memberships(
    session: Session,
    *,
    old_membership_id: int,
    new_membership_id: int,
    target_team_for: dict[int, Team],
    merge_date: date,
) -> None:
    """Carry a membership's team assignments over to its new membership.

    A team assignment that started before the merge is ended the day before
    and a new one is opened on the merge date. One that starts on or after the
    merge date has no history, so it is simply pointed at the new membership.
    """
    day_before = merge_date - timedelta(days=1)

    assignments = (
        session.execute(
            select(TeamMember).where(
                TeamMember.membership_id == old_membership_id,
                TeamMember.team_id.in_(list(target_team_for)),
                or_(TeamMember.end_date.is_(None), TeamMember.end_date >= merge_date),
            )
        )
        .scalars()
        .all()
    )

    for assignment in assignments:
        target_team = target_team_for[assignment.team_id]

        if assignment.start_date >= merge_date:
            assignment.team_id = target_team.id
            assignment.membership_id = new_membership_id
            continue

        original_end = assignment.end_date
        assignment.end_date = day_before
        session.add(
            TeamMember(
                team_id=target_team.id,
                membership_id=new_membership_id,
                start_date=merge_date,
                end_date=original_end,
            )
        )
    session.flush()


def merge_lcs(
    session: Session,
    *,
    source_id: int,
    target_id: int,
    actor_membership_id: int | None = None,
    as_of: date | None = None,
) -> MergeSummary:
    """Merge the source LC into the target LC as of `as_of` (default today).

    History is never rewritten, so past reports stay accurate (spec §5.1):

    - A membership active at the merge date is ended the day before and a new
      one is opened in the target from the merge date. Its KPI records stay on
      the old membership, so they keep counting towards the source LC.
    - A membership that has not started yet is simply pointed at the target.
    - Current and future teams are copied to (or matched in) the target LC.
    - Ended memberships and past teams are untouched.
    - The source LC is marked inactive.

    Raises ValueError if the LCs can't be merged (see `_validate_merge`).
    """
    source, _target = _validate_merge(session, source_id=source_id, target_id=target_id)
    merge_date = as_of if as_of is not None else date.today()
    day_before = merge_date - timedelta(days=1)

    target_team_for, teams_created, teams_reused = _copy_teams_to_target(
        session, source_id=source_id, target_id=target_id, merge_date=merge_date
    )

    open_memberships = (
        session.execute(
            select(Membership).where(
                Membership.lc_id == source_id,
                or_(Membership.end_date.is_(None), Membership.end_date >= merge_date),
            )
        )
        .scalars()
        .all()
    )

    # old membership id -> the membership that carries on in the target LC
    carried_on_as: dict[int, int] = {}
    memberships_moved = 0
    future_repointed = 0
    affected_person_ids: set[int] = set()

    for old in open_memberships:
        affected_person_ids.add(old.person_id)

        if old.start_date >= merge_date:
            # No history yet, so nothing to preserve: just change the LC.
            old.lc_id = target_id
            carried_on_as[old.id] = old.id
            future_repointed += 1
            _move_team_memberships(
                session,
                old_membership_id=old.id,
                new_membership_id=old.id,
                target_team_for=target_team_for,
                merge_date=merge_date,
            )
            continue

        original_end = old.end_date
        old.end_date = day_before
        new = Membership(
            person_id=old.person_id,
            lc_id=target_id,
            position_id=old.position_id,
            function_id=old.function_id,
            term_id=old.term_id,
            start_date=merge_date,
            end_date=original_end,
            is_primary=old.is_primary,
        )
        session.add(new)
        session.flush()
        carried_on_as[old.id] = new.id
        memberships_moved += 1

        record_audit(
            session,
            action="membership.end_term",
            resource_type="membership",
            resource_id=old.id,
            summary=f"Membership ended due to merge of LC {source_id} into LC {target_id}",
            actor_membership_id=actor_membership_id,
            diff={"before": str(original_end), "after": str(day_before)},
        )
        record_audit(
            session,
            action="membership.create",
            resource_type="membership",
            resource_id=new.id,
            summary=f"Membership opened in LC {target_id} due to merge of LC {source_id}",
            actor_membership_id=actor_membership_id,
            diff={"after": {"lc_id": target_id, "start_date": str(merge_date)}},
        )
        _move_team_memberships(
            session,
            old_membership_id=old.id,
            new_membership_id=new.id,
            target_team_for=target_team_for,
            merge_date=merge_date,
        )

    leaders_not_carried = _carry_over_team_leaders(
        session, target_team_for=target_team_for, carried_on_as=carried_on_as
    )

    source.active = False
    session.flush()

    for person_id in affected_person_ids:
        refresh_person_timezone(session, person_id=person_id, as_of=merge_date)

    summary = MergeSummary(
        memberships_moved=memberships_moved,
        future_memberships_repointed=future_repointed,
        teams_created=teams_created,
        teams_reused=teams_reused,
        leaders_not_carried=leaders_not_carried,
    )
    record_audit(
        session,
        action="lc.merge",
        resource_type="lc",
        resource_id=source_id,
        summary=(
            f"LC {source_id} merged into LC {target_id}: "
            f"{memberships_moved} memberships moved, "
            f"{future_repointed} future memberships re-pointed"
        ),
        actor_membership_id=actor_membership_id,
        diff={
            "source_id": source_id,
            "target_id": target_id,
            "merge_date": str(merge_date),
            "memberships_moved": memberships_moved,
            "future_memberships_repointed": future_repointed,
            "teams_created": teams_created,
            "teams_reused": teams_reused,
            "leaders_not_carried": leaders_not_carried,
        },
    )
    return summary


def _carry_over_team_leaders(
    session: Session,
    *,
    target_team_for: dict[int, Team],
    carried_on_as: dict[int, int],
) -> int:
    """Give each target team the leader of its source team, if it has none.

    Returns how many leaders could not be carried over because the target
    team already had its own leader.
    """
    not_carried = 0
    for source_team_id, target_team in target_team_for.items():
        source_team = session.get(Team, source_team_id)
        if source_team is None or source_team.leader_membership_id is None:
            continue

        new_leader_id = carried_on_as.get(source_team.leader_membership_id)
        if new_leader_id is None:
            continue

        if target_team.leader_membership_id is None:
            target_team.leader_membership_id = new_leader_id
        elif target_team.leader_membership_id != new_leader_id:
            not_carried += 1
    session.flush()
    return not_carried
