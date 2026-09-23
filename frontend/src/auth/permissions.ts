/**
 * Permission gating and the hierarchy rule, as pure functions.
 *
 * READ THIS FIRST (for a reader with no context)
 * Spec §3: what a person may do is decided by TWO checks that must BOTH pass:
 *   1. The permission matrix grants the action, and the grant's SCOPE covers the target
 *      (own / team / function / lc / all).
 *   2. The hierarchy rule (§3.4): the target's position must rank BELOW the actor's.
 *      A higher `rank` number is a higher position. The one exception is the president
 *      exception: LCP/MCP may ADD another holder of the same position.
 *
 * The server enforces all of this on every request. Nothing here grants access. These
 * functions only decide what the UI SHOWS, so people are not offered buttons the server
 * would reject. If the server and these functions ever disagree, the server wins.
 *
 * Simplification worth knowing: the spec takes rank from "the actor's membership that
 * supplies the grant" (§3.4). The resolved permission payload does not say which
 * membership supplied a grant, so the UI uses the actor's HIGHEST-ranked active
 * membership. That can only over-show a button in an unusual multi-membership case;
 * the server still refuses it.
 */
import type {
  Action,
  FunctionDef,
  FunctionRef,
  IsoDate,
  Lc,
  Me,
  MemberSummaryRow,
  MembershipView,
  Permission,
  Position,
  Scope,
  Team,
} from '../api/types'

/** Narrowest to widest. A wider scope covers everything a narrower one does. */
export const SCOPE_ORDER: readonly Scope[] = ['own', 'team', 'function', 'lc', 'all']

const scopeRank = (scope: Scope): number => SCOPE_ORDER.indexOf(scope)

// ---------------------------------------------------------------------------
// Resolving grants (§3.2)
// ---------------------------------------------------------------------------

/** The widest scope granted for (resource, action), or null. Deny by default. */
export function widestScope(
  permissions: readonly Permission[],
  resource: string,
  action: Action,
): Scope | null {
  let best: Scope | null = null
  for (const p of permissions) {
    if (p.resource === resource && p.action === action) {
      if (best === null || scopeRank(p.scope) > scopeRank(best)) best = p.scope
    }
  }
  return best
}

export function can(permissions: readonly Permission[], resource: string, action: Action): boolean {
  return widestScope(permissions, resource, action) !== null
}

/**
 * Whether the widest granted scope for (resource, action) is AT LEAST as wide as
 * `minScope` (§3.2). `can()` only checks "is there any grant"; this checks "is the grant
 * wide enough to be useful" — e.g. the Data page's group rollups (§2A.7) need at least
 * 'team', since an 'own'-only grant has nothing to roll up.
 */
export function hasMinScope(
  permissions: readonly Permission[],
  resource: string,
  action: Action,
  minScope: Scope,
): boolean {
  const scope = widestScope(permissions, resource, action)
  return scope !== null && scopeRank(scope) >= scopeRank(minScope)
}

// ---------------------------------------------------------------------------
// Who is acting
// ---------------------------------------------------------------------------

/** Access follows the dates (§4.1, §5.3): start <= today and (no end or end >= today). */
export function isActive(
  membership: Pick<MembershipView, 'startDate' | 'endDate'>,
  today: IsoDate,
): boolean {
  return membership.startDate <= today && (membership.endDate === null || membership.endDate >= today)
}

/** A person with no active membership sees the not-allocated page (§9). */
export function hasActiveMembership(me: Me, today: IsoDate): boolean {
  return me.memberships.some((m) => isActive(m, today))
}

export interface Actor {
  personId: string
  /** ACTIVE memberships only. */
  memberships: MembershipView[]
}

export function actorFromMe(me: Me, today: IsoDate): Actor {
  return { personId: me.person.id, memberships: me.memberships.filter((m) => isActive(m, today)) }
}

/** The actor's highest-ranked active membership (see the simplification note above). */
export function actingMembership(actor: Actor): MembershipView | null {
  let best: MembershipView | null = null
  for (const m of actor.memberships) {
    if (best === null || m.position.rank > best.position.rank) best = m
  }
  return best
}

export function actingPosition(actor: Actor): Position | null {
  return actingMembership(actor)?.position ?? null
}

// ---------------------------------------------------------------------------
// Acting on an EXISTING membership: Extend term, Move to team (§2A.5, §3.4)
// ---------------------------------------------------------------------------

/** The membership being acted on. */
export interface TargetRole {
  personId: string
  position: Position
  lcId: string
  functionKey: string | null
  teamId: string | null
}

/** Check 1 of 2: does the grant's scope reach this target? */
export function scopeCovers(scope: Scope, actor: Actor, target: TargetRole): boolean {
  switch (scope) {
    case 'own':
      return target.personId === actor.personId
    case 'team':
      return (
        target.teamId !== null && actor.memberships.some((m) => m.team?.id === target.teamId)
      )
    case 'function':
      return (
        target.functionKey !== null &&
        actor.memberships.some(
          (m) => m.lc.id === target.lcId && m.function?.key === target.functionKey,
        )
      )
    case 'lc':
      return actor.memberships.some((m) => m.lc.id === target.lcId)
    case 'all':
      return true
  }
}

/** Check 2 of 2: the target's position must rank strictly below the actor's. */
export function outranks(actor: Actor, target: Position): boolean {
  const acting = actingPosition(actor)
  return acting !== null && target.rank < acting.rank
}

/**
 * The shared two-check rule (§3.4) behind Extend term, Move to team and Track someone:
 * the matrix must grant `edit` on the resource at a scope that reaches the target, AND
 * the target's position must rank below the actor's. Nobody can act on themselves this
 * way, which is also why nobody can extend their own term or track themself here (§2A.5,
 * §2A.6) — a person's OWN tracking is a separate, always-allowed path (§3.4).
 */
function canActOnTarget(
  actor: Actor,
  permissions: readonly Permission[],
  resource: 'membership' | 'team_member' | 'kpi_record',
  target: TargetRole,
): boolean {
  const scope = widestScope(permissions, resource, 'edit')
  if (scope === null) return false
  // Load-bearing, not redundant with outranks(): outranks() compares against the
  // actor's BEST active membership, not the specific target, so without this a
  // multi-membership actor (e.g. Team Leader in one function, Member in another)
  // could "outrank" their own lower-ranked membership and act on themselves.
  if (target.personId === actor.personId) return false
  return scopeCovers(scope, actor, target) && outranks(actor, target.position)
}

/** Extend term edits the membership's end date (§2A.5). Needs `membership.edit`. */
export function canExtendTerm(
  actor: Actor,
  permissions: readonly Permission[],
  target: TargetRole,
): boolean {
  return canActOnTarget(actor, permissions, 'membership', target)
}

/**
 * Move to team (§2A.5). Needs `team_member.edit`, which the matrix grants to LCVP and
 * above only. Team Leaders do not hold it, so they never see this action.
 */
export function canMoveToTeam(
  actor: Actor,
  permissions: readonly Permission[],
  target: TargetRole,
): boolean {
  return canActOnTarget(actor, permissions, 'team_member', target)
}

export function targetRoleOf(row: MemberSummaryRow, role: MemberSummaryRow['roles'][number]): TargetRole {
  return {
    personId: row.personId,
    position: role.position,
    lcId: row.lc.id,
    functionKey: role.function?.key ?? null,
    teamId: role.teamId,
  }
}

export interface RowActions {
  /** Memberships of this person the actor may extend. */
  extendRoleIds: string[]
  /** Memberships of this person the actor may move between teams. */
  moveRoleIds: string[]
}

/**
 * Whether the "Manage membership" hub should show at all: does the actor hold
 * `membership.edit` or `team_member.edit` at wider than `own` scope, for ANYONE.
 * Whether a SPECIFIC person may be managed is the separate, per-target `rowActions`
 * check below (same "does X exist at all" vs. "for this one target" split as
 * `canTrackOthers`/`trackableRoleIds` on the Tracking page).
 */
export function canManageMemberships(permissions: readonly Permission[]): boolean {
  const editScope = widestScope(permissions, 'membership', 'edit')
  const teamScope = widestScope(permissions, 'team_member', 'edit')
  return (editScope !== null && editScope !== 'own') || (teamScope !== null && teamScope !== 'own')
}

/**
 * Which actions to show for one row of the member table. A person can hold several
 * memberships, and the rank check compares the SPECIFIC membership acted on (§3.4), so
 * the result lists the membership ids each action may be applied to.
 */
export function rowActions(
  actor: Actor,
  permissions: readonly Permission[],
  row: MemberSummaryRow,
): RowActions {
  const extendRoleIds: string[] = []
  const moveRoleIds: string[] = []
  for (const role of row.roles) {
    const target = targetRoleOf(row, role)
    if (canExtendTerm(actor, permissions, target)) extendRoleIds.push(role.membershipId)
    if (canMoveToTeam(actor, permissions, target)) moveRoleIds.push(role.membershipId)
  }
  return { extendRoleIds, moveRoleIds }
}

// ---------------------------------------------------------------------------
// Tracking (§2A.6): own numbers, plus tracking someone below you
// ---------------------------------------------------------------------------

/**
 * The functions the actor currently holds, deduplicated, for the Tracking page's
 * function switcher (§2A.6). A position with no function (e.g. LCP/MCP hold the
 * President function) still has one entry.
 */
export function distinctFunctions(actor: Actor): FunctionRef[] {
  const seen = new Map<string, FunctionRef>()
  for (const m of actor.memberships) {
    if (m.function && !seen.has(m.function.key)) seen.set(m.function.key, m.function)
  }
  return [...seen.values()]
}

/**
 * Whether "Track someone" should show at all (§2A.6): needs `kpi_record.edit` wider
 * than `own`. Whether a SPECIFIC person may be tracked is a separate, per-person check
 * (`canTrackPerson`), because scope and rank are checked per target, same as Extend
 * term and Move to team.
 */
export function canTrackOthers(permissions: readonly Permission[]): boolean {
  const scope = widestScope(permissions, 'kpi_record', 'edit')
  return scope !== null && scope !== 'own'
}

/** The two-check rule (§3.4) applied to tracking one specific person's numbers. */
function canTrackPerson(
  actor: Actor,
  permissions: readonly Permission[],
  target: TargetRole,
): boolean {
  return canActOnTarget(actor, permissions, 'kpi_record', target)
}

/** Which of a member-row's position/function pairs the actor may track (§2A.6, §3.4). */
export function trackableRoleIds(
  actor: Actor,
  permissions: readonly Permission[],
  row: MemberSummaryRow,
): string[] {
  return row.roles
    .filter((role) => canTrackPerson(actor, permissions, targetRoleOf(row, role)))
    .map((role) => role.membershipId)
}

// ---------------------------------------------------------------------------
// Adding a member: which LCs, positions and functions to offer (§2A.5, §3.4, §3.6)
// ---------------------------------------------------------------------------

/**
 * LCs the actor may add to. `all` scope (MC) picks any LC, or the MC itself. Every
 * narrower scope is fixed to the LC(s) where the actor holds an active membership.
 */
export function addableLcs(
  actor: Actor,
  permissions: readonly Permission[],
  lcs: readonly Lc[],
): Lc[] {
  const scope = widestScope(permissions, 'membership', 'create')
  if (scope === null || scope === 'own') return []
  if (scope === 'all') return [...lcs]
  const own = new Set(actor.memberships.map((m) => m.lc.id))
  return lcs.filter((lc) => own.has(lc.id))
}

/**
 * Teams offered for a given LC + function, once a team-holding position is chosen
 * (§3.4, §3.6). A Team-Leader-scope adder never reaches this — `fixedTeam` already
 * gives them their one team; this is for the broader scopes that get a genuine choice.
 */
export function addableTeams(
  actor: Actor,
  permissions: readonly Permission[],
  teams: readonly Team[],
  lc: Lc,
  functionKey: string,
): Team[] {
  if (!addableLcs(actor, permissions, [lc]).length) return []
  return teams.filter((t) => t.lcId === lc.id && t.functionKey === functionKey)
}

/**
 * All of the actor's active memberships that tie with `actingMembership`'s own choice
 * (same position, hence same rank and grants — the permission matrix is keyed by
 * position). Usually one membership; more than one when the actor holds several of
 * that same position (e.g. Team Leader of two teams) — Add-Member then asks which one
 * they're adding under, instead of silently picking the first in array order.
 */
export function actingMembershipCandidates(actor: Actor): MembershipView[] {
  const key = actingPosition(actor)?.key
  return key === undefined ? [] : actor.memberships.filter((m) => m.position.key === key)
}

/** Narrows an actor to exactly one membership — the one they've explicitly chosen to
 * act as (Add-Member's "Add as" picker). Every `addable*`/`fixedTeam` function then
 * behaves as if that were the actor's only membership. */
export function narrowToMembership(actor: Actor, membershipId: string): Actor {
  return { personId: actor.personId, memberships: actor.memberships.filter((m) => m.id === membershipId) }
}

/**
 * Positions offered for a given LC:
 *   - level must match the LC type (§3.6),
 *   - rank must be BELOW the actor's (§3.4),
 *   - except the president exception: a position with `canAddSameRank` may add another
 *     holder of the SAME position (LCP in their own LC only, which `addableLcs` already
 *     guarantees; MCP in the MC). It applies to adding only.
 */
export function addablePositions(
  actor: Actor,
  permissions: readonly Permission[],
  positions: readonly Position[],
  lc: Lc,
): Position[] {
  const acting = actingPosition(actor)
  if (acting === null) return []
  if (!addableLcs(actor, permissions, [lc]).length) return []
  return positions.filter(
    (p) =>
      p.level === lc.type &&
      (outranks(actor, p) || (acting.canAddSameRank && p.key === acting.key)),
  )
}

/**
 * The Team Leader's own team (§3.4): a `team`-scope adder can only add to it, and so
 * only in that team's function.
 */
export function fixedTeam(
  actor: Actor,
  permissions: readonly Permission[],
): { team: { id: string; name: string }; functionKey: string | null } | null {
  if (widestScope(permissions, 'membership', 'create') !== 'team') return null
  const acting = actingMembership(actor)
  return acting?.team ? { team: acting.team, functionKey: acting.function?.key ?? null } : null
}

/**
 * Functions offered for a position. Presidential positions use the President function
 * and nobody else does (see `Position.presidential`). A team-scope adder is fixed to
 * their team's function.
 */
export function addableFunctions(
  actor: Actor,
  permissions: readonly Permission[],
  functions: readonly FunctionDef[],
  position: Position,
): FunctionDef[] {
  const fitting = functions.filter((f) => f.active && f.presidentOnly === position.presidential)
  const team = fixedTeam(actor, permissions)
  if (team) return fitting.filter((f) => f.key === team.functionKey)
  return fitting
}

// ---------------------------------------------------------------------------
// Data page scope tabs (§2A.7, §6)
// ---------------------------------------------------------------------------

/**
 * Which grouping tabs (Team / Function / LC / Australia-wide) to offer on the Data
 * page. A grant at one scope already covers every NARROWER cut of the same data (a
 * function's total is built from the teams inside it, §6 "computed by query"), so
 * every scope up to and including the widest grant is safe to offer. This is a
 * frontend assumption pending the real report design (spec §12 #18).
 */
export function availableDataScopes(permissions: readonly Permission[]): Scope[] {
  const maxScope = widestScope(permissions, 'analytics_report', 'view')
  if (maxScope === null) return []
  const maxIndex = scopeRank(maxScope)
  return (['team', 'function', 'lc', 'all'] as const).filter((s) => scopeRank(s) <= maxIndex)
}

// ---------------------------------------------------------------------------
// Navigation and the homepage
// ---------------------------------------------------------------------------

export interface Gated {
  /** Omit for pages every allocated person may open. `minScope` (optional) additionally
   * requires the grant to reach at least that scope; default 'own' (any scope
   * qualifies — same as before this field existed). */
  requires?: { resource: string; action: Action; minScope?: Scope }
  /** False for pages planned but not built yet. Hidden until they exist. */
  built: boolean
}

/** Menu items the person may see. Hiding is a convenience, the server enforces access (§2A). */
export function visibleNavItems<T extends Gated>(
  items: readonly T[],
  permissions: readonly Permission[],
  options: { includeUnbuilt?: boolean } = {},
): T[] {
  return items.filter(
    (item) =>
      (item.built || options.includeUnbuilt === true) &&
      (item.requires === undefined ||
        hasMinScope(permissions, item.requires.resource, item.requires.action, item.requires.minScope ?? 'own')),
  )
}

/**
 * Which default chart the homepage shows, from the acting membership's position:
 * Member/TL see a team chart, LCVP/LCP a function chart, MC positions all of Australia.
 */
export function homeChartScope(acting: MembershipView | null): Position['homeChartScope'] {
  return acting?.position.homeChartScope ?? 'team'
}
