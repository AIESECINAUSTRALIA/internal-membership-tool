"""Queries and mutations for the `position` and `function` tables (spec §1.5, §2A.2).

Positions and functions are plain lookup tables, not hardcoded enums, so an admin
can add, rename, or deactivate them at runtime without a code change (spec §1.5).
They are never hard-deleted: deactivating is the soft delete. The database's FK
constraints enforce this — a row referenced by a membership row cannot be deleted.

Every mutating function calls `record_audit` in the same session.
"""

import re
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.models.org import Function, Position

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")

VALID_LEVELS = {"lc", "mc"}


def _derive_key(label: str) -> str:
    """Turn a display label into a machine-readable key (lowercase, underscores)."""
    key = label.lower().strip()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = key.strip("_")
    return key[:50] or "item"


def _ensure_unique_key(session: Session, model: type, base_key: str) -> str:
    """Return `base_key` if unused, otherwise append _2, _3, ... until it is."""
    key = base_key
    suffix = 2
    existing = set(session.execute(select(model.key)).scalars())  # type: ignore[attr-defined]
    while key in existing:
        key = f"{base_key}_{suffix}"
        suffix += 1
    return key


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


def list_positions(session: Session, *, include_inactive: bool = False) -> Sequence[Position]:
    stmt = select(Position)
    if not include_inactive:
        stmt = stmt.where(Position.active.is_(True))
    return session.execute(stmt).scalars().all()


def get_position(session: Session, position_id: int) -> Position | None:
    return session.get(Position, position_id)


def create_position(
    session: Session,
    *,
    label: str,
    level: str | None,
    rank: int | None,
    can_add_same_rank: bool,
    actor_membership_id: int | None,
) -> Position:
    if level is not None and level not in VALID_LEVELS:
        raise ValueError(f"level must be 'lc' or 'mc', got '{level}'")
    key = _ensure_unique_key(session, Position, _derive_key(label))
    pos = Position(
        key=key,
        label=label.strip(),
        level=level,
        rank=rank,
        can_add_same_rank=can_add_same_rank,
        active=True,
    )
    session.add(pos)
    session.flush()
    record_audit(
        session,
        actor_membership_id=actor_membership_id,
        action="position.create",
        resource_type="position",
        resource_id=pos.id,
        summary=f"Created position '{label}'",
    )
    return pos


def update_position(
    session: Session,
    *,
    position_id: int,
    label: str | None = None,
    level: str | None = None,
    rank: int | None = None,
    can_add_same_rank: bool | None = None,
    active: bool | None = None,
    actor_membership_id: int | None,
) -> Position:
    pos = get_position(session, position_id)
    if pos is None:
        raise ValueError(f"Position {position_id} not found")
    if level is not None and level not in VALID_LEVELS:
        raise ValueError(f"level must be 'lc' or 'mc', got '{level}'")

    diff: dict[str, object] = {}
    if label is not None and label.strip() != pos.label:
        diff["label"] = {"before": pos.label, "after": label.strip()}
        pos.label = label.strip()
    if level is not None and level != pos.level:
        diff["level"] = {"before": pos.level, "after": level}
        pos.level = level
    if rank is not None and rank != pos.rank:
        diff["rank"] = {"before": pos.rank, "after": rank}
        pos.rank = rank
    if can_add_same_rank is not None and can_add_same_rank != pos.can_add_same_rank:
        diff["can_add_same_rank"] = {"before": pos.can_add_same_rank, "after": can_add_same_rank}
        pos.can_add_same_rank = can_add_same_rank
    if active is not None and active != pos.active:
        diff["active"] = {"before": pos.active, "after": active}
        pos.active = active

    if diff:
        record_audit(
            session,
            actor_membership_id=actor_membership_id,
            action="position.update",
            resource_type="position",
            resource_id=pos.id,
            summary=f"Updated position '{pos.label}'",
            diff=diff,
        )
    return pos


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------


def list_functions(session: Session, *, include_inactive: bool = False) -> Sequence[Function]:
    stmt = select(Function)
    if not include_inactive:
        stmt = stmt.where(Function.active.is_(True))
    return session.execute(stmt).scalars().all()


def get_function(session: Session, function_id: int) -> Function | None:
    return session.get(Function, function_id)


def create_function(
    session: Session,
    *,
    label: str,
    actor_membership_id: int | None,
) -> Function:
    key = _ensure_unique_key(session, Function, _derive_key(label))
    func = Function(key=key, label=label.strip(), active=True)
    session.add(func)
    session.flush()
    record_audit(
        session,
        actor_membership_id=actor_membership_id,
        action="function.create",
        resource_type="function",
        resource_id=func.id,
        summary=f"Created function '{label}'",
    )
    return func


def update_function(
    session: Session,
    *,
    function_id: int,
    label: str | None = None,
    active: bool | None = None,
    actor_membership_id: int | None,
) -> Function:
    func = get_function(session, function_id)
    if func is None:
        raise ValueError(f"Function {function_id} not found")

    diff: dict[str, object] = {}
    if label is not None and label.strip() != func.label:
        diff["label"] = {"before": func.label, "after": label.strip()}
        func.label = label.strip()
    if active is not None and active != func.active:
        diff["active"] = {"before": func.active, "after": active}
        func.active = active

    if diff:
        record_audit(
            session,
            actor_membership_id=actor_membership_id,
            action="function.update",
            resource_type="function",
            resource_id=func.id,
            summary=f"Updated function '{func.label}'",
            diff=diff,
        )
    return func
