"""Permission resolution and hierarchy rules (Spec §3.1, §3.2, §3.4, §3.6).

Access control in AIESEC Australia uses two checks that must BOTH pass:
1. Matrix grant & Scope check: Does the actor have a grant whose scope
   (own < team < function < lc < all) covers the target?
2. Hierarchy check (Spec §3.4): Does the target's position rank strictly below
   the actor's? (With the President exception allowing LCP/MCP to add another
   holder of the same position).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

# Scopes ordered narrowest to widest (Spec §3.1)
Scope = Literal["own", "team", "function", "lc", "all"]
SCOPE_ORDER: list[Scope] = ["own", "team", "function", "lc", "all"]

Action = Literal["view", "create", "edit", "delete", "export", "manage"]

# Known rank configuration per Spec §2 (fallback if position.rank is not populated)
POSITION_RANKS: dict[str, int] = {
    "member": 1,
    "team_leader": 2,
    "lcvp": 3,
    "lcp": 4,
    "mcd": 5,
    "mcvp": 6,
    "mcp": 7,
}

PRESIDENTIAL_POSITIONS: set[str] = {"lcp", "mcp"}
TEAM_HOLDING_POSITIONS: set[str] = {"member", "team_leader"}


def scope_rank(scope: Scope) -> int:
    """Return numeric weight of scope to compare reach."""
    return SCOPE_ORDER.index(scope)


@dataclass(frozen=True)
class MatrixGrant:
    position_key: str
    resource: str
    action: Action
    scope: Scope


# Baseline Permission Matrix matching Spec §3.1 and frontend/src/api/mock/seed.ts
BASELINE_PERMISSION_MATRIX: list[MatrixGrant] = [
    # Member: own record and tracking only. No membership summary management.
    MatrixGrant("member", "member_record", "view", "own"),
    MatrixGrant("member", "member_record", "edit", "own"),
    MatrixGrant("member", "kpi_record", "view", "own"),
    MatrixGrant("member", "kpi_record", "create", "own"),
    # Team Leader: team scope. Can view, add and extend within their team; no move.
    MatrixGrant("team_leader", "member_record", "view", "own"),
    MatrixGrant("team_leader", "member_record", "edit", "own"),
    MatrixGrant("team_leader", "membership", "view", "team"),
    MatrixGrant("team_leader", "membership", "create", "team"),
    MatrixGrant("team_leader", "membership", "edit", "team"),
    MatrixGrant("team_leader", "kpi_record", "view", "team"),
    MatrixGrant("team_leader", "kpi_record", "create", "team"),
    MatrixGrant("team_leader", "kpi_record", "edit", "team"),
    MatrixGrant("team_leader", "analytics_report", "view", "function"),
    # LCVP: read whole LC, add to any function in LC, edit within own function only.
    MatrixGrant("lcvp", "member_record", "view", "own"),
    MatrixGrant("lcvp", "member_record", "edit", "own"),
    MatrixGrant("lcvp", "membership", "view", "lc"),
    MatrixGrant("lcvp", "membership", "create", "lc"),
    MatrixGrant("lcvp", "membership", "edit", "function"),
    MatrixGrant("lcvp", "team_member", "edit", "function"),
    MatrixGrant("lcvp", "kpi_record", "view", "lc"),
    MatrixGrant("lcvp", "kpi_record", "create", "function"),
    MatrixGrant("lcvp", "kpi_record", "edit", "function"),
    MatrixGrant("lcvp", "analytics_report", "view", "function"),
    # LCP: full LC scope.
    MatrixGrant("lcp", "member_record", "view", "own"),
    MatrixGrant("lcp", "member_record", "edit", "own"),
    MatrixGrant("lcp", "membership", "view", "lc"),
    MatrixGrant("lcp", "membership", "create", "lc"),
    MatrixGrant("lcp", "membership", "edit", "lc"),
    MatrixGrant("lcp", "team_member", "edit", "lc"),
    MatrixGrant("lcp", "kpi_record", "view", "lc"),
    MatrixGrant("lcp", "kpi_record", "create", "lc"),
    MatrixGrant("lcp", "kpi_record", "edit", "lc"),
    MatrixGrant("lcp", "analytics_report", "view", "lc"),
    MatrixGrant("lcp", "analytics_report", "export", "lc"),
]

# MC positions (mcd, mcvp, mcp) have national 'all' scope
for _mc_pos in ["mcd", "mcvp", "mcp"]:
    BASELINE_PERMISSION_MATRIX.extend(
        [
            MatrixGrant(_mc_pos, "member_record", "view", "all"),
            MatrixGrant(_mc_pos, "member_record", "edit", "own"),
            MatrixGrant(_mc_pos, "membership", "view", "all"),
            MatrixGrant(_mc_pos, "membership", "create", "all"),
            MatrixGrant(_mc_pos, "membership", "edit", "all"),
            MatrixGrant(_mc_pos, "team_member", "edit", "all"),
            MatrixGrant(_mc_pos, "kpi_record", "view", "all"),
            MatrixGrant(_mc_pos, "kpi_record", "create", "all"),
            MatrixGrant(_mc_pos, "kpi_record", "edit", "all"),
            MatrixGrant(_mc_pos, "analytics_report", "view", "all"),
            MatrixGrant(_mc_pos, "analytics_report", "export", "all"),
            MatrixGrant(_mc_pos, "function", "manage", "all"),
        ]
    )


@dataclass(frozen=True)
class MembershipContext:
    """Context representing a single active membership of an actor or target."""

    membership_id: int
    person_id: int
    lc_id: int
    position_key: str
    position_rank: int
    can_add_same_rank: bool = False
    function_id: int | None = None
    function_key: str | None = None
    team_id: int | None = None
    lc_type: str = "LC"  # "LC" or "MC"


def resolve_widest_scope(
    actor_memberships: Sequence[MembershipContext],
    resource: str,
    action: Action,
) -> Scope | None:
    """Spec §3.2: Widest scope granted across all active memberships of the actor."""
    widest: Scope | None = None
    for m in actor_memberships:
        for grant in BASELINE_PERMISSION_MATRIX:
            if (
                grant.position_key == m.position_key
                and grant.resource == resource
                and grant.action == action
            ):
                if widest is None or scope_rank(grant.scope) > scope_rank(widest):
                    widest = grant.scope
    return widest


def get_acting_membership(
    memberships: Sequence[MembershipContext],
) -> MembershipContext | None:
    """The actor's highest-ranking active membership."""
    if not memberships:
        return None
    return max(memberships, key=lambda m: m.position_rank)


def scope_covers(
    scope: Scope,
    actor_memberships: Sequence[MembershipContext],
    target_person_id: int,
    target_lc_id: int,
    target_function_id: int | None = None,
    target_team_id: int | None = None,
) -> bool:
    """Check 1 of 2: does the grant's scope reach this target? (Spec §3.4)"""
    if scope == "all":
        return True

    for actor in actor_memberships:
        if scope == "own" and target_person_id == actor.person_id:
            return True
        if scope == "lc" and target_lc_id == actor.lc_id:
            return True
        if (
            scope == "function"
            and target_lc_id == actor.lc_id
            and target_function_id is not None
            and target_function_id == actor.function_id
        ):
            return True
        if (
            scope == "team"
            and target_team_id is not None
            and actor.team_id is not None
            and target_team_id == actor.team_id
        ):
            return True

    return False


def can_act_on_target(
    actor_memberships: Sequence[MembershipContext],
    target: MembershipContext,
    resource: str,
    action: Action,
) -> bool:
    """The shared two-check rule (§3.4) for existing memberships (Move, Extend, Track).

    1. Matrix must grant action at a scope covering target.
    2. Target position must rank strictly below actor.
    3. Self-action guard: nobody can act on themselves here.
    """
    if not actor_memberships:
        return False

    acting = get_acting_membership(actor_memberships)
    if acting is None:
        return False

    # Nobody can act on themselves through these management actions (Spec §3.4)
    if target.person_id == acting.person_id:
        return False

    scope = resolve_widest_scope(actor_memberships, resource, action)
    if scope is None:
        return False

    # Check 1: Scope
    if not scope_covers(
        scope=scope,
        actor_memberships=actor_memberships,
        target_person_id=target.person_id,
        target_lc_id=target.lc_id,
        target_function_id=target.function_id,
        target_team_id=target.team_id,
    ):
        return False

    # Check 2: Rank hierarchy (strictly below)
    return target.position_rank < acting.position_rank


def can_extend_term(
    actor_memberships: Sequence[MembershipContext],
    target: MembershipContext,
) -> bool:
    """Extend term: edits membership end_date. Needs membership:edit and lower rank."""
    return can_act_on_target(actor_memberships, target, resource="membership", action="edit")


def can_move_to_team(
    actor_memberships: Sequence[MembershipContext],
    target: MembershipContext,
) -> bool:
    """Move to team: edits team_member.

    Granted to LCVP and above only. Team Leaders lack team_member:edit so return False.
    """
    return can_act_on_target(actor_memberships, target, resource="team_member", action="edit")


def can_add_member(
    actor_memberships: Sequence[MembershipContext],
    target_lc_id: int,
    target_lc_type: str,
    target_position_key: str,
    target_position_rank: int,
    target_position_level: str,
    target_function_id: int | None = None,
    target_team_id: int | None = None,
) -> tuple[bool, str | None]:
    """Validate whether an actor can add a member with the chosen parameters.

    Returns (is_allowed, rejection_reason).
    """
    acting = get_acting_membership(actor_memberships)
    if acting is None:
        return False, "No active membership found."

    scope = resolve_widest_scope(actor_memberships, "membership", "create")
    if scope is None:
        return False, "You do not have permission to add members."

    # Spec §3.6: Level must match entity type ('lc' with 'LC', 'mc' with 'MC')
    if target_position_level.lower() != target_lc_type.lower():
        return False, "Position level does not match LC type."

    # Check 1: Scope covers target entity/function/team
    if not scope_covers(
        scope=scope,
        actor_memberships=actor_memberships,
        target_person_id=-1,  # Not checking person id for new add
        target_lc_id=target_lc_id,
        target_function_id=target_function_id,
        target_team_id=target_team_id,
    ):
        return False, "You cannot add people outside your scope."

    # Check 2: Rank hierarchy + President Exception (§3.4)
    if target_position_rank < acting.position_rank:
        return True, None

    # President Exception: LCP / MCP can add another holder of the same position
    if (
        acting.can_add_same_rank
        and target_position_key == acting.position_key
        and target_lc_id == acting.lc_id
    ):
        return True, None

    return False, "You cannot add someone of equal or higher rank."
