"""Queries over `team` / `team_member`."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.membership import Team, TeamMember


def get_current_teams_for_memberships(
    session: Session, membership_ids: Sequence[int], as_of: date | None = None
) -> dict[int, Team]:
    """The team each membership is currently in, keyed by membership id.

    "Current" uses `team_member`'s own dates, the same rule as memberships
    (`start_date <= as_of`, and `end_date` empty or not passed). A membership with no
    current `team_member` row (e.g. an LCVP) is simply absent from the result.
    """
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
