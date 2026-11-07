"""What the signed-in person may do, for `GET /api/v1/me` (spec §3.2).

Kept in its own module, separate from `core/permissions.py` (the matrix and the
hierarchy checks), so the two can change independently.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.core.permissions import BASELINE_PERMISSION_MATRIX, Action, Scope, scope_rank


@dataclass(frozen=True)
class ResolvedPermission:
    """One (resource, action) the signed-in person holds, at its widest scope."""

    resource: str
    action: Action
    scope: Scope


def resolve_permissions(position_keys: Iterable[str]) -> list[ResolvedPermission]:
    """Spec §3.2: everything a person may do, from all their active memberships.

    A person can hold several memberships at once (e.g. LCVP oGV and Team Leader BD).
    Access is the UNION of what each position grants; where two grant the same
    (resource, action), the WIDER scope wins. This is what `GET /api/v1/me` returns,
    so the frontend shows exactly what the server will allow.

    This is the one place the matrix is read for `/me`: when the matrix moves to a
    database table (spec §3.3), only where the grants come from changes here.
    """
    keys = set(position_keys)
    widest: dict[tuple[str, Action], Scope] = {}
    for grant in BASELINE_PERMISSION_MATRIX:
        if grant.position_key not in keys:
            continue
        key = (grant.resource, grant.action)
        if key not in widest or scope_rank(grant.scope) > scope_rank(widest[key]):
            widest[key] = grant.scope
    return [
        ResolvedPermission(resource=resource, action=action, scope=scope)
        for (resource, action), scope in sorted(widest.items())
    ]
