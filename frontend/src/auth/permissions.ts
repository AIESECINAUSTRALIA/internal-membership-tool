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
  IsoDate,
  Lc,
  Me,
  MemberSummaryRow,
  MembershipView,
  Permission,
  Position,
  Scope,
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

function canEditMembership(
  actor: Actor,
  permissions: readonly Permission[],
  resource: 'membership' | 'team_member',
  target: TargetRole,
): boolean {
  const scope = widestScope(permissions, resource, 'edit')
  if (scope === null) return false
  // Nobody can act on their own membership, so nobody can extend their own term (§2A.5).
  if (target.personId === actor.personId) return false
  return scopeCovers(scope, actor, target) && outranks(actor, target.position)
}

/** Extend term edits the membership's end date (§2A.5). Needs `membership.edit`. */
export function canExtendTerm(
  actor: Actor,
  permissions: readonly Permission[],
  target: TargetRole,
): boolean {
  return canEditMembership(actor, permissions, 'membership', target)
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
  return canEditMembership(actor, permissions, 'team_member', target)
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

/** True when the actor's LC is fixed rather than chosen (everyone except MC, §2A.5). */
export function isLcFixed(permissions: readonly Permission[]): boolean {
  const scope = widestScope(permissions, 'membership', 'create')
  return scope !== null && scope !== 'all'
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
      (p.rank < acting.rank || (acting.canAddSameRank && p.key === acting.key)),
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
  const withTeam = actor.memberships.find(
    (m) => m.team !== null && m.position.key === acting?.position.key,
  )
  return withTeam?.team ? { team: withTeam.team, functionKey: withTeam.function?.key ?? null } : null
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
// Navigation and the homepage
// ---------------------------------------------------------------------------

export interface Gated {
  /** Omit for pages every allocated person may open. */
  requires?: { resource: string; action: Action }
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
      (item.requires === undefined || can(permissions, item.requires.resource, item.requires.action)),
  )
}

/**
 * Which default chart the homepage shows, from the actor's highest position:
 * Member/TL see a team chart, LCVP/LCP a function chart, MC positions all of Australia.
 */
export function homeChartScope(actor: Actor): Position['homeChartScope'] {
  return actingPosition(actor)?.homeChartScope ?? 'team'
}
