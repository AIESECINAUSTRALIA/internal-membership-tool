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

MC_POSITIONS: set[str] = {"mcd", "mcvp", "mcp"}
# Admin positions (spec §1.4 "Data / Privacy admin") are position-linked, not
# named people. The position itself is not seeded yet (spec §12 #12), so nobody
# holds this key today; the grants below take effect once it is created.
ADMIN_POSITIONS: set[str] = {"admin"}
PRESIDENTIAL_POSITIONS: set[str] = {"lcp", "mcp"}
TEAM_HOLDING_POSITIONS: set[str] = {"member", "team_leader"}
# Positions whose homepage chart covers their whole function in their LC.
FUNCTION_SCOPE_POSITIONS: set[str] = {"lcvp", "lcp"}


def position_level(position_key: str) -> Literal["lc", "mc"]:
    """Which kind of entity a position belongs to (Spec §3.6).

    Only a fallback now: `position.level` exists (DEV-0049) and
    `repositories.membership._position_level` reads it first, using this only
    while the column is empty. Same pattern as `POSITION_RANKS`.
    """
    return "mc" if position_key in MC_POSITIONS else "lc"


HomeChartScope = Literal["team", "function", "all"]
DataChartScope = Literal["team", "function", "lc", "all"]


def home_chart_scope(position_key: str) -> HomeChartScope:
    """Whose data the homepage chart covers (Spec §2A.4, docs/home-chart.md):
    Member and TL see their team, LCVP and LCP their function in their LC, MC
    positions all LCs. Any other position (e.g. `admin`, or one added later)
    gets `team`. Mirrors `homeChartScope` in the frontend seed.

    Fallback until ticket 2 adds position columns, same pattern as `POSITION_RANKS`.
    """
    if position_key in MC_POSITIONS:
        return "all"
    if position_key in FUNCTION_SCOPE_POSITIONS:
        return "function"
    # Deliberately the narrowest scope: a position this rule doesn't know
    # about should see less data, never more.
    return "team"


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
    # Team Leader: sees the whole LC; adds and extends within their team only; no move.
    MatrixGrant("team_leader", "member_record", "view", "own"),
    MatrixGrant("team_leader", "member_record", "edit", "own"),
    MatrixGrant("team_leader", "membership", "view", "lc"),
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


# LC and attribute-catalog management (spec §1.5, §2A.2) are org-wide configuration,
# so MC and admin positions hold them at the widest scope.
for _position_key in sorted(MC_POSITIONS | ADMIN_POSITIONS):
    BASELINE_PERMISSION_MATRIX.append(MatrixGrant(_position_key, "lc", "manage", "all"))
    BASELINE_PERMISSION_MATRIX.append(MatrixGrant(_position_key, "attribute", "manage", "all"))

# People and memberships on the Admin console (spec §1.5, §2A.2). Same holders as `lc`
# above, so the capability comes from a position held by several people, never one
# named person (spec §2). `membership:manage` is separate from `membership:create` /
# `edit`: those are the Membership summary page's scoped grants (§2A.5), this is the
# admin screen's org-wide one. The hierarchy rule still applies to it
# (`can_admin_manage_membership`).
for _position_key in sorted(MC_POSITIONS | ADMIN_POSITIONS):
    BASELINE_PERMISSION_MATRIX.append(MatrixGrant(_position_key, "person", "manage", "all"))
    BASELINE_PERMISSION_MATRIX.append(MatrixGrant(_position_key, "membership", "manage", "all"))
# Position management (spec §1.5, §2A.2): Admin console only.
# MC positions can ALSO manage functions via Settings (spec §2A.8), and are
# already granted `function:manage` above. `position:manage` is added here too
# so the Admin console's unified Positions & functions screen is accessible to
# MC positions (consistent with lc:manage and person:manage above).
for _position_key in sorted(MC_POSITIONS | ADMIN_POSITIONS):
    BASELINE_PERMISSION_MATRIX.append(MatrixGrant(_position_key, "position", "manage", "all"))


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


def can_manage_position(actor_memberships: Sequence[MembershipContext]) -> bool:
    """Add, rename, deactivate, or edit rank/level/can_add_same_rank on positions (§1.5, §2A.2)."""
    return resolve_widest_scope(actor_memberships, "position", "manage") == "all"


def can_edit_position(
    actor_memberships: Sequence[MembershipContext],
    *,
    current_rank: int | None,
    new_rank: int | None,
) -> bool:
    """The hierarchy rule for editing positions (spec §3.4, DEV-0049).

    Holding `manage` on `position` is not enough on its own: you may only change a
    position that ranks BELOW your own highest position, and only give it a rank
    below yours. Without this, an MCD (rank 5) could set the MCP's rank to 1 and end
    up out-ranking the president.

    - `current_rank`: the position's rank today. `None` when creating a position, or
      for an old position with no rank yet (anyone with `manage` may fix those).
    - `new_rank`: the rank being set. `None` when the rank isn't changing.
    """
    if not actor_memberships:
        return False
    top_rank = max(context.position_rank for context in actor_memberships)

    if current_rank is not None and current_rank >= top_rank:
        return False
    if new_rank is not None and new_rank >= top_rank:
        return False
    return True


def can_manage_function(actor_memberships: Sequence[MembershipContext]) -> bool:
    """Add, rename, or deactivate functions (spec §1.5, §2A.2, §2A.8)."""
    return resolve_widest_scope(actor_memberships, "function", "manage") == "all"


def can_manage_lc(actor_memberships: Sequence[MembershipContext]) -> bool:
    """Add, rename, set state, deactivate or merge LCs (spec §1.5).

    Needs `manage` on `lc` at scope `all`. There is no target person, so the
    hierarchy and self-action checks from `can_act_on_target` do not apply.
    """
    return resolve_widest_scope(actor_memberships, "lc", "manage") == "all"


def can_manage_attribute(actor_memberships: Sequence[MembershipContext]) -> bool:
    """Add, edit or retire KPIs and custom fields (spec §1.5, §4.2).

    Needs `manage` on `attribute` at scope `all`. Like `can_manage_lc`, there is
    no target person, so the hierarchy and self-action checks do not apply.
    """
    return resolve_widest_scope(actor_memberships, "attribute", "manage") == "all"


def can_manage_person(actor_memberships: Sequence[MembershipContext]) -> bool:
    """Add, edit, deactivate or reactivate people on the Admin console (spec §1.5).

    Needs `manage` on `person` at scope `all`. This function checks only the matrix
    grant. The §3.4 hierarchy rule is applied per target person by
    `_check_outranks_person` in `repositories/admin_people.py` (edit, deactivate,
    reactivate and unlink EXPA).
    """
    return resolve_widest_scope(actor_memberships, "person", "manage") == "all"


def can_admin_manage_membership(
    actor_memberships: Sequence[MembershipContext],
    *,
    target_person_id: int,
    target_position_key: str,
    target_position_rank: int,
    target_lc_id: int,
    adding: bool,
) -> tuple[bool, str | None]:
    """Assign, correct or end a membership on the Admin console (spec §2A.2).

    Returns (is_allowed, rejection_reason). Both checks from §3.4 must pass:

    1. The matrix grants `manage` on `membership` at scope `all`. An admin is not
       limited to one LC or team the way the Membership summary page is (DEV-47).
    2. The hierarchy rule still holds: nobody changes their own memberships, and the
       position involved must rank below the actor's. The president exception (an
       LCP or MCP adding another holder of their own position, in their own entity)
       applies to adding only, as in `can_add_member`.

    The level-match rule (§3.6) is about the LC, not the actor, so the repository
    checks it separately for every write.
    """
    if resolve_widest_scope(actor_memberships, "membership", "manage") != "all":
        return False, "You do not have permission to manage memberships."

    acting = get_acting_membership(actor_memberships)
    if acting is None:
        return False, "No active membership found."

    if target_person_id == acting.person_id:
        return False, "You can't change your own memberships."

    if target_position_rank < acting.position_rank:
        return True, None

    if (
        adding
        and acting.can_add_same_rank
        and target_position_key == acting.position_key
        and target_lc_id == acting.lc_id
    ):
        return True, None

    return False, "You can't assign or change a position at or above your own."


def can_view_membership(
    actor_memberships: Sequence[MembershipContext],
    target: MembershipContext,
) -> bool:
    """Read access to one membership: matrix grant whose scope reaches the target.

    No rank check: viewing is not a write, so the §3.4 hierarchy rule does not apply.
    """
    scope = resolve_widest_scope(actor_memberships, "membership", "view")
    if scope is None:
        return False
    return scope_covers(
        scope=scope,
        actor_memberships=actor_memberships,
        target_person_id=target.person_id,
        target_lc_id=target.lc_id,
        target_function_id=target.function_id,
        target_team_id=target.team_id,
    )


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
