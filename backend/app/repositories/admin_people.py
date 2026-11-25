"""People and memberships on the Admin console (spec §1.5, §2A.2, ticket DEV-47).

The admin-side version of the Membership summary's Add member (§2A.5), but broader:
someone holding `manage` on `person` / `membership` is not limited to one LC or team.
What still applies to every write:

- the hierarchy rule (§3.4, `can_admin_manage_membership`): nobody changes their own
  memberships, and the position involved must rank below the actor's;
- the level-match rule (§3.6): a position's level must equal its LC's type;
- the overlap and MC→LC rules shared with Add member (`membership_conflict`), and the
  transfer rule (`end_memberships_in_other_lcs`).

Nothing here deletes a row. Deactivating a person sets `person.status = INACTIVE` and
end-dates their current memberships, so membership and KPI history stay exactly as
they were (§1.5). Every change writes an audit entry (§8.4) that names people by id
only: no names or emails, because audit entries can never be edited or deleted.

The functions don't commit. The API route commits, so a change and its audit entries
are saved together or not at all.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.permissions import MembershipContext, can_admin_manage_membership
from app.core.sessions import revoke_sessions_for_person
from app.models.membership import Membership, Team, TeamMember
from app.models.org import LC, Function, Position, Term
from app.models.person import SIGN_IN_BLOCKED, Person, PersonStatus
from app.repositories.lc import refresh_person_timezone
from app.repositories.membership import (
    _audit_actor,
    _position_level,
    _resolve_term_id,
    effective_position_rank,
    end_memberships_in_other_lcs,
    end_team_rows,
    is_current_membership,
    membership_conflict,
    no_term_message,
    person_name_parts,
)


class PersonNotFoundError(LookupError):
    """No person with that id (an ANONYMISED one counts as not found)."""


class EmailTakenError(ValueError):
    """Another person already has that AIESEC email."""


class NotAllowedError(PermissionError):
    """The hierarchy rule (§3.4) refuses this change. The message says why."""


Result = dict[str, Any]


def _rejected(message: str) -> Result:
    return {"status": "rejected", "message": message}


# ---------------------------------------------------------------------------
# Shared checks
# ---------------------------------------------------------------------------


def _get_person(session: Session, person_id: int) -> Person:
    """The person, or PersonNotFoundError. After a deletion request (§8) an
    ANONYMISED record is no longer anyone's, so it can't be edited here."""
    person = session.get(Person, person_id)
    if person is None or person.status == PersonStatus.ANONYMISED:
        raise PersonNotFoundError(f"Person {person_id} not found")
    return person


def clean_aiesec_email(email: str, allowed_domains: Collection[str]) -> str:
    """Lower-cased, trimmed, and on an allowed domain, or ValueError.

    Sign-in only accepts `ALLOWED_EMAIL_DOMAINS` (docs/auth.md), so a person added
    with any other address could never sign in. Checking here catches the typo.
    """
    clean = email.strip().lower()
    local, _, domain = clean.partition("@")
    if not local or not domain or " " in clean or "@" in domain:
        raise ValueError("Enter a valid email address.")
    if domain not in allowed_domains:
        allowed = ", ".join(f"@{d}" for d in sorted(allowed_domains))
        raise ValueError(f"Use an AIESEC email address ({allowed}).")
    return clean


def _ensure_email_free(session: Session, email: str, *, except_person_id: int | None) -> None:
    stmt = select(Person.id).where(func.lower(Person.aiesec_email) == email)
    if except_person_id is not None:
        stmt = stmt.where(Person.id != except_person_id)
    if session.execute(stmt).first() is not None:
        raise EmailTakenError("Someone already has that email address.")


def _current_and_future_memberships(
    session: Session, person_id: int, today: date
) -> Sequence[Membership]:
    """Memberships that haven't ended yet: the ones that give, or will give, access."""
    return (
        session.execute(
            select(Membership).where(
                Membership.person_id == person_id,
                or_(Membership.end_date.is_(None), Membership.end_date >= today),
            )
        )
        .scalars()
        .all()
    )


def _check_outranks_person(
    session: Session,
    actor_memberships: Sequence[MembershipContext],
    person: Person,
    *,
    today: date,
    allow_self: bool,
) -> None:
    """NotAllowedError unless the actor outranks every position the person holds or
    is about to hold (spec §3.4).

    This matters for more than memberships: the linked EXPA id decides who signs in as
    this person (the AIESEC email only picks the account for a first sign-in), so
    without it an MCD could unlink or re-point an MCP's account at one of their own.
    `allow_self` lets an admin fix their own name and email.
    """
    acting_person_ids = {m.person_id for m in actor_memberships}
    if person.id in acting_person_ids:
        if allow_self:
            return
        raise NotAllowedError("You can't do this to your own record.")

    for membership in _current_and_future_memberships(session, person.id, today):
        pos = session.get(Position, membership.position_id)
        allowed, reason = can_admin_manage_membership(
            actor_memberships,
            target_person_id=person.id,
            target_position_key=pos.key if pos else "member",
            target_position_rank=effective_position_rank(pos),
            target_lc_id=membership.lc_id,
            adding=False,
        )
        if not allowed:
            raise NotAllowedError(reason or "You can't change this person.")


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------


def _escape_like(text: str) -> str:
    """Make `%`, `_` and `\\` match themselves in an ILIKE pattern."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def person_row(person: Person, *, has_active_membership: bool) -> Result:
    """The `AdminPersonRow` shape from frontend/src/api/types.ts."""
    first_name, last_name = person_name_parts(person)
    return {
        "id": str(person.id),
        "firstName": first_name,
        "lastName": last_name,
        "email": person.aiesec_email,
        "active": has_active_membership,
        "status": person.status.value.lower(),
        "expaLinked": person.expa_id is not None,
    }


def _people_with_active_membership(
    session: Session, person_ids: Sequence[int], today: date
) -> set[int]:
    if not person_ids:
        return set()
    stmt = select(Membership.person_id).where(
        Membership.person_id.in_(person_ids),
        is_current_membership(today),
    )
    return set(session.execute(stmt).scalars().all())


def get_person_row(session: Session, person_id: int, *, today: date | None = None) -> Result:
    """One person in the `AdminPersonRow` shape, or PersonNotFoundError."""
    person = _get_person(session, person_id)
    active = _people_with_active_membership(session, [person.id], today or date.today())
    return person_row(person, has_active_membership=person.id in active)


def list_people(
    session: Session,
    *,
    search: str = "",
    page: int = 0,
    page_size: int = 10,
    today: date | None = None,
) -> Result:
    """Everyone except ANONYMISED records, with or without a current membership.

    Search (name or email), sort (last name, then first name) and pagination all run
    in the query, so the screen works at any size (§2A). `person` still has a single
    `full_name`, so "last name" is everything after the first space, the same split as
    `person_name_parts`.
    """
    ref_date = today or date.today()
    base = select(Person).where(Person.status != PersonStatus.ANONYMISED)
    needle = search.strip()
    if needle:
        pattern = f"%{_escape_like(needle)}%"
        base = base.where(
            or_(
                Person.full_name.ilike(pattern, escape="\\"),
                Person.aiesec_email.ilike(pattern, escape="\\"),
            )
        )

    total = session.execute(select(func.count()).select_from(base.subquery())).scalar_one()

    last_name = func.lower(func.substr(Person.full_name, func.strpos(Person.full_name, " ") + 1))
    people = (
        session.execute(
            base.order_by(last_name, func.lower(Person.full_name), Person.id)
            .offset(max(page, 0) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    active = _people_with_active_membership(session, [p.id for p in people], ref_date)
    rows = [person_row(p, has_active_membership=p.id in active) for p in people]
    return {"rows": rows, "total": total}


def _clean_name(first_name: str, last_name: str) -> str:
    first, last = first_name.strip(), last_name.strip()
    if not first or not last:
        raise ValueError("Enter a first name and a last name.")
    return f"{first} {last}"


def create_person(
    session: Session,
    actor_memberships: Sequence[MembershipContext],
    *,
    first_name: str,
    last_name: str,
    email: str,
    allowed_domains: Collection[str],
    today: date | None = None,
) -> Person:
    """Add a person with no memberships yet. Assigning one is a separate step."""
    full_name = _clean_name(first_name, last_name)
    clean_email = clean_aiesec_email(email, allowed_domains)
    _ensure_email_free(session, clean_email, except_person_id=None)

    person = Person(
        full_name=full_name,
        aiesec_email=clean_email,
        join_date=today or date.today(),
        status=PersonStatus.ACTIVE,
    )
    session.add(person)
    session.flush()
    record_audit(
        session,
        action="person.create",
        resource_type="person",
        resource_id=person.id,
        summary=f"Person {person.id} added on the Admin console",
        **_audit_actor(actor_memberships),
        diff={"after": {"status": PersonStatus.ACTIVE.value}},
    )
    return person


def update_person(
    session: Session,
    actor_memberships: Sequence[MembershipContext],
    person_id: int,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    allowed_domains: Collection[str],
    today: date | None = None,
) -> Person:
    """Change a person's name and/or AIESEC email. Fields left as None are unchanged.

    All or nothing: every check runs before anything is changed, so a refused edit
    (say, the email is taken) leaves the name alone too. The audit entry lists which
    fields changed (`name`, `aiesec_email`), never the old or new values.
    """
    ref_date = today or date.today()
    person = _get_person(session, person_id)
    _check_outranks_person(session, actor_memberships, person, today=ref_date, allow_self=True)

    new_full_name = person.full_name
    if first_name is not None or last_name is not None:
        current_first, current_last = person_name_parts(person)
        new_full_name = _clean_name(
            first_name if first_name is not None else current_first,
            last_name if last_name is not None else current_last,
        )

    new_email = person.aiesec_email
    if email is not None:
        # The same address (any case) is not a change. Skipping validation here keeps
        # a name edit working for someone whose stored email is on a retired domain.
        if email.strip().lower() != person.aiesec_email.lower():
            clean_email = clean_aiesec_email(email, allowed_domains)
            _ensure_email_free(session, clean_email, except_person_id=person.id)
            new_email = clean_email

    changed: list[str] = []
    if new_full_name != person.full_name:
        person.full_name = new_full_name
        changed.append("name")
    if new_email != person.aiesec_email:
        person.aiesec_email = new_email
        changed.append("aiesec_email")

    if changed:
        session.flush()
        record_audit(
            session,
            action="person.edit",
            resource_type="person",
            resource_id=person.id,
            summary=f"Person {person.id} edited on the Admin console: {', '.join(changed)}",
            **_audit_actor(actor_memberships),
            diff={"changed_keys": changed},
        )
    return person


def deactivate_person(
    session: Session,
    actor_memberships: Sequence[MembershipContext],
    person_id: int,
    *,
    today: date | None = None,
) -> Person:
    """Set the person INACTIVE and end their current memberships. Deletes nothing.

    - `status = INACTIVE`, so they can no longer sign in (`get_current_person`), and
      their open sessions are revoked.
    - Each membership active today ends yesterday, so it stops giving access now. One
      that started today can't end before it began, so it ends today. Their team rows
      are cut to the same date. Each end is audit-logged.
    - Memberships that haven't started yet are left as they are. Being INACTIVE
      already blocks the access they would give, and a reactivation keeps them.
    - `membership`, `team_member` and `kpi_record` rows all stay, so reports and past
      totals don't change (§1.5).
    """
    ref_date = today or date.today()
    person = _get_person(session, person_id)
    if person.status == PersonStatus.INACTIVE:
        raise ValueError("This person is already deactivated.")
    _check_outranks_person(session, actor_memberships, person, today=ref_date, allow_self=False)

    audit_actor = _audit_actor(actor_memberships)
    yesterday = ref_date - timedelta(days=1)
    active_now = session.execute(
        select(Membership).where(
            Membership.person_id == person.id,
            Membership.start_date <= ref_date,
            or_(Membership.end_date.is_(None), Membership.end_date >= ref_date),
        )
    ).scalars()
    ended: list[int] = []
    for membership in active_now:
        old_end = membership.end_date
        new_end = max(yesterday, membership.start_date)
        membership.end_date = new_end
        end_team_rows(session, membership_id=membership.id, end_date=new_end)
        record_audit(
            session,
            action="membership.end_term",
            resource_type="membership",
            resource_id=membership.id,
            summary="Membership ended because the person was deactivated",
            **audit_actor,
            diff={"before": str(old_end), "after": str(new_end)},
        )
        ended.append(membership.id)

    old_status = person.status
    person.status = PersonStatus.INACTIVE
    session.flush()
    # Sign them out everywhere now; without this a session would last until it expires.
    sessions_revoked = revoke_sessions_for_person(session, person.id)
    record_audit(
        session,
        action="person.deactivate",
        resource_type="person",
        resource_id=person.id,
        summary=f"Person {person.id} deactivated; {len(ended)} membership(s) ended",
        **audit_actor,
        diff={
            "before": {"status": old_status.value},
            "after": {"status": PersonStatus.INACTIVE.value},
            "memberships_ended": ended,
            "sessions_revoked": sessions_revoked,
        },
    )
    return person


def unlink_expa(
    session: Session,
    actor_memberships: Sequence[MembershipContext],
    person_id: int,
    *,
    today: date | None = None,
) -> Person:
    """Clear the person's EXPA link and sign them out everywhere.

    The next sign-in matches by AIESEC email and links again. So to fix a wrong match,
    correct the email first, then unlink. The audit entry says only that a link was
    removed, never the EXPA id (spec §8.4).
    """
    ref_date = today or date.today()
    person = _get_person(session, person_id)
    if person.expa_id is None:
        raise ValueError("This person isn't linked to EXPA.")
    _check_outranks_person(session, actor_memberships, person, today=ref_date, allow_self=False)

    person.expa_id = None
    session.flush()
    sessions_revoked = revoke_sessions_for_person(session, person.id)
    record_audit(
        session,
        action="person.unlink_expa",
        resource_type="person",
        resource_id=person.id,
        summary=f"EXPA account unlinked from person {person.id}",
        **_audit_actor(actor_memberships),
        diff={
            "before": {"expaLinked": True},
            "after": {"expaLinked": False},
            "sessions_revoked": sessions_revoked,
        },
    )
    return person


def reactivate_person(
    session: Session,
    actor_memberships: Sequence[MembershipContext],
    person_id: int,
    *,
    today: date | None = None,
) -> Person:
    """Undo a deactivation: `status` back to ACTIVE.

    Ended memberships stay ended (they are history). Give the person access again by
    assigning a new membership.
    """
    ref_date = today or date.today()
    person = _get_person(session, person_id)
    if person.status != PersonStatus.INACTIVE:
        raise ValueError("Only a deactivated person can be reactivated.")
    _check_outranks_person(session, actor_memberships, person, today=ref_date, allow_self=False)

    person.status = PersonStatus.ACTIVE
    session.flush()
    record_audit(
        session,
        action="person.reactivate",
        resource_type="person",
        resource_id=person.id,
        summary=f"Person {person.id} reactivated",
        **_audit_actor(actor_memberships),
        diff={
            "before": {"status": PersonStatus.INACTIVE.value},
            "after": {"status": PersonStatus.ACTIVE.value},
        },
    )
    return person


# ---------------------------------------------------------------------------
# Memberships
# ---------------------------------------------------------------------------


def list_person_memberships(
    session: Session, person_id: int, *, today: date | None = None
) -> list[Result]:
    """Every membership the person has held (past, current and future), newest
    first, in the `AdminMembershipRow` shape."""
    ref_date = today or date.today()
    person = _get_person(session, person_id)
    # Same rule as `is_current_membership` (Decision 1): a deactivated person's kept
    # future membership must not show as current once its start date arrives.
    person_counts = person.status not in SIGN_IN_BLOCKED
    memberships = (
        session.execute(
            select(Membership)
            .where(Membership.person_id == person_id)
            .order_by(Membership.start_date.desc(), Membership.id.desc())
        )
        .scalars()
        .all()
    )

    # The team each membership was last in (its current one, or its final one if
    # it has ended), for display only.
    team_names: dict[int, str] = {}
    if memberships:
        team_rows = session.execute(
            select(TeamMember.membership_id, Team.name)
            .join(Team, Team.id == TeamMember.team_id)
            .where(TeamMember.membership_id.in_([m.id for m in memberships]))
            .order_by(TeamMember.start_date, TeamMember.id)
        ).tuples()
        for membership_id, team_name in team_rows:
            team_names[membership_id] = team_name

    rows: list[Result] = []
    for m in memberships:
        lc = session.get(LC, m.lc_id)
        pos = session.get(Position, m.position_id)
        fn = session.get(Function, m.function_id) if m.function_id else None
        term = session.get(Term, m.term_id)
        rows.append(
            {
                "id": str(m.id),
                "lc": {
                    "id": str(m.lc_id),
                    "name": lc.name if lc else "",
                    "type": lc.type.value.lower() if lc else "lc",
                },
                "position": {"key": pos.key, "label": pos.label} if pos else None,
                "function": {"key": fn.key, "label": fn.label} if fn else None,
                "termName": term.name if term else None,
                "teamName": team_names.get(m.id),
                "startDate": m.start_date.isoformat(),
                "endDate": m.end_date.isoformat() if m.end_date else None,
                "current": person_counts
                and m.start_date <= ref_date
                and (m.end_date is None or m.end_date >= ref_date),
            }
        )
    return rows


def _level_problem(pos: Position, lc: LC) -> str | None:
    """Spec §3.6: a position's level must equal its LC's type."""
    if _position_level(pos) != lc.type.value.lower():
        kind = "the MC" if lc.type.value == "MC" else "an LC"
        return f"{pos.label} can't be used in {kind}."
    return None


def _find_position(session: Session, key: str) -> Position | None:
    return session.execute(select(Position).where(Position.key == key)).scalar_one_or_none()


def _find_function(session: Session, key: str) -> Function | None:
    return session.execute(select(Function).where(Function.key == key)).scalar_one_or_none()


def assign_membership(
    session: Session,
    actor_memberships: Sequence[MembershipContext],
    *,
    person_id: int,
    lc_id: int,
    position_key: str,
    function_key: str | None,
    start_date: date,
    end_date: date,
    team_id: int | None = None,
    term_id: int | None = None,
) -> Result:
    """Give an existing person a new membership (spec §2A.2 "Assign").

    This is also how a transfer works: assigning someone to a different LC ends their
    memberships in other LCs the day before the new one starts (§5.1, §3.6). Returns
    `{"status": "ok", "membershipId": ...}` or `{"status": "rejected", ...}`.
    """
    person = _get_person(session, person_id)
    if person.status == PersonStatus.INACTIVE:
        return _rejected("Reactivate this person before assigning a membership.")
    if end_date < start_date:
        return _rejected("The end date must be on or after the start date.")

    lc = session.get(LC, lc_id)
    if lc is None:
        return _rejected("LC not found.")
    if not lc.active:
        return _rejected("That LC is inactive.")

    pos = _find_position(session, position_key)
    if pos is None or not pos.active:
        return _rejected("Choose a position that is in use.")

    fn = None
    if function_key is not None:
        fn = _find_function(session, function_key)
        if fn is None or not fn.active:
            return _rejected("Choose a function that is in use.")

    allowed, reason = can_admin_manage_membership(
        actor_memberships,
        target_person_id=person.id,
        target_position_key=pos.key,
        target_position_rank=effective_position_rank(pos),
        target_lc_id=lc.id,
        adding=True,
    )
    if not allowed:
        return _rejected(reason or "You can't assign this membership.")

    level_problem = _level_problem(pos, lc)
    if level_problem is not None:
        return _rejected(level_problem)

    if team_id is not None:
        team = session.get(Team, team_id)
        if team is None or team.lc_id != lc.id or team.function_id != (fn.id if fn else None):
            return _rejected("Choose a team in the same LC and function.")

    resolved_term_id = _resolve_term_id(session, term_id, start_date)
    if resolved_term_id is None:
        return _rejected(no_term_message(session, term_id))

    conflict = membership_conflict(
        session,
        person_id=person.id,
        lc=lc,
        function_id=fn.id if fn else None,
        start_date=start_date,
        end_date=end_date,
        detailed=True,
    )
    if conflict is not None:
        return _rejected(conflict)

    audit_actor = _audit_actor(actor_memberships)
    end_memberships_in_other_lcs(
        session,
        person_id=person.id,
        lc_id=lc.id,
        start_date=start_date,
        end_date=end_date,
        audit_actor=audit_actor,
    )

    membership = Membership(
        person_id=person.id,
        lc_id=lc.id,
        position_id=pos.id,
        function_id=fn.id if fn else None,
        term_id=resolved_term_id,
        start_date=start_date,
        end_date=end_date,
    )
    session.add(membership)
    session.flush()
    if team_id is not None:
        session.add(
            TeamMember(
                team_id=team_id,
                membership_id=membership.id,
                start_date=start_date,
                end_date=end_date,
            )
        )
        session.flush()

    record_audit(
        session,
        action="membership.create",
        resource_type="membership",
        resource_id=membership.id,
        summary=f"Membership {membership.id} assigned to person {person.id} on the Admin console",
        **audit_actor,
        diff={
            "after": {
                "person_id": person.id,
                "lc_id": lc.id,
                "position_id": pos.id,
                "function_id": fn.id if fn else None,
                "team_id": team_id,
                "start_date": str(start_date),
                "end_date": str(end_date),
            }
        },
    )
    # Timezone follows the person's most recent membership (spec §4.1).
    refresh_person_timezone(session, person_id=person.id, as_of=start_date)
    return {"status": "ok", "membershipId": str(membership.id)}


@dataclass(frozen=True)
class MembershipCorrection:
    """What to change on a membership. None means "leave as it is".

    `clear_function` removes the function (some positions, such as LCP, aren't tied to
    one); it is separate from `function_key = None`, which means "unchanged".
    """

    position_key: str | None = None
    function_key: str | None = None
    clear_function: bool = False
    start_date: date | None = None
    end_date: date | None = None


def _overlaps_other_lc(
    session: Session, membership: Membership, start_date: date, end_date: date
) -> bool:
    stmt = select(Membership.id).where(
        Membership.person_id == membership.person_id,
        Membership.id != membership.id,
        Membership.lc_id != membership.lc_id,
        Membership.start_date <= end_date,
        or_(Membership.end_date.is_(None), Membership.end_date >= start_date),
    )
    return session.execute(stmt).first() is not None


def correct_membership(
    session: Session,
    actor_memberships: Sequence[MembershipContext],
    membership_id: int,
    correction: MembershipCorrection,
) -> Result:
    """Fix a mistake in a membership's position, function or dates (spec §2A.2 "Correct").

    This edits the row in place, which is only right for a data-entry mistake. A real
    change of role still ends this membership and assigns a new one, so history shows
    what actually happened (§5.1). The LC can't be corrected: moving someone to another
    LC is a transfer, done with Assign.

    The audit entry holds the before and after of every changed field, as ids and
    dates only.
    """
    m = session.get(Membership, membership_id)
    if m is None:
        return _rejected("Membership not found.")
    lc = session.get(LC, m.lc_id)
    old_pos = session.get(Position, m.position_id)
    if lc is None or old_pos is None:
        return _rejected("Membership not found.")

    # Deactivating ended this person's memberships on purpose. Correcting dates could
    # silently bring one back, so a deactivated person must be reactivated first. (End
    # has no such check: ending a membership can only shorten it, which is harmless.)
    owner = session.get(Person, m.person_id)
    if owner is not None and owner.status == PersonStatus.INACTIVE:
        return _rejected("Reactivate this person before assigning a membership.")

    # The hierarchy rule on the membership as it is now (§3.4)...
    allowed, reason = can_admin_manage_membership(
        actor_memberships,
        target_person_id=m.person_id,
        target_position_key=old_pos.key,
        target_position_rank=effective_position_rank(old_pos),
        target_lc_id=m.lc_id,
        adding=False,
    )
    if not allowed:
        return _rejected(reason or "You can't change this membership.")

    new_pos = old_pos
    if correction.position_key is not None and correction.position_key != old_pos.key:
        found = _find_position(session, correction.position_key)
        if found is None or not found.active:
            return _rejected("Choose a position that is in use.")
        new_pos = found
        # ...and on the position it would become.
        allowed, reason = can_admin_manage_membership(
            actor_memberships,
            target_person_id=m.person_id,
            target_position_key=new_pos.key,
            target_position_rank=effective_position_rank(new_pos),
            target_lc_id=m.lc_id,
            adding=False,
        )
        if not allowed:
            return _rejected(reason or "You can't change this membership.")
        level_problem = _level_problem(new_pos, lc)
        if level_problem is not None:
            return _rejected(level_problem)

    new_function_id = m.function_id
    if correction.clear_function:
        new_function_id = None
    elif correction.function_key is not None:
        fn = _find_function(session, correction.function_key)
        if fn is None:
            return _rejected("Choose a function that is in use.")
        if fn.id != m.function_id and not fn.active:
            return _rejected("Choose a function that is in use.")
        new_function_id = fn.id

    if new_function_id != m.function_id:
        has_team = session.execute(
            select(TeamMember.id).where(TeamMember.membership_id == m.id)
        ).first()
        if has_team is not None:
            return _rejected(
                "This membership has been in a team of its current function. End it and "
                "assign a new one instead, so the team history stays right."
            )

    new_start = correction.start_date or m.start_date
    new_end = correction.end_date or m.end_date
    if new_end is None:
        return _rejected("Enter an end date.")
    if new_end < new_start:
        return _rejected("The end date must be on or after the start date.")

    new_term_id = m.term_id
    term = session.get(Term, m.term_id)
    if term is None or not (term.start_date <= new_start <= term.end_date):
        resolved = _resolve_term_id(session, None, new_start)
        if resolved is None:
            return _rejected("No term covers that start date.")
        new_term_id = resolved

    # Moving the start later pulls the earlier team rows forward with it, so a team
    # row never begins before its membership. A row that already ended before the
    # new start would be left with nothing, so the whole correction is refused.
    team_rows_to_move: list[TeamMember] = []
    if new_start > m.start_date:
        team_rows_to_move = list(
            session.execute(
                select(TeamMember).where(
                    TeamMember.membership_id == m.id, TeamMember.start_date < new_start
                )
            ).scalars()
        )
        if any(row.end_date is not None and row.end_date < new_start for row in team_rows_to_move):
            return _rejected(
                "A team row of this membership ended before that start date. Choose an "
                "earlier start date, or end this membership and assign a new one."
            )

    if new_start != m.start_date or new_end != m.end_date:
        if _overlaps_other_lc(session, m, new_start, new_end):
            return _rejected(
                "These dates overlap this person's membership in another LC. "
                "Correct or end that one first."
            )

    conflict = membership_conflict(
        session,
        person_id=m.person_id,
        lc=lc,
        function_id=new_function_id,
        start_date=new_start,
        end_date=new_end,
        detailed=True,
        ignore_membership_id=m.id,
    )
    if conflict is not None:
        return _rejected(conflict)

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    def track(field: str, old: object, new: object) -> None:
        if old != new:
            before[field] = old
            after[field] = new

    track("position_id", m.position_id, new_pos.id)
    track("function_id", m.function_id, new_function_id)
    track("start_date", str(m.start_date), str(new_start))
    track("end_date", str(m.end_date) if m.end_date else None, str(new_end))
    track("term_id", m.term_id, new_term_id)
    if not after:
        return {"status": "ok"}

    old_end = m.end_date
    m.position_id = new_pos.id
    m.function_id = new_function_id
    m.start_date = new_start
    m.end_date = new_end
    m.term_id = new_term_id
    for row in team_rows_to_move:
        row.start_date = new_start
    if old_end is None or new_end < old_end:
        end_team_rows(session, membership_id=m.id, end_date=new_end)
    session.flush()

    record_audit(
        session,
        action="membership.correct",
        resource_type="membership",
        resource_id=m.id,
        summary=f"Membership {m.id} corrected on the Admin console: {', '.join(after)}",
        **_audit_actor(actor_memberships),
        diff={"before": before, "after": after},
    )
    return {"status": "ok"}


def end_membership(
    session: Session,
    actor_memberships: Sequence[MembershipContext],
    membership_id: int,
    end_date: date,
) -> Result:
    """End a membership early (spec §2A.2 "End"). To make one longer, use Correct."""
    m = session.get(Membership, membership_id)
    if m is None:
        return _rejected("Membership not found.")
    pos = session.get(Position, m.position_id)

    allowed, reason = can_admin_manage_membership(
        actor_memberships,
        target_person_id=m.person_id,
        target_position_key=pos.key if pos else "member",
        target_position_rank=effective_position_rank(pos),
        target_lc_id=m.lc_id,
        adding=False,
    )
    if not allowed:
        return _rejected(reason or "You can't end this membership.")

    if end_date < m.start_date:
        return _rejected("A membership can't end before it started.")
    if m.end_date is not None and end_date >= m.end_date:
        return _rejected("Choose a date before the current end date. To extend, use Correct.")

    old_end = m.end_date
    m.end_date = end_date
    end_team_rows(session, membership_id=m.id, end_date=end_date)
    session.flush()
    record_audit(
        session,
        action="membership.end_term",
        resource_type="membership",
        resource_id=m.id,
        summary=f"Membership {m.id} ended on the Admin console",
        **_audit_actor(actor_memberships),
        diff={"before": str(old_end), "after": str(end_date)},
    )
    return {"status": "ok"}
