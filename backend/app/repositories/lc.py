"""Queries and mutations for the `lc` table.

Every mutating function calls `record_audit` in the same session so the
audit entry is saved if and only if the change is saved.
"""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.models.membership import Membership, Team
from app.models.org import LC, LCType, StateTimezone, Term

LC_DEFAULT_TIMEZONE = "Australia/Melbourne"


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
    LC_DEFAULT_TIMEZONE when the LC has no state or the state isn't in
    the lookup (e.g. the MC row, which has no state).
    """
    lc = session.get(LC, lc_id)
    if lc is None or lc.state is None:
        return LC_DEFAULT_TIMEZONE
    row = session.get(StateTimezone, lc.state)
    if row is None:
        return LC_DEFAULT_TIMEZONE
    return row.timezone


def create_lc(
    session: Session,
    *,
    name: str,
    lc_type: LCType,
    state: str | None = None,
    actor_membership_id: int | None = None,
) -> LC:
    """Insert a new LC row and audit-log the creation."""
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
) -> LC:
    """Set the Australian state for an LC and audit-log the change."""
    lc = session.get(LC, lc_id)
    if lc is None:
        raise ValueError(f"LC {lc_id} not found")
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
    return lc


def deactivate_lc(
    session: Session,
    *,
    lc_id: int,
    actor_membership_id: int | None = None,
) -> LC:
    """Mark an LC inactive. Historical records pointing at it are preserved.

    Per spec §1.5: deactivate/soft-delete for anything referenced by
    history; hard-delete is not offered.
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


def merge_lcs(
    session: Session,
    *,
    source_id: int,
    target_id: int,
    actor_membership_id: int | None = None,
) -> tuple[int, int]:
    """Merge source LC into target LC.

    Re-points active memberships and current-term teams from source to
    target. Historical records (ended memberships, past-term teams) stay
    pointing at source so historical reports remain accurate. Source is
    then marked inactive.

    Returns (memberships_moved, teams_moved).

    Raises ValueError if source == target or either LC doesn't exist.
    """
    if source_id == target_id:
        raise ValueError("source and target must differ")

    source = session.get(LC, source_id)
    if source is None:
        raise ValueError(f"LC {source_id} not found")

    target = session.get(LC, target_id)
    if target is None:
        raise ValueError(f"LC {target_id} not found")

    today = date.today()

    # Re-point active memberships (no end_date, or end_date in the future).
    result = session.execute(
        update(Membership)
        .where(
            Membership.lc_id == source_id,
            or_(Membership.end_date.is_(None), Membership.end_date >= today),
        )
        .values(lc_id=target_id)
    )
    memberships_moved: int = result.rowcount

    # Re-point teams whose term has not yet ended.
    current_team_ids = list(
        session.execute(
            select(Team.id)
            .join(Term, Team.term_id == Term.id)
            .where(Team.lc_id == source_id, Term.end_date >= today)
        ).scalars()
    )
    teams_moved = 0
    if current_team_ids:
        result2 = session.execute(
            update(Team)
            .where(Team.id.in_(current_team_ids))
            .values(lc_id=target_id)
        )
        teams_moved = result2.rowcount

    # Mark source inactive.
    source.active = False
    session.flush()

    record_audit(
        session,
        action="lc.merge",
        resource_type="lc",
        resource_id=source_id,
        summary=(
            f"LC {source_id} merged into LC {target_id}: "
            f"{memberships_moved} active memberships and {teams_moved} current-term teams re-pointed"
        ),
        actor_membership_id=actor_membership_id,
        diff={
            "source_id": source_id,
            "target_id": target_id,
            "memberships_moved": memberships_moved,
            "teams_moved": teams_moved,
        },
    )

    return memberships_moved, teams_moved
