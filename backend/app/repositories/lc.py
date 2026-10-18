"""Queries and mutations for the `lc` table.

Every mutating function calls `record_audit` in the same session so the
audit entry is saved if and only if the change is saved.
"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.org import LC, StateTimezone

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
