"""Membership repository queries and lifecycle mutations.

Implements Spec §2A.5, §3.4, §3.6, §5.1, and §8.4.

"Current membership" is never a stored flag — it's derived from
`start_date`/`end_date` at query time (spec §4.1, §5.1), so a membership
change (position, function, team, leaving) only ever needs an end-date on the
old row and a new row, never an update to some `is_current` column that could
drift out of sync.
"""

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any, Literal

from sqlalchemy import ColumnElement, exists, or_, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.permissions import (
    POSITION_RANKS,
    PRESIDENTIAL_POSITIONS,
    MembershipContext,
    can_add_member,
    can_extend_term,
    can_move_to_team,
    can_view_membership,
    get_acting_membership,
    home_chart_scope,
    position_level,
    resolve_widest_scope,
)
from app.models.membership import Membership, Team, TeamMember
from app.models.org import LC, Function, Position, Term
from app.models.person import SIGN_IN_BLOCKED, Person, PersonStatus
from app.repositories.lc import refresh_person_timezone


def is_current_membership(ref_date: date) -> ColumnElement[bool]:
    """SQL condition: this membership counts as a current one on `ref_date`.

    Two things must both be true:
    - the dates cover the day (`start_date <= ref_date`, and the end date is empty
      or not before `ref_date`), and
    - the person can still sign in (their status is not in `SIGN_IN_BLOCKED`).

    The second part matters because deactivating someone ends the memberships that
    are running *today* but keeps future ones (so reactivating restores them). Without
    it, a kept future membership would start counting the day it begins, and the
    deactivated person would reappear as a member. ALUMNUS is not blocked, so an
    alumnus with a current membership still counts.

    There is no `Membership.person` relationship, hence the `exists()` subquery.
    """
    person_can_sign_in = exists(
        select(Person.id).where(
            Person.id == Membership.person_id,
            Person.status.not_in(SIGN_IN_BLOCKED),
        )
    )
    return (
        (Membership.start_date <= ref_date)
        & or_(Membership.end_date.is_(None), Membership.end_date >= ref_date)
        & person_can_sign_in
    )


def get_active_memberships_for_person(
    session: Session, person_id: int, as_of: date | None = None
) -> Sequence[Membership]:
    """Memberships for `person_id` that are current as of `as_of` (default: today).

    A membership is current when it has started (`start_date <= as_of`) and
    either has no end date yet or hasn't ended (`end_date IS NULL OR
    end_date >= as_of`). A person can hold several concurrent memberships
    (spec §5.1), so this can return more than one row.
    """
    ref_date = as_of if as_of is not None else date.today()
    stmt = select(Membership).where(
        Membership.person_id == person_id,
        is_current_membership(ref_date),
    )
    return session.execute(stmt).scalars().all()


# The three helpers below read a position's settings from the `position` table,
# which admins edit on the Positions & functions screen (DEV-0049). Each falls back
# to the hardcoded spec §2 values (by key) only while the column is still empty,
# e.g. on a database that hasn't run migration b4e81d2c9a07 yet.


def effective_position_rank(pos: Position | None) -> int:
    """`position.rank` when set, else the spec §2 fallback by key.

    Checked with `is not None` (not `or`) so a rank of 0 is used as-is.
    """
    if pos is not None and pos.rank is not None:
        return pos.rank
    pos_key = pos.key if pos else "member"
    return POSITION_RANKS.get(pos_key, 1)


def _position_can_add_same_rank(pos: Position | None) -> bool:
    """The president exception (spec §3.4): `position.can_add_same_rank` when set,
    else true only for the presidential keys."""
    if pos is not None and pos.can_add_same_rank is not None:
        return pos.can_add_same_rank
    pos_key = pos.key if pos else "member"
    return pos_key in PRESIDENTIAL_POSITIONS


def _position_level(pos: Position) -> Literal["lc", "mc"]:
    """Whether the position belongs to an LC or the MC (spec §3.6):
    `position.level` when set, else decided by key."""
    if pos.level == "lc":
        return "lc"
    if pos.level == "mc":
        return "mc"
    return position_level(pos.key)


def person_name_parts(person: Person) -> tuple[str, str]:
    """(first name, last name) for display.

    `person` still has a single `full_name` column (docs/data-model.md, "Known
    differences from the spec"), so this splits on the first space until the
    schema-alignment ticket adds `first_name` / `last_name`. Every caller goes
    through here, so that ticket only has to change this one function.
    """
    first_name = getattr(person, "first_name", "") or person.full_name.split(" ")[0]
    last_name = getattr(person, "last_name", "") or (
        " ".join(person.full_name.split(" ")[1:]) if " " in person.full_name else ""
    )
    return first_name, last_name


def position_payload(pos: Position | None, lc: LC | None) -> dict[str, Any]:
    """The `Position` shape from frontend/src/api/types.ts for a membership's position.

    `level`, `presidential` and `holdsTeam` are derived here until the
    schema-alignment ticket adds them as columns (spec §2). `homeChartScope`
    comes from `home_chart_scope` (docs/home-chart.md).
    """
    pos_key = pos.key if pos else "member"
    is_mc = lc is not None and lc.type.value == "MC"
    return {
        "key": pos_key,
        "label": pos.label if pos else pos_key,
        "level": "mc" if is_mc else "lc",
        "rank": effective_position_rank(pos),
        "canAddSameRank": _position_can_add_same_rank(pos),
        "presidential": pos_key in {"lcp", "mcp"},
        "homeChartScope": home_chart_scope(pos_key),
        "holdsTeam": pos_key in {"member", "team_leader"},
    }


def _audit_actor(actor_memberships: Sequence[MembershipContext]) -> dict[str, int | None]:
    """Who to name on an audit row: the actor's highest-ranking membership and their person."""
    acting = get_acting_membership(actor_memberships)
    return {
        "actor_membership_id": acting.membership_id if acting else None,
        "actor_person_id": acting.person_id if acting else None,
    }


def _resolve_term_id(session: Session, term_id: int | None, start_date: date) -> int | None:
    """The term a new membership belongs to, or None if there isn't a valid one.

    An explicit `term_id` must exist and cover `start_date` (callers turn None into
    a message with `no_term_message`); otherwise the term covering `start_date`
    (the latest-starting one if several overlap; the newest-created one if
    they also start on the same day, so the choice is never arbitrary).
    """
    if term_id is not None:
        term = session.get(Term, term_id)
        covers = term is not None and term.start_date <= start_date <= term.end_date
        return term_id if covers else None
    stmt = (
        select(Term.id)
        .where(Term.start_date <= start_date, Term.end_date >= start_date)
        .order_by(Term.start_date.desc(), Term.id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def no_term_message(session: Session, term_id: int | None) -> str:
    """The rejection text for when `_resolve_term_id` finds no term."""
    # A term that exists but doesn't cover the start date gets its own wording.
    if term_id is not None and session.get(Term, term_id) is not None:
        return "The start date isn't inside the chosen term."
    return "No term covers that start date."


def membership_conflict(
    session: Session,
    *,
    person_id: int,
    lc: LC,
    function_id: int | None,
    start_date: date,
    end_date: date,
    detailed: bool,
    ignore_membership_id: int | None = None,
) -> str | None:
    """Why `person_id` can't hold a membership in `lc` for these dates, or None.

    Shared by the Membership summary's Add member and the Admin console, so both
    apply the same rules:

    - Spec §3.6: no LC membership while an MC membership overlaps the dates. The
      message is generic on purpose and does not say why.
    - Spec §5.1: the same function can't be held twice in one LC with overlapping
      dates.
    - A new membership is refused while the person has one in a different LC that
      overlaps its dates and starts on or after its start date: the transfer rule
      would otherwise have to end a membership that hasn't begun. `detailed` picks
      the message: an admin (who can see every LC) is told which LC and date; an
      LC-scoped user gets a vague one, so they can't learn about another LC's
      records.

    `ignore_membership_id` leaves out the membership being corrected, so it isn't
    compared with itself.
    """
    theirs = [
        m
        for m in session.execute(select(Membership).where(Membership.person_id == person_id))
        .scalars()
        .all()
        if m.id != ignore_membership_id
    ]

    def overlaps(m: Membership) -> bool:
        return m.start_date <= end_date and (m.end_date is None or m.end_date >= start_date)

    if lc.type.value == "LC":
        for m in theirs:
            m_lc = session.get(LC, m.lc_id)
            if m_lc and m_lc.type.value == "MC" and overlaps(m):
                return "This person can't be added. Contact your MC."

    for m in theirs:
        if m.lc_id != lc.id and m.start_date >= start_date and overlaps(m):
            if not detailed:
                return "This person already has a membership coming up elsewhere. Contact your MC."
            other_lc = session.get(LC, m.lc_id)
            lc_name = other_lc.name if other_lc else "another LC"
            return (
                f"This person's membership in {lc_name} starts on "
                f"{m.start_date.strftime('%d %b %Y')}. "
                "Correct it first, or end this one before that date."
            )

    if function_id is not None:
        for m in theirs:
            if m.lc_id == lc.id and m.function_id == function_id and overlaps(m):
                return "This person already holds that function in this LC for overlapping dates."
    return None


def end_memberships_in_other_lcs(
    session: Session,
    *,
    person_id: int,
    lc_id: int,
    start_date: date,
    end_date: date,
    audit_actor: dict[str, int | None],
) -> None:
    """Transfer rule (spec §5.1, §3.6): a new membership in `lc_id` ends the person's
    memberships in every other LC on the day before it starts.

    Each one gets its own audit entry (§8.4), and its open team rows end with it.
    """
    theirs = (
        session.execute(
            select(Membership).where(
                Membership.person_id == person_id,
                Membership.lc_id != lc_id,
                Membership.start_date <= end_date,
                or_(Membership.end_date.is_(None), Membership.end_date >= start_date),
            )
        )
        .scalars()
        .all()
    )

    day_before = start_date - timedelta(days=1)
    for old_m in theirs:
        old_end = old_m.end_date
        # `membership_conflict` runs first and refuses any membership in another LC
        # that starts on or after `start_date`, so `day_before >= old_m.start_date`
        # always holds here and no "end before it began" case is needed.
        new_end = day_before
        old_m.end_date = new_end
        session.flush()
        end_team_rows(session, membership_id=old_m.id, end_date=new_end)

        record_audit(
            session,
            action="membership.end_term",
            resource_type="membership",
            resource_id=old_m.id,
            summary="Membership ended automatically due to transfer to another LC",
            **audit_actor,
            diff={"before": str(old_end), "after": str(new_end)},
        )


def end_team_rows(session: Session, *, membership_id: int, end_date: date) -> None:
    """Keep a membership's `team_member` rows inside its dates once it ends earlier.

    A team row that would outlast the membership is cut to the same end date, so
    nobody stays "in a team" after their membership is over. Rows that already
    ended earlier are left alone (they are history).
    """
    rows = session.execute(
        select(TeamMember).where(
            TeamMember.membership_id == membership_id,
            or_(TeamMember.end_date.is_(None), TeamMember.end_date > end_date),
        )
    ).scalars()
    for row in rows:
        row.end_date = max(end_date, row.start_date)
    session.flush()


def build_membership_context(session: Session, membership: Membership) -> MembershipContext:
    """Build a MembershipContext helper for permission evaluations."""
    pos = session.get(Position, membership.position_id)
    pos_key = pos.key if pos else "member"
    rank = effective_position_rank(pos)
    can_add_same_rank = _position_can_add_same_rank(pos)

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
    stmt = select(Membership).where(is_current_membership(ref_date))
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
        for p in session.execute(select(Person).where(Person.id.in_(person_ids))).scalars().all()
    }
    lcs = {lc.id: lc for lc in session.execute(select(LC)).scalars().all()}
    positions = {pos.id: pos for pos in session.execute(select(Position)).scalars().all()}
    functions = {fn.id: fn for fn in session.execute(select(Function)).scalars().all()}

    # Team member mappings
    team_members = (
        session.execute(
            select(TeamMember).where(
                TeamMember.membership_id.in_([m.id for m in memberships]),
                TeamMember.start_date <= ref_date,
                or_(TeamMember.end_date.is_(None), TeamMember.end_date >= ref_date),
            )
        )
        .scalars()
        .all()
    )
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

        first_name, last_name = person_name_parts(person)

        # A person with memberships in several LCs shows their most recent one: that
        # LC, and the roles they hold in it (concurrent functions stay listed together).
        latest = max(p_memberships, key=lambda m: (m.start_date, m.id))
        p_memberships = [m for m in p_memberships if m.lc_id == latest.lc_id]
        primary_lc = lcs.get(latest.lc_id)
        lc_payload = {
            "id": str(primary_lc.id) if primary_lc else "",
            "name": primary_lc.name if primary_lc else "",
            "type": primary_lc.type.value.lower() if primary_lc else "lc",
        }

        roles_payload: list[dict[str, Any]] = []
        for m in p_memberships:
            pos = positions.get(m.position_id)
            fn = functions.get(m.function_id) if m.function_id else None

            roles_payload.append(
                {
                    "membershipId": str(m.id),
                    "position": position_payload(pos, primary_lc),
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
    if not lc.active:
        return {"status": "rejected", "message": "That LC is inactive."}

    pos = session.execute(select(Position).where(Position.key == position_key)).scalar_one_or_none()
    if not pos:
        return {"status": "rejected", "message": "Position not found."}
    # An inactive position stays on existing memberships but is never given out
    # again (spec §1.5). Same rule as inactive LCs above.
    if not pos.active:
        return {"status": "rejected", "message": "That position is inactive."}

    func = None
    if function_key:
        func = session.execute(
            select(Function).where(Function.key == function_key)
        ).scalar_one_or_none()
        if func is None:
            return {"status": "rejected", "message": "Function not found."}
        if not func.active:
            return {"status": "rejected", "message": "That function is inactive."}

    # Authorise before touching the person table: a denied actor must not be able
    # to probe which emails exist (via `confirm_existing`). Spec §3.4, §3.6.
    allowed, reason = can_add_member(
        actor_memberships,
        target_lc_id=lc.id,
        target_lc_type=lc.type.value,
        target_position_key=pos.key,
        target_position_rank=effective_position_rank(pos),
        target_position_level=_position_level(pos),
        target_function_id=func.id if func else None,
        target_team_id=team_id,
    )
    if not allowed:
        return {"status": "rejected", "message": reason}

    # Same rule as moveToTeam: a team must belong to the target LC and function.
    if team_id is not None:
        team = session.get(Team, team_id)
        if team is None or team.lc_id != lc.id or team.function_id != (func.id if func else None):
            return {"status": "rejected", "message": "Choose a team in the same LC and function."}

    resolved_term_id = _resolve_term_id(session, term_id, start_date)
    if resolved_term_id is None:
        return {"status": "rejected", "message": no_term_message(session, term_id)}

    clean_email = email.strip().lower()

    # Check if person exists
    person = session.execute(
        select(Person).where(Person.aiesec_email == clean_email)
    ).scalar_one_or_none()

    # A deactivated person comes back only through the Admin console's Reactivate,
    # so a deactivation can't be undone by accident from the main app (DEV-47).
    if person is not None and person.status == PersonStatus.INACTIVE:
        return {"status": "rejected", "message": "This person can't be added. Contact your MC."}

    if person is None:
        if not first_name or not last_name or not first_name.strip() or not last_name.strip():
            return {"status": "needs_name"}
    elif not confirmed_existing:
        return {"status": "confirm_existing"}

    # Validate target against their other memberships (spec §3.6, §5.1)
    if person is not None:
        conflict = membership_conflict(
            session,
            person_id=person.id,
            lc=lc,
            function_id=func.id if func else None,
            start_date=start_date,
            end_date=end_date,
            detailed=False,
        )
        if conflict is not None:
            return {"status": "rejected", "message": conflict}

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
        end_memberships_in_other_lcs(
            session,
            person_id=person.id,
            lc_id=lc.id,
            start_date=start_date,
            end_date=end_date,
            audit_actor=_audit_actor(actor_memberships),
        )

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
    record_audit(
        session,
        action="membership.create",
        resource_type="membership",
        resource_id=new_membership.id,
        summary=f"Added member to LC {lc.name}",
        **_audit_actor(actor_memberships),
        diff={"after": {"lc_id": lc.id, "position_id": pos.id, "start_date": str(start_date)}},
    )

    # Timezone follows the person's most recent membership (spec §4.1).
    refresh_person_timezone(session, person_id=person.id, as_of=start_date)

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

    record_audit(
        session,
        action="membership.extend_term",
        resource_type="membership",
        resource_id=m.id,
        summary=f"Extended term of membership {m.id}",
        **_audit_actor(actor_memberships),
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

    record_audit(
        session,
        action="team_member.move",
        resource_type="team_member",
        resource_id=new_tm.id,
        summary=f"Moved membership {m.id} to team {new_team.name}",
        **_audit_actor(actor_memberships),
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

    # Same LC isolation as the list (§2A.5). Callers see "not found" either way, so
    # ids in other LCs are not confirmed to exist.
    if not can_view_membership(actor_memberships, build_membership_context(session, m)):
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

    return {
        "membershipId": str(m.id),
        "personName": person.full_name if person else "",
        "position": position_payload(pos, lc),
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
