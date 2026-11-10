"""Queries for the reference data the membership pages pick from (DEV-0043)."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.membership import Membership, Team
from app.models.org import Function, LCType, Term
from app.models.person import Person
from app.repositories.lc import list_lcs
from app.schemas.reference import (
    LcOption,
    MembershipOptions,
    TeamLeader,
    TeamOption,
    TermOption,
)


def get_membership_options(session: Session) -> MembershipOptions:
    """Active LCs, every term, and the current or upcoming teams of those LCs.

    Inactive LCs (and their teams) are left out: they keep their history but are
    never offered when adding members (spec §1.5). Teams whose term has ended are
    left out too: after a rollover the old "oGV Team A" still exists under the same
    name, and offering it would let someone add a member to last term's team.
    """
    lcs = list_lcs(session)
    active_lc_ids = [lc.id for lc in lcs]

    terms = session.execute(select(Term).order_by(Term.start_date)).scalars().all()

    team_rows = session.execute(
        select(Team, Function.key)
        .join(Function, Function.id == Team.function_id)
        .join(Term, Term.id == Team.term_id)
        .where(Team.lc_id.in_(active_lc_ids), Term.end_date >= date.today())
        .order_by(Team.lc_id, Team.name)
    ).all()

    # One query for every leader's name, rather than one per team.
    leader_ids = [team.leader_membership_id for team, _ in team_rows if team.leader_membership_id]
    leader_names: dict[int, str] = {}
    if leader_ids:
        leader_names = {
            membership_id: full_name
            for membership_id, full_name in session.execute(
                select(Membership.id, Person.full_name)
                .join(Person, Person.id == Membership.person_id)
                .where(Membership.id.in_(leader_ids))
            ).tuples()
        }

    return MembershipOptions(
        lcs=[
            LcOption(
                id=str(lc.id),
                name=lc.name,
                type="mc" if lc.type == LCType.MC else "lc",
                state=lc.state,
                active=lc.active,
            )
            for lc in lcs
        ],
        terms=[
            TermOption(
                id=str(term.id),
                name=term.name,
                startDate=term.start_date.isoformat(),
                endDate=term.end_date.isoformat(),
            )
            for term in terms
        ],
        teams=[
            TeamOption(
                id=str(team.id),
                name=team.name,
                lcId=str(team.lc_id),
                functionKey=function_key,
                leader=_leader(team, leader_names),
            )
            for team, function_key in team_rows
        ],
    )


def _leader(team: Team, leader_names: dict[int, str]) -> TeamLeader | None:
    if team.leader_membership_id is None or team.leader_membership_id not in leader_names:
        return None
    return TeamLeader(
        membershipId=str(team.leader_membership_id),
        name=leader_names[team.leader_membership_id],
    )
