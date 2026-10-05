"""Membership repository queries and lifecycle mutations.

Implements Spec §2A.5, §3.4, §3.6, §5.1, and §8.4.
"""

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.permissions import (
    POSITION_RANKS,
    MembershipContext,
    can_extend_term,
    can_move_to_team,
    resolve_widest_scope,
)
from app.models.membership import Membership, Team, TeamMember
from app.models.org import LC, Function, Position
from app.models.person import Person, PersonStatus


def get_active_memberships_for_person(
    session: Session, person_id: int, as_of: date | None = None
) -> Sequence[Membership]:
    """Memberships for person_id that are current as of as_of (default: today)."""
    ref_date = as_of if as_of is not None else date.today()
    stmt = select(Membership).where(
        Membership.person_id == person_id,
        Membership.start_date <= ref_date,
        or_(Membership.end_date.is_(None), Membership.end_date >= ref_date),
    )
    return session.execute(stmt).scalars().all()


def build_membership_context(
    session: Session, membership: Membership
) -> MembershipContext:
    """Build a MembershipContext helper for permission evaluations."""
    pos = session.get(Position, membership.position_id)
    pos_key = pos.key if pos else "member"
    rank = (
        getattr(pos, "rank", None)
        or POSITION_RANKS.get(pos_key, 1)
    )
    can_add_same_rank = getattr(pos, "can_add_same_rank", False) or (pos_key in {"lcp", "mcp"})

    lc = session.get(LC, membership.lc_id)
    lc_type = lc.type.value if lc and hasattr(lc.type, "value") else "LC"

    func = session.get(Function, membership.function_id) if membership.function_id else None
    func_key = func.key if func else None

    # Current team lookup
    today = date.today()
    stmt = select(TeamMember).where(
        TeamMember.membership_id == membership.id,
        TeamMember.start_date <= today,
        or_(TeamMember.end_date.is_(None), TeamMember.end_date >= today),
    )
    team_member = session.execute(stmt).scalars().first()
    team_id = team_member.team_id if team_member else None

    return MembershipContext(
        membership_id=membership.id,
        person_id=membership.person_id,
        lc_id=membership.lc_id,
        position_key=pos_key,
        position_rank=rank,
        can_add_same_rank=can_add_same_rank,
        function_id=membership.function_id,
        function_key=func_key,
        team_id=team_id,
        lc_type=lc_type,
    )


# ---------------------------------------------------------------------------
# Spec §2A.5: listMembers
# ---------------------------------------------------------------------------


def list_members_summary(
    session: Session,
    actor_memberships: Sequence[MembershipContext],
    *,
    search: str = "",
    sort_field: str = "lastName",
    sort_direction: str = "asc",
    page: int = 0,
    page_size: int = 15,
    filter_lc_id: int | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Summary list of current members matching Spec §2A.5.

    - LC Isolation: Non-MC viewer only sees their own LC.
    - No email/phone (PII stays server-side).
    - People with multiple active roles appear once, with all roles listed.
    """
    ref_date = as_of if as_of is not None else date.today()

    scope = resolve_widest_scope(actor_memberships, "membership", "view")
    if scope is None:
        return {"rows": [], "total": 0}

    # LC Isolation rule (§2A.5)
    allowed_lc_ids: set[int] | None = None
    if scope != "all":
        allowed_lc_ids = {m.lc_id for m in actor_memberships}

    # Fetch active memberships
    stmt = select(Membership).where(
        Membership.start_date <= ref_date,
        or_(Membership.end_date.is_(None), Membership.end_date >= ref_date),
    )
    if allowed_lc_ids is not None:
        stmt = stmt.where(Membership.lc_id.in_(allowed_lc_ids))
    if filter_lc_id is not None:
        if allowed_lc_ids is None or filter_lc_id in allowed_lc_ids:
            stmt = stmt.where(Membership.lc_id == filter_lc_id)
        else:
            return {"rows": [], "total": 0}

    memberships = session.execute(stmt).scalars().all()

    # Group by person
    person_ids = {m.person_id for m in memberships}
    if not person_ids:
        return {"rows": [], "total": 0}

    people = {
        p.id: p
        for p in session.execute(
            select(Person).where(Person.id.in_(person_ids))
        ).scalars().all()
    }
    lcs = {
        lc.id: lc
        for lc in session.execute(select(LC)).scalars().all()
    }
    positions = {
        pos.id: pos
        for pos in session.execute(select(Position)).scalars().all()
    }
    functions = {
        fn.id: fn
        for fn in session.execute(select(Function)).scalars().all()
    }

    # Team member mappings
    team_members = session.execute(
        select(TeamMember).where(
            TeamMember.membership_id.in_([m.id for m in memberships]),
            TeamMember.start_date <= ref_date,
            or_(TeamMember.end_date.is_(None), TeamMember.end_date >= ref_date),
        )
    ).scalars().all()
    team_by_membership = {tm.membership_id: tm.team_id for tm in team_members}

    # Group memberships by person
    by_person: dict[int, list[Membership]] = {}
    for m in memberships:
        by_person.setdefault(m.person_id, []).append(m)

    rows: list[dict[str, Any]] = []
    for pid, p_memberships in by_person.items():
        person = people.get(pid)
        if not person:
            continue

        first_name = getattr(person, "first_name", "") or person.full_name.split(" ")[0]
        last_name = (
            getattr(person, "last_name", "")
            or (" ".join(person.full_name.split(" ")[1:]) if " " in person.full_name else "")
        )

        primary_lc = lcs.get(p_memberships[0].lc_id)
        lc_payload = {
            "id": str(primary_lc.id) if primary_lc else "",
            "name": primary_lc.name if primary_lc else "",
            "type": primary_lc.type.value.lower() if primary_lc else "lc",
        }

        roles_payload: list[dict[str, Any]] = []
        for m in p_memberships:
            pos = positions.get(m.position_id)
            fn = functions.get(m.function_id) if m.function_id else None
            pos_key = pos.key if pos else "member"
            rank = getattr(pos, "rank", None) or POSITION_RANKS.get(pos_key, 1)

            roles_payload.append(
                {
                    "membershipId": str(m.id),
                    "position": {
                        "key": pos_key,
                        "label": pos.label if pos else pos_key,
                        "level": "mc" if primary_lc and primary_lc.type.value == "MC" else "lc",
                        "rank": rank,
                        "canAddSameRank": getattr(pos, "can_add_same_rank", False)
                        or (pos_key in {"lcp", "mcp"}),
                        "presidential": pos_key in {"lcp", "mcp"},
                        "homeChartScope": "all"
                        if primary_lc and primary_lc.type.value == "MC"
                        else "team",
                        "holdsTeam": pos_key in {"member", "team_leader"},
                    },
                    "function": {"key": fn.key, "label": fn.label} if fn else None,
                    "teamId": str(team_by_membership[m.id]) if m.id in team_by_membership else None,
                }
            )

        # Sort roles descending by rank
        roles_payload.sort(key=lambda r: r["position"]["rank"], reverse=True)

        rows.append(
            {
                "personId": str(person.id),
                "firstName": first_name,
                "lastName": last_name,
                "lc": lc_payload,
                "roles": roles_payload,
            }
        )

    # Search filter
    needle = search.strip().lower()
    if needle:
        filtered = []
        for r in rows:
            haystack = [
                r["firstName"],
                r["lastName"],
                f"{r['firstName']} {r['lastName']}",
                r["lc"]["name"],
            ]
            for role in r["roles"]:
                haystack.append(role["position"]["label"])
                if role["function"]:
                    haystack.append(role["function"]["label"])
            if any(needle in s.lower() for s in haystack if s):
                filtered.append(r)
        rows = filtered

    # Sorting
    reverse = sort_direction.lower() == "desc"
    if sort_field == "firstName":
        rows.sort(key=lambda r: r["firstName"].lower(), reverse=reverse)
    elif sort_field == "lc":
        rows.sort(key=lambda r: r["lc"]["name"].lower(), reverse=reverse)
    elif sort_field == "position":
        rows.sort(key=lambda r: r["roles"][0]["position"]["rank"], reverse=reverse)
    else:  # default 'lastName'
        rows.sort(key=lambda r: r["lastName"].lower(), reverse=reverse)

    total = len(rows)
    start = page * page_size
    paged_rows = rows[start : start + page_size]

    return {"rows": paged_rows, "total": total}


# ---------------------------------------------------------------------------
# Spec §2A.5 & §5.1: addMember
# ---------------------------------------------------------------------------


def add_member(
    session: Session,
    actor_memberships: Sequence[MembershipContext],
    *,
    email: str,
    lc_id: int,
    position_key: str,
    start_date: date,
    end_date: date,
    first_name: str | None = None,
    last_name: str | None = None,
    function_key: str | None = None,
    team_id: int | None = None,
    term_id: int | None = None,
    confirmed_existing: bool = False,
) -> dict[str, Any]:
    """Add a member per Spec §2A.5, §3.4, §3.6, and §5.1."""
    if end_date < start_date:
        return {"status": "rejected", "message": "The end date must be on or after the start date."}

    lc = session.get(LC, lc_id)
    if not lc:
        return {"status": "rejected", "message": "LC not found."}

    pos = session.execute(
        select(Position).where(Position.key == position_key)
    ).scalar_one_or_none()
    if not pos:
        return {"status": "rejected", "message": "Position not found."}

    func = None
    if function_key:
        func = session.execute(
            select(Function).where(Function.key == function_key)
        ).scalar_one_or_none()

    clean_email = email.strip().lower()

    # Check if person exists
    person = session.execute(
        select(Person).where(Person.aiesec_email == clean_email)
    ).scalar_one_or_none()

    if person is None:
        if not first_name or not last_name or not first_name.strip() or not last_name.strip():
            return {"status": "needs_name"}
    elif not confirmed_existing:
        return {"status": "confirm_existing"}

    # Validate target against active memberships
    if person is not None:
        theirs = session.execute(
            select(Membership).where(Membership.person_id == person.id)
        ).scalars().all()

        # Spec §3.6: Adding to LC while holding active overlapping MC membership is blocked
        for m in theirs:
            m_lc = session.get(LC, m.lc_id)
            if (
                m_lc
                and m_lc.type.value == "MC"
                and lc.type.value == "LC"
                and m.start_date <= end_date
                and (m.end_date is None or m.end_date >= start_date)
            ):
                return {
                    "status": "rejected",
                    "message": "This person can't be added. Contact your MC.",
                }

        # Check overlapping duplicate function in same LC
        if func:
            for m in theirs:
                if (
                    m.lc_id == lc.id
                    and m.function_id == func.id
                    and m.start_date <= end_date
                    and (m.end_date is None or m.end_date >= start_date)
                ):
                    return {
                        "status": "rejected",
                        "message": (
                            "This person already holds that function "
                            "in this LC for overlapping dates."
                        ),
                    }

    # Create person if new
    if person is None:
        f_name = first_name.strip() if first_name else ""
        l_name = last_name.strip() if last_name else ""
        full_name = f"{f_name} {l_name}".strip()
        person = Person(
            full_name=full_name,
            aiesec_email=clean_email,
            join_date=start_date,
            status=PersonStatus.ACTIVE,
        )
        session.add(person)
        session.flush()
    else:
        # Transfer logic (§5.1): End active memberships in other LCs to start_date - 1 day
        theirs = session.execute(
            select(Membership).where(
                Membership.person_id == person.id,
                Membership.lc_id != lc.id,
                Membership.start_date <= end_date,
                or_(Membership.end_date.is_(None), Membership.end_date >= start_date),
            )
        ).scalars().all()

        day_before = start_date - timedelta(days=1)
        for old_m in theirs:
            old_end = old_m.end_date
            new_end = day_before if day_before >= old_m.start_date else old_m.start_date
            old_m.end_date = new_end
            session.flush()

            acting = actor_memberships[0] if actor_memberships else None
            record_audit(
                session,
                action="membership.end_term",
                resource_type="membership",
                resource_id=old_m.id,
                summary="Membership ended automatically due to transfer to another LC",
                actor_membership_id=acting.membership_id if acting else None,
                diff={"before": str(old_end), "after": str(new_end)},
            )

    # Resolve term_id if not provided
    resolved_term_id = term_id or 1

    # Insert new membership
    new_membership = Membership(
        person_id=person.id,
        lc_id=lc.id,
        position_id=pos.id,
        function_id=func.id if func else None,
        term_id=resolved_term_id,
        start_date=start_date,
        end_date=end_date,
    )
    session.add(new_membership)
    session.flush()

    if team_id:
        tm = TeamMember(
            team_id=team_id,
            membership_id=new_membership.id,
            start_date=start_date,
            end_date=end_date,
        )
        session.add(tm)
        session.flush()

    # Record audit log for membership creation
    acting = actor_memberships[0] if actor_memberships else None
    record_audit(
        session,
        action="membership.create",
        resource_type="membership",
        resource_id=new_membership.id,
        summary=f"Added member to LC {lc.name}",
        actor_membership_id=acting.membership_id if acting else None,
        diff={"after": {"lc_id": lc.id, "position_id": pos.id, "start_date": str(start_date)}},
    )

    return {"status": "created"}


# ---------------------------------------------------------------------------
# Spec §2A.5: extendTerm
# ---------------------------------------------------------------------------


def extend_term(
    session: Session,
    actor_memberships: Sequence[MembershipContext],
    membership_id: int,
    new_end_date: date,
) -> dict[str, Any]:
    """Extend membership term per Spec §2A.5 and §3.4."""
    m = session.get(Membership, membership_id)
    if not m:
        return {"status": "rejected", "message": "Membership not found."}

    target_ctx = build_membership_context(session, m)
    if not can_extend_term(actor_memberships, target_ctx):
        return {"status": "rejected", "message": "You can't extend this term."}

    if m.end_date and new_end_date <= m.end_date:
        return {"status": "rejected", "message": "Choose an end date after the current end date."}

    old_end = m.end_date
    m.end_date = new_end_date
    session.flush()

    acting = actor_memberships[0] if actor_memberships else None
    record_audit(
        session,
        action="membership.extend_term",
        resource_type="membership",
        resource_id=m.id,
        summary=f"Extended term of membership {m.id}",
        actor_membership_id=acting.membership_id if acting else None,
        diff={"before": str(old_end), "after": str(new_end_date)},
    )

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Spec §2A.5: moveToTeam
# ---------------------------------------------------------------------------


def move_to_team(
    session: Session,
    actor_memberships: Sequence[MembershipContext],
    membership_id: int,
    team_id: int,
) -> dict[str, Any]:
    """Move member to a different team in same LC and function per Spec §2A.5 and §5.1."""
    m = session.get(Membership, membership_id)
    if not m:
        return {"status": "rejected", "message": "Membership not found."}

    target_ctx = build_membership_context(session, m)
    if not can_move_to_team(actor_memberships, target_ctx):
        return {"status": "rejected", "message": "You can't move this person."}

    new_team = session.get(Team, team_id)
    if not new_team:
        return {"status": "rejected", "message": "Team not found."}

    if new_team.lc_id != m.lc_id or new_team.function_id != m.function_id:
        return {"status": "rejected", "message": "Choose a team in the same LC and function."}

    today = date.today()

    # End current team_member row
    stmt = select(TeamMember).where(
        TeamMember.membership_id == m.id,
        TeamMember.start_date <= today,
        or_(TeamMember.end_date.is_(None), TeamMember.end_date >= today),
    )
    current_tm = session.execute(stmt).scalars().first()
    old_team_id = current_tm.team_id if current_tm else None
    if current_tm:
        current_tm.end_date = today

    # Insert new team_member row (Spec §5.1: no in-place mutation, history is preserved)
    new_tm = TeamMember(
        team_id=new_team.id,
        membership_id=m.id,
        start_date=today,
        end_date=m.end_date,
    )
    session.add(new_tm)
    session.flush()

    acting = actor_memberships[0] if actor_memberships else None
    record_audit(
        session,
        action="team_member.move",
        resource_type="team_member",
        resource_id=new_tm.id,
        summary=f"Moved membership {m.id} to team {new_team.name}",
        actor_membership_id=acting.membership_id if acting else None,
        diff={"before": {"team_id": old_team_id}, "after": {"team_id": new_team.id}},
    )

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Spec §2A.5: getMembershipDetail
# ---------------------------------------------------------------------------


def get_membership_detail(
    session: Session,
    actor_memberships: Sequence[MembershipContext],
    membership_id: int,
) -> dict[str, Any] | None:
    """Detail payload for the Manage Membership dialog per Spec §2A.5."""
    m = session.get(Membership, membership_id)
    if not m:
        return None

    person = session.get(Person, m.person_id)
    lc = session.get(LC, m.lc_id)
    pos = session.get(Position, m.position_id)
    func = session.get(Function, m.function_id) if m.function_id else None

    # Current team
    today = date.today()
    stmt = select(TeamMember).where(
        TeamMember.membership_id == m.id,
        TeamMember.start_date <= today,
        or_(TeamMember.end_date.is_(None), TeamMember.end_date >= today),
    )
    current_tm = session.execute(stmt).scalars().first()
    curr_team = session.get(Team, current_tm.team_id) if current_tm else None

    # Team options in same LC & function
    teams_stmt = select(Team).where(
        Team.lc_id == m.lc_id,
        Team.function_id == m.function_id,
    )
    if curr_team:
        teams_stmt = teams_stmt.where(Team.id != curr_team.id)
    team_options = session.execute(teams_stmt).scalars().all()

    pos_key = pos.key if pos else "member"
    rank = getattr(pos, "rank", None) or POSITION_RANKS.get(pos_key, 1)

    return {
        "membershipId": str(m.id),
        "personName": person.full_name if person else "",
        "position": {
            "key": pos_key,
            "label": pos.label if pos else pos_key,
            "level": "mc" if lc and lc.type.value == "MC" else "lc",
            "rank": rank,
            "canAddSameRank": getattr(pos, "can_add_same_rank", False)
            or (pos_key in {"lcp", "mcp"}),
            "presidential": pos_key in {"lcp", "mcp"},
            "homeChartScope": "all" if lc and lc.type.value == "MC" else "team",
            "holdsTeam": pos_key in {"member", "team_leader"},
        },
        "function": {"key": func.key, "label": func.label} if func else None,
        "lc": {
            "id": str(lc.id) if lc else "",
            "name": lc.name if lc else "",
            "type": lc.type.value.lower() if lc else "lc",
        },
        "startDate": str(m.start_date),
        "endDate": str(m.end_date) if m.end_date else None,
        "currentTeam": {"id": str(curr_team.id), "name": curr_team.name} if curr_team else None,
        "teamOptions": [
            {
                "id": str(t.id),
                "name": t.name,
                "lcId": str(t.lc_id),
                "functionKey": func.key if func else "",
            }
            for t in team_options
        ],
    }
