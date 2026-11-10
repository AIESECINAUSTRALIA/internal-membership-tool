"""Queries and mutations for `team` / `team_member` (spec §1.5)."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.models.membership import Membership, Team, TeamMember
from app.models.org import Function


def get_team(session: Session, team_id: int) -> Team | None:
    return session.get(Team, team_id)


def list_teams(
    session: Session,
    *,
    lc_id: int,
    term_id: int | None = None,
    include_inactive: bool = False,
) -> Sequence[Team]:
    stmt = select(Team).where(Team.lc_id == lc_id)
    if term_id is not None:
        stmt = stmt.where(Team.term_id == term_id)
    if not include_inactive:
        stmt = stmt.where(Team.active.is_(True))
    return session.execute(stmt).scalars().all()


def create_team(
    session: Session,
    *,
    lc_id: int,
    function_id: int,
    term_id: int,
    name: str,
    actor_membership_id: int | None = None,
) -> Team:
    _require_function(session, function_id)
    team = Team(
        lc_id=lc_id,
        function_id=function_id,
        term_id=term_id,
        name=name,
        active=True,
    )
    session.add(team)
    session.flush()
    record_audit(
        session,
        action="team.create",
        resource_type="team",
        resource_id=team.id,
        summary=f"Team '{name}' created in LC {lc_id}",
        actor_membership_id=actor_membership_id,
    )
    return team


def rename_team(
    session: Session,
    *,
    team_id: int,
    new_name: str,
    actor_membership_id: int | None = None,
) -> Team:
    team = _require_team(session, team_id)
    old_name = team.name
    team.name = new_name
    session.flush()
    record_audit(
        session,
        action="team.rename",
        resource_type="team",
        resource_id=team_id,
        summary=f"Team {team_id} renamed '{old_name}' → '{new_name}'",
        actor_membership_id=actor_membership_id,
    )
    return team


def disband_team(
    session: Session,
    *,
    team_id: int,
    actor_membership_id: int | None = None,
) -> Team:
    """Soft-disable the team. Historical team_member rows are preserved."""
    team = _require_team(session, team_id)
    if not team.active:
        raise ValueError(f"Team {team_id} is already disbanded")
    team.active = False
    session.flush()
    record_audit(
        session,
        action="team.disband",
        resource_type="team",
        resource_id=team_id,
        summary=f"Team {team_id} disbanded",
        actor_membership_id=actor_membership_id,
    )
    return team


def reassign_leader(
    session: Session,
    *,
    team_id: int,
    new_leader_membership_id: int | None,
    actor_membership_id: int | None = None,
) -> Team:
    team = _require_team(session, team_id)
    if new_leader_membership_id is not None:
        m = session.get(Membership, new_leader_membership_id)
        if m is None:
            raise ValueError(f"Membership {new_leader_membership_id} not found")
    old_id = team.leader_membership_id
    team.leader_membership_id = new_leader_membership_id
    session.flush()
    record_audit(
        session,
        action="team.reassign_leader",
        resource_type="team",
        resource_id=team_id,
        summary=(
            f"Team {team_id} leader changed from membership "
            f"{old_id} to {new_leader_membership_id}"
        ),
        actor_membership_id=actor_membership_id,
    )
    return team


def reparent_team(
    session: Session,
    *,
    team_id: int,
    new_function_id: int,
    actor_membership_id: int | None = None,
) -> Team:
    team = _require_team(session, team_id)
    _require_function(session, new_function_id)
    old_function_id = team.function_id
    team.function_id = new_function_id
    session.flush()
    record_audit(
        session,
        action="team.reparent",
        resource_type="team",
        resource_id=team_id,
        summary=(
            f"Team {team_id} re-parented from function "
            f"{old_function_id} to {new_function_id}"
        ),
        actor_membership_id=actor_membership_id,
    )
    return team


def move_member(
    session: Session,
    *,
    membership_id: int,
    new_team_id: int,
    as_of: date | None = None,
    actor_membership_id: int | None = None,
) -> TeamMember:
    """Move a membership to a new team.

    Ends the current active team_member row and opens a new one for the target
    team, preserving history (spec §1.5).
    """
    reference_date = as_of if as_of is not None else date.today()
    new_team = _require_team(session, new_team_id)

    # End existing active row for this membership, if any.
    current = session.execute(
        select(TeamMember).where(
            TeamMember.membership_id == membership_id,
            TeamMember.start_date <= reference_date,
            or_(
                TeamMember.end_date.is_(None),
                TeamMember.end_date >= reference_date,
            ),
        )
    ).scalar_one_or_none()

    old_team_id = current.team_id if current else None
    if current is not None:
        current.end_date = reference_date

    new_row = TeamMember(
        team_id=new_team_id,
        membership_id=membership_id,
        start_date=reference_date,
    )
    session.add(new_row)
    session.flush()
    record_audit(
        session,
        action="team.move_member",
        resource_type="team",
        resource_id=new_team.id,
        summary=(
            f"Membership {membership_id} moved from team "
            f"{old_team_id} to team {new_team_id}"
        ),
        actor_membership_id=actor_membership_id,
    )
    return new_row


def get_current_teams_for_memberships(
    session: Session, membership_ids: Sequence[int], as_of: date | None = None
) -> dict[int, Team]:
    """The team each membership is currently in, keyed by membership id."""
    if not membership_ids:
        return {}
    reference_date = as_of if as_of is not None else date.today()
    stmt = (
        select(TeamMember.membership_id, Team)
        .join(Team, Team.id == TeamMember.team_id)
        .where(
            TeamMember.membership_id.in_(membership_ids),
            TeamMember.start_date <= reference_date,
            or_(TeamMember.end_date.is_(None), TeamMember.end_date >= reference_date),
        )
    )
    return {membership_id: team for membership_id, team in session.execute(stmt).tuples()}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require_team(session: Session, team_id: int) -> Team:
    team = session.get(Team, team_id)
    if team is None:
        raise ValueError(f"Team {team_id} not found")
    return team


def _require_function(session: Session, function_id: int) -> None:
    if session.get(Function, function_id) is None:
        raise ValueError(f"Function {function_id} not found")
