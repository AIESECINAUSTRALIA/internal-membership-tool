"""Unit tests for permission resolution and hierarchy rules (Spec §3.1, §3.4, §3.6)."""

import pytest

from app.core.permissions import (
    POSITION_RANKS,
    MembershipContext,
    can_add_member,
    can_extend_term,
    can_manage_lc,
    can_move_to_team,
    can_view_membership,
    position_level,
    resolve_widest_scope,
)


@pytest.fixture
def member_context() -> MembershipContext:
    # Rank 1: Member
    return MembershipContext(
        membership_id=1,
        person_id=10,
        lc_id=100,
        position_key="member",
        position_rank=1,
        function_id=5,
        team_id=20,
    )


@pytest.fixture
def tl_context() -> MembershipContext:
    # Rank 2: Team Leader
    return MembershipContext(
        membership_id=2,
        person_id=20,
        lc_id=100,
        position_key="team_leader",
        position_rank=2,
        function_id=5,
        team_id=20,
    )


@pytest.fixture
def lcvp_context() -> MembershipContext:
    # Rank 3: LCVP
    return MembershipContext(
        membership_id=3,
        person_id=30,
        lc_id=100,
        position_key="lcvp",
        position_rank=3,
        function_id=5,
    )


@pytest.fixture
def lcp_context() -> MembershipContext:
    # Rank 4: LCP (president exception: can_add_same_rank=True)
    return MembershipContext(
        membership_id=4,
        person_id=40,
        lc_id=100,
        position_key="lcp",
        position_rank=4,
        can_add_same_rank=True,
    )


@pytest.fixture
def mcvp_context() -> MembershipContext:
    # Rank 6: MCVP
    return MembershipContext(
        membership_id=5,
        person_id=50,
        lc_id=999,
        lc_type="MC",
        position_key="mcvp",
        position_rank=6,
    )


# ---------------------------------------------------------------------------
# Scope resolution tests
# ---------------------------------------------------------------------------


def test_resolve_widest_scope_for_tl(tl_context: MembershipContext) -> None:
    # A Team Leader sees their whole LC, but only adds and extends within their team.
    assert resolve_widest_scope([tl_context], "membership", "view") == "lc"
    assert resolve_widest_scope([tl_context], "membership", "create") == "team"
    assert resolve_widest_scope([tl_context], "membership", "edit") == "team"


def test_resolve_widest_scope_for_lcvp(lcvp_context: MembershipContext) -> None:
    # LCVP has 'lc' scope for membership:create and 'function' scope for membership:edit
    assert resolve_widest_scope([lcvp_context], "membership", "create") == "lc"
    assert resolve_widest_scope([lcvp_context], "membership", "edit") == "function"


def test_resolve_widest_scope_multi_membership(
    tl_context: MembershipContext, lcvp_context: MembershipContext
) -> None:
    # Wider scope wins: lcvp gives 'lc', tl gives 'team' -> widest is 'lc'
    widest = resolve_widest_scope([tl_context, lcvp_context], "membership", "create")
    assert widest == "lc"


# ---------------------------------------------------------------------------
# Extend term tests (§3.4)
# ---------------------------------------------------------------------------


def test_extend_term_allowed_for_higher_rank(
    lcvp_context: MembershipContext, member_context: MembershipContext
) -> None:
    # LCVP (rank 3, function scope) outranks Member (rank 1, same function) -> Allowed
    assert can_extend_term([lcvp_context], member_context) is True


def test_extend_term_denied_for_equal_rank(
    tl_context: MembershipContext,
) -> None:
    # Team Leader trying to extend another Team Leader (equal rank) -> Denied
    target_tl = MembershipContext(
        membership_id=99,
        person_id=999,
        lc_id=100,
        position_key="team_leader",
        position_rank=2,
        function_id=5,
        team_id=20,
    )
    assert can_extend_term([tl_context], target_tl) is False


def test_extend_term_denied_for_self(lcvp_context: MembershipContext) -> None:
    # Nobody can extend their own term (Spec §3.4)
    assert can_extend_term([lcvp_context], lcvp_context) is False


# ---------------------------------------------------------------------------
# Move to team tests (§2A.5, §3.4)
# ---------------------------------------------------------------------------


def test_move_to_team_allowed_for_lcvp(
    lcvp_context: MembershipContext, member_context: MembershipContext
) -> None:
    # LCVP has team_member:edit at function scope -> Allowed
    assert can_move_to_team([lcvp_context], member_context) is True


def test_move_to_team_denied_for_team_leader(
    tl_context: MembershipContext, member_context: MembershipContext
) -> None:
    # Team Leaders do NOT have team_member:edit grant (Spec §2A.5: TL cannot move teams)
    assert can_move_to_team([tl_context], member_context) is False


# ---------------------------------------------------------------------------
# Add member & President Exception tests (§3.4, §3.6)
# ---------------------------------------------------------------------------


def test_add_member_allowed_for_lower_rank(lcvp_context: MembershipContext) -> None:
    # LCVP (rank 3) adding Member (rank 1) in own LC -> Allowed
    allowed, msg = can_add_member(
        actor_memberships=[lcvp_context],
        target_lc_id=100,
        target_lc_type="LC",
        target_position_key="member",
        target_position_rank=1,
        target_position_level="lc",
        target_function_id=5,
    )
    assert allowed is True
    assert msg is None


def test_add_member_denied_for_higher_rank(lcvp_context: MembershipContext) -> None:
    # LCVP (rank 3) trying to add LCP (rank 4) -> Denied
    allowed, msg = can_add_member(
        actor_memberships=[lcvp_context],
        target_lc_id=100,
        target_lc_type="LC",
        target_position_key="lcp",
        target_position_rank=4,
        target_position_level="lc",
    )
    assert allowed is False
    assert msg is not None
    assert "higher rank" in msg.lower()


def test_president_exception_allowed_for_lcp(lcp_context: MembershipContext) -> None:
    # President Exception: LCP (rank 4) adding another LCP (rank 4) in own LC -> Allowed
    allowed, msg = can_add_member(
        actor_memberships=[lcp_context],
        target_lc_id=100,
        target_lc_type="LC",
        target_position_key="lcp",
        target_position_rank=4,
        target_position_level="lc",
    )
    assert allowed is True
    assert msg is None


def test_president_exception_denied_for_different_lc(lcp_context: MembershipContext) -> None:
    # LCP can only add in their OWN LC (Spec §3.4)
    allowed, msg = can_add_member(
        actor_memberships=[lcp_context],
        target_lc_id=200,  # Different LC
        target_lc_type="LC",
        target_position_key="lcp",
        target_position_rank=4,
        target_position_level="lc",
    )
    assert allowed is False


def test_level_mismatch_denied(lcp_context: MembershipContext) -> None:
    # Spec §3.6: Level must match entity type. Adding MC position into an LC is rejected.
    allowed, msg = can_add_member(
        actor_memberships=[lcp_context],
        target_lc_id=100,
        target_lc_type="LC",
        target_position_key="mcvp",
        target_position_rank=6,
        target_position_level="mc",
    )
    assert allowed is False
    assert msg is not None
    assert "level" in msg.lower()


def test_position_level_mc_keys() -> None:
    assert position_level("mcvp") == "mc"
    assert position_level("lcvp") == "lc"


def test_can_view_membership_lc_scope(
    lcvp_context: MembershipContext, member_context: MembershipContext
) -> None:
    other_lc = MembershipContext(
        membership_id=9,
        person_id=90,
        lc_id=101,
        position_key="member",
        position_rank=1,
        function_id=5,
    )
    assert can_view_membership([lcvp_context], member_context) is True
    assert can_view_membership([lcvp_context], other_lc) is False
    # A plain member has no membership:view grant at all
    assert can_view_membership([member_context], lcvp_context) is False
    assert can_view_membership([], member_context) is False


def test_team_leader_can_view_whole_own_lc_but_not_others(
    tl_context: MembershipContext, member_context: MembershipContext
) -> None:
    other_team_same_lc = MembershipContext(
        membership_id=11,
        person_id=110,
        lc_id=tl_context.lc_id,
        position_key="member",
        position_rank=1,
        function_id=99,
        team_id=777,
    )
    other_lc = MembershipContext(
        membership_id=12,
        person_id=120,
        lc_id=tl_context.lc_id + 1,
        position_key="member",
        position_rank=1,
        function_id=5,
        team_id=20,
    )
    assert can_view_membership([tl_context], other_team_same_lc) is True
    assert can_view_membership([tl_context], other_lc) is False
    # Viewing wider does not widen writes: extending still needs team scope.
    assert can_extend_term([tl_context], other_team_same_lc) is False


# ---------------------------------------------------------------------------
# LC management (spec §1.5): `manage` on `lc`, MC and admin positions only
# ---------------------------------------------------------------------------


def _context_for(position_key: str) -> MembershipContext:
    return MembershipContext(
        membership_id=1,
        person_id=1,
        lc_id=1,
        position_key=position_key,
        position_rank=POSITION_RANKS.get(position_key, 1),
    )


@pytest.mark.parametrize("position_key", ["mcd", "mcvp", "mcp", "admin"])
def test_mc_and_admin_positions_can_manage_lcs(position_key: str) -> None:
    assert can_manage_lc([_context_for(position_key)]) is True


@pytest.mark.parametrize("position_key", ["member", "team_leader", "lcvp", "lcp"])
def test_lc_level_positions_cannot_manage_lcs(position_key: str) -> None:
    assert can_manage_lc([_context_for(position_key)]) is False


def test_actor_without_memberships_cannot_manage_lcs() -> None:
    assert can_manage_lc([]) is False
