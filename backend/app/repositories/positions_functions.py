"""Queries and mutations for the `position` and `function` tables (spec §1.5, §2A.2).

Positions and functions are plain lookup tables, not hardcoded enums, so an admin
can add, rename, or deactivate them at runtime without a code change (spec §1.5).
They are never hard-deleted: deactivating is the soft delete. The database's FK
constraints enforce this — a row referenced by a membership row cannot be deleted.

Same shape as `app/repositories/lc.py`: one function per kind of change, and each
one writes its own audit action (`position.rename`, `position.deactivate`, ...) in
the same session, so the Auditing screen can filter by what happened.

Who may make a change (the `manage` grant and the hierarchy rule) is checked by
the endpoint before it calls these functions.
"""

import re
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.permissions import (
    ADMIN_POSITIONS,
    BASELINE_PERMISSION_MATRIX,
    FUNCTION_SCOPE_POSITIONS,
    MC_POSITIONS,
    POSITION_RANKS,
    PRESIDENTIAL_POSITIONS,
    TEAM_HOLDING_POSITIONS,
)
from app.models.org import Function, Position

# Positions that give access to the Admin console. Deactivating one is a way to
# lock every admin out (docs/admin-lockout-recovery.md), so it isn't allowed here.
ADMIN_ACCESS_POSITIONS = MC_POSITIONS | ADMIN_POSITIONS

# Position keys the code gives meaning to: permission grants, ranks, the president
# exception, team-holding and chart scope. Until the permission matrix is a table
# (DEV-51), a NEW position that got one of these keys would silently inherit those
# grants (e.g. a position named "Admin" becoming a real admin). So a new position
# never gets one, even when no row holds it yet: it gets `admin_2` etc. instead.
RESERVED_POSITION_KEYS: frozenset[str] = frozenset(
    {grant.position_key for grant in BASELINE_PERMISSION_MATRIX}
    | set(POSITION_RANKS)
    | ADMIN_POSITIONS
    | MC_POSITIONS
    | PRESIDENTIAL_POSITIONS
    | TEAM_HOLDING_POSITIONS
    | FUNCTION_SCOPE_POSITIONS
)


def _derive_key(label: str) -> str:
    """Turn a display label into a machine-readable key (lowercase, underscores)."""
    key = label.lower().strip()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = key.strip("_")
    return key[:50] or "item"


def _ensure_unique_key(
    session: Session,
    model: type[Position] | type[Function],
    base_key: str,
    *,
    reserved: frozenset[str] = frozenset(),
) -> str:
    """Return `base_key` if unused, otherwise append _2, _3, ... until it is.

    Keys in `reserved` count as used even when no row holds them yet.
    """
    existing = set(session.execute(select(model.key)).scalars()) | reserved
    key = base_key
    suffix = 2
    while key in existing:
        key = f"{base_key}_{suffix}"
        suffix += 1
    return key


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


def list_positions(session: Session, *, include_inactive: bool = False) -> Sequence[Position]:
    """Highest rank first, so the list reads top-down like the org chart."""
    stmt = select(Position).order_by(Position.rank.desc().nulls_last(), func.lower(Position.label))
    if not include_inactive:
        stmt = stmt.where(Position.active.is_(True))
    return session.execute(stmt).scalars().all()


def get_position(session: Session, position_id: int) -> Position | None:
    return session.get(Position, position_id)


def _require_position(session: Session, position_id: int) -> Position:
    position = get_position(session, position_id)
    if position is None:
        raise ValueError(f"Position {position_id} not found")
    return position


def create_position(
    session: Session,
    *,
    label: str,
    level: str,
    rank: int,
    can_add_same_rank: bool,
    actor_membership_id: int | None,
) -> Position:
    position = Position(
        key=_ensure_unique_key(
            session, Position, _derive_key(label), reserved=RESERVED_POSITION_KEYS
        ),
        label=label,
        level=level,
        rank=rank,
        can_add_same_rank=can_add_same_rank,
        active=True,
    )
    session.add(position)
    # Flush now so a duplicate name fails here (unique index) and we get an id.
    session.flush()
    record_audit(
        session,
        actor_membership_id=actor_membership_id,
        action="position.create",
        resource_type="position",
        resource_id=position.id,
        summary=f"Created position '{label}'",
    )
    return position


def rename_position(
    session: Session, *, position_id: int, new_label: str, actor_membership_id: int | None
) -> Position:
    position = _require_position(session, position_id)
    if new_label == position.label:
        return position

    old_label = position.label
    position.label = new_label
    session.flush()  # a duplicate name fails here, not at commit
    record_audit(
        session,
        actor_membership_id=actor_membership_id,
        action="position.rename",
        resource_type="position",
        resource_id=position.id,
        summary=f"Renamed position '{old_label}' to '{new_label}'",
        diff={"label": {"before": old_label, "after": new_label}},
    )
    return position


def set_position_details(
    session: Session,
    *,
    position_id: int,
    level: str | None,
    rank: int | None,
    can_add_same_rank: bool | None,
    actor_membership_id: int | None,
) -> Position:
    """Change level, rank and/or the president flag. `None` means "leave as it is".
    Writes one `position.edit` audit row listing what changed, or none if nothing did."""
    position = _require_position(session, position_id)

    diff: dict[str, Any] = {}
    if level is not None and level != position.level:
        diff["level"] = {"before": position.level, "after": level}
        position.level = level
    if rank is not None and rank != position.rank:
        diff["rank"] = {"before": position.rank, "after": rank}
        position.rank = rank
    if can_add_same_rank is not None and can_add_same_rank != position.can_add_same_rank:
        diff["can_add_same_rank"] = {
            "before": position.can_add_same_rank,
            "after": can_add_same_rank,
        }
        position.can_add_same_rank = can_add_same_rank

    if diff:
        record_audit(
            session,
            actor_membership_id=actor_membership_id,
            action="position.edit",
            resource_type="position",
            resource_id=position.id,
            summary=f"Edited position '{position.label}'",
            diff=diff,
        )
    return position


def set_position_active(
    session: Session, *, position_id: int, active: bool, actor_membership_id: int | None
) -> Position:
    """Deactivate or reactivate. Existing memberships keep the position either way;
    an inactive position is just no longer offered for new ones (spec §1.5)."""
    position = _require_position(session, position_id)
    if active == position.active:
        return position
    if not active and position.key in ADMIN_ACCESS_POSITIONS:
        raise ValueError(
            "This position gives admin access, so it can't be deactivated here. "
            "Ask the tech team if it really needs to be retired."
        )

    position.active = active
    record_audit(
        session,
        actor_membership_id=actor_membership_id,
        action="position.activate" if active else "position.deactivate",
        resource_type="position",
        resource_id=position.id,
        summary=f"{'Reactivated' if active else 'Deactivated'} position '{position.label}'",
        diff={"active": {"before": not active, "after": active}},
    )
    return position


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------


def list_functions(session: Session, *, include_inactive: bool = False) -> Sequence[Function]:
    """Alphabetical, ignoring case (so "iGV" sorts with the I's, whatever the
    database's collation is)."""
    stmt = select(Function).order_by(func.lower(Function.label))
    if not include_inactive:
        stmt = stmt.where(Function.active.is_(True))
    return session.execute(stmt).scalars().all()


def get_function(session: Session, function_id: int) -> Function | None:
    return session.get(Function, function_id)


def _require_function(session: Session, function_id: int) -> Function:
    function = get_function(session, function_id)
    if function is None:
        raise ValueError(f"Function {function_id} not found")
    return function


def create_function(session: Session, *, label: str, actor_membership_id: int | None) -> Function:
    function = Function(
        key=_ensure_unique_key(session, Function, _derive_key(label)),
        label=label,
        active=True,
    )
    session.add(function)
    session.flush()  # a duplicate name fails here, and we get an id
    record_audit(
        session,
        actor_membership_id=actor_membership_id,
        action="function.create",
        resource_type="function",
        resource_id=function.id,
        summary=f"Created function '{label}'",
    )
    return function


def rename_function(
    session: Session, *, function_id: int, new_label: str, actor_membership_id: int | None
) -> Function:
    function = _require_function(session, function_id)
    if new_label == function.label:
        return function

    old_label = function.label
    function.label = new_label
    session.flush()  # a duplicate name fails here, not at commit
    record_audit(
        session,
        actor_membership_id=actor_membership_id,
        action="function.rename",
        resource_type="function",
        resource_id=function.id,
        summary=f"Renamed function '{old_label}' to '{new_label}'",
        diff={"label": {"before": old_label, "after": new_label}},
    )
    return function


def set_function_active(
    session: Session, *, function_id: int, active: bool, actor_membership_id: int | None
) -> Function:
    """Deactivate or reactivate. Existing memberships and teams keep the function."""
    function = _require_function(session, function_id)
    if active == function.active:
        return function

    function.active = active
    record_audit(
        session,
        actor_membership_id=actor_membership_id,
        action="function.activate" if active else "function.deactivate",
        resource_type="function",
        resource_id=function.id,
        summary=f"{'Reactivated' if active else 'Deactivated'} function '{function.label}'",
        diff={"active": {"before": not active, "after": active}},
    )
    return function
