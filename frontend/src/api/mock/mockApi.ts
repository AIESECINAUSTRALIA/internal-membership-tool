/**
 * In-memory implementation of `Api`, standing in for the real backend.
 *
 * It behaves like the server the spec describes, so the UI can be built and tested
 * without one:
 *   - scope is applied INSIDE the query, never left to the UI (§2A, LC isolation),
 *   - the member list never contains email (§2A.5),
 *   - the hierarchy rule and LC-level rule are re-checked on every write (§3.4, §3.6),
 *   - adding an existing email attaches to that person and ends their memberships in
 *     other LCs the day before the new start date (§5.1).
 *
 * Data resets on page reload, except the "signed in" flag (sessionStorage), so a
 * refresh does not sign you out.
 *
 * SIGNING IN AS SOMEONE ELSE (development only): the sign-in button signs in as the
 * default persona. `api/index.ts` can pass another persona, chosen with `?as=` in the
 * URL, e.g. /sign-in?as=tl (see PERSONAS in seed.ts). There is no persona picker in
 * the UI. Delete this with the mock when the real backend lands.
 */
import dayjs from 'dayjs'

import {
  actingMembership,
  actorFromMe,
  addableFunctions,
  addableLcs,
  addablePositions,
  addableTeams,
  can,
  canExtendTerm,
  canMoveToTeam,
  actingPosition,
  fixedTeam,
  homeChartScope,
  isActive,
  narrowToMembership,
  scopeCovers,
  widestScope,
  type Actor,
  type TargetRole,
} from '../../auth/permissions'
import type {
  ActionResult,
  AddMemberInput,
  AddMemberResult,
  AdminMembershipRow,
  AdminPersonInput,
  AdminFunctionRow,
  AdminPersonQuery,
  AdminPersonRow,
  AdminPositionRow,
  Api,
  AssignMembershipInput,
  CorrectMembershipInput,
  CatalogAttribute,
  CreateAttributeInput,
  CreateFunctionInput,
  CreateLcInput,
  CreatePositionInput,
  CustomField,
  CustomFieldValue,
  DataChart,
  DataQuery,
  FunctionDef,
  HomeChart,
  IsoDate,
  Lc,
  MemberQuery,
  MemberRole,
  MemberSummaryRow,
  MergeLcResult,
  Me,
  MembershipDetail,
  MembershipView,
  Page,
  Permission,
  Position,
  ReferenceData,
  StateTimezone,
  UpdateAttributeInput,
  UpdateFunctionInput,
  UpdateLcInput,
  UpdatePositionInput,
} from '../types'
import { shortLabel } from '../../lib/labels'
import { definitionProblem, KEY_PATTERN } from './attributeRules'
import {
  ATTRIBUTES,
  buildSeed,
  buildTerms,
  CUSTOM_FIELD_DEFS,
  FUNCTIONS,
  LCS,
  PERMISSION_MATRIX,
  STATE_TIMEZONES,
  PERSONAS,
  POSITIONS,
  TEAMS,
  type DbAttribute,
  type DbMembership,
  type DbPerson,
  type MockDb,
  type PersonaKey,
} from './seed'

const SESSION_KEY = 'membership-tool.mock-session'

export interface MockApiOptions {
  /** Who the sign-in button signs in as. Defaults to the LC Vice President. */
  persona?: PersonaKey
  /** Fake network delay. Tests pass 0. */
  latencyMs?: number
  /** Today, as an ISO date. Tests pass a fixed value. */
  today?: () => IsoDate
  /** Person-level custom field catalog (§4.2). Empty by default: see seed.ts. */
  customFieldDefs?: Omit<CustomField, 'value'>[]
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** A deep-enough copy: the arrays and validation object are edited in place otherwise. */
function copyAttribute(attribute: DbAttribute): DbAttribute {
  return {
    ...attribute,
    enumOptions: attribute.enumOptions && [...attribute.enumOptions],
    validation: attribute.validation && { ...attribute.validation },
    recorded: [...attribute.recorded],
  }
}

// ---- Positions & functions (§1.5, §2A.2, DEV-0049) ---------------------------

/** A position as the mock stores it: the app's `Position`, plus id and active flag. */
type StoredPosition = Position & { id: number; active: boolean }
/** A function as the mock stores it: the app's `FunctionDef`, plus an id. */
type StoredFunction = FunctionDef & { id: number }

/** Back to the plain `Position` the rest of the app expects. */
function asPosition(p: StoredPosition): Position {
  return {
    key: p.key,
    label: p.label,
    level: p.level,
    rank: p.rank,
    canAddSameRank: p.canAddSameRank,
    presidential: p.presidential,
    homeChartScope: p.homeChartScope,
    holdsTeam: p.holdsTeam,
  }
}

function asFunctionDef(f: StoredFunction): FunctionDef {
  return { key: f.key, label: f.label, active: f.active, presidentOnly: f.presidentOnly }
}

/** Positions whose holders can open the Admin console. Deactivating one is a way to
 * lock every admin out (docs/admin-lockout-recovery.md), so the screen refuses. */
const adminAccessPositionKeys = new Set(
  PERMISSION_MATRIX.filter((r) => r.resource === 'admin_console').map((r) => r.positionKey),
)

const OUTRANKED_MESSAGE = 'You can only change positions ranked below your own.'

/**
 * Position keys the permission rules give meaning to, same as the backend's
 * `RESERVED_POSITION_KEYS`. A new position never gets one, even if no position holds
 * it yet, or it would inherit those permissions ("Admin" becoming a real admin).
 * `admin` is listed by hand: the backend grants it, but no mock persona holds it.
 */
const RESERVED_POSITION_KEYS: ReadonlySet<string> = new Set([
  ...PERMISSION_MATRIX.map((r) => r.positionKey),
  ...POSITIONS.map((p) => p.key),
  'admin',
])

/**
 * The hierarchy rule for editing positions (§3.4), same as the backend's
 * `can_edit_position`: the position must rank below the actor's highest position,
 * and so must any new rank given to it. `null` means "no rank involved".
 */
function canEditPosition(actor: Actor, currentRank: number | null, newRank: number | null): boolean {
  const topRank = actingPosition(actor)?.rank
  if (topRank === undefined) return false
  if (currentRank !== null && currentRank >= topRank) return false
  if (newRank !== null && newRank >= topRank) return false
  return true
}

function isValidRank(rank: unknown): rank is number {
  return typeof rank === 'number' && Number.isInteger(rank) && rank >= 1
}

/** Names are unique ignoring case. `exceptId` skips the row being renamed. */
function labelTaken(rows: readonly { id: number; label: string }[], label: string, exceptId: number | null): boolean {
  return rows.some((r) => r.id !== exceptId && r.label.toLowerCase() === label.toLowerCase())
}

/** Same as the backend: lowercase, non-alphanumerics to `_`, then `_2`, `_3`, ... if taken.
 * Keys in `reserved` count as taken even when no row holds them. */
function uniqueKey(rows: readonly { key: string }[], label: string, reserved: ReadonlySet<string> = new Set()): string {
  const base =
    label
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, 50) || 'item'
  const taken = new Set([...rows.map((r) => r.key), ...reserved])
  let key = base
  for (let suffix = 2; taken.has(key); suffix++) key = `${base}_${suffix}`
  return key
}

function toCatalogAttribute(attribute: DbAttribute): CatalogAttribute {
  const { recorded, ...rest } = copyAttribute(attribute)
  return { ...rest, inUse: recorded.length > 0 }
}

export function createMockApi(options: MockApiOptions = {}): Api {
  const latencyMs = options.latencyMs ?? 150
  const today = options.today ?? (() => dayjs().format('YYYY-MM-DD'))
  const persona = options.persona ?? 'lcvp'
  const customFieldDefs = options.customFieldDefs ?? CUSTOM_FIELD_DEFS

  const db: MockDb = buildSeed(today())
  // Copies, because management screens edit these and seed constants are shared.
  // Every other method reads LCs, positions and functions from these copies, so a
  // change made in the Admin console shows up everywhere (e.g. Add member).
  const lcs: Lc[] = LCS.map((lc) => ({ ...lc }))
  // Positions and functions also get a numeric id (like the backend) and an `active` flag.
  const positions: StoredPosition[] = POSITIONS.map((p, i) => ({ ...p, id: i + 1, active: true }))
  const functions: StoredFunction[] = FUNCTIONS.map((f, i) => ({ ...f, id: i + 1 }))
  const attributes: DbAttribute[] = ATTRIBUTES.map(copyAttribute)
  let sessionPersonId: string | null = readSession()
  let nextId = 1000

  const wait = () => new Promise<void>((resolve) => setTimeout(resolve, latencyMs))

  function readSession(): string | null {
    try {
      return sessionStorage.getItem(SESSION_KEY)
    } catch {
      return null
    }
  }
  function writeSession(personId: string | null): void {
    sessionPersonId = personId
    try {
      if (personId) sessionStorage.setItem(SESSION_KEY, personId)
      else sessionStorage.removeItem(SESSION_KEY)
    } catch {
      /* storage blocked: the session just lasts until reload */
    }
  }

  // ---- lookups ------------------------------------------------------------
  // Includes inactive positions: existing memberships keep showing theirs (§1.5).
  const position = (key: string): Position => {
    const found = positions.find((p) => p.key === key)
    if (!found) throw new Error(`Unknown position ${key}`)
    return asPosition(found)
  }
  /** What Add member may offer: active positions only. */
  const activePositions = (): Position[] => positions.filter((p) => p.active).map(asPosition)
  /** Every function, with its `active` flag: callers already skip inactive ones. */
  const functionDefs = (): FunctionDef[] => functions.map(asFunctionDef)
  const lcOf = (id: string): Lc => {
    const found = lcs.find((l) => l.id === id)
    if (!found) throw new Error(`Unknown LC ${id}`)
    return found
  }
  const functionRef = (key: string | null) => {
    if (key === null) return null
    const f = functions.find((x) => x.key === key)
    return f ? { key: f.key, label: f.label } : null
  }
  const teamRef = (id: string | null) => {
    const t = TEAMS.find((x) => x.id === id)
    return t ? { id: t.id, name: t.name } : null
  }
  const personById = (id: string) => db.people.find((p) => p.id === id)

  /** The longest-serving person currently holding `team_leader` for this team. Mock-only
   * simplification: the real schema's `team.leader_membership_id` (docs/data-model.md)
   * is a single explicit FK; this derives an equivalent from membership data since the
   * mock seed can (rarely) have more than one active Team Leader per team. */
  function resolveTeamLeader(teamId: string): { membershipId: string; name: string } | null {
    const leader = db.memberships
      .filter((m) => m.teamId === teamId && m.positionKey === 'team_leader' && isActive(m, today()))
      .sort((a, b) => (a.startDate < b.startDate ? -1 : 1))[0]
    if (!leader) return null
    const person = personById(leader.personId)!
    return { membershipId: leader.id, name: [person.firstName, person.lastName].filter(Boolean).join(' ') }
  }

  function toView(m: DbMembership): MembershipView {
    return {
      id: m.id,
      position: position(m.positionKey),
      function: functionRef(m.functionKey),
      lc: lcOf(m.lcId),
      team: teamRef(m.teamId),
      startDate: m.startDate,
      endDate: m.endDate,
    }
  }

  /** §3.2: the widest grant per (resource, action) across the person's ACTIVE memberships. */
  function resolvePermissions(personId: string): Permission[] {
    const widest = new Map<string, Permission>()
    const order = ['own', 'team', 'function', 'lc', 'all']
    for (const m of db.memberships) {
      if (m.personId !== personId || !isActive(m, today())) continue
      for (const r of PERMISSION_MATRIX) {
        if (r.positionKey !== m.positionKey) continue
        const key = `${r.resource}:${r.action}`
        const have = widest.get(key)
        if (!have || order.indexOf(r.scope) > order.indexOf(have.scope)) {
          widest.set(key, { resource: r.resource, action: r.action, scope: r.scope })
        }
      }
    }
    return [...widest.values()]
  }

  function buildCustomFields(personId: string): CustomField[] {
    const p = personById(personId)
    if (!p) throw new Error(`Unknown person ${personId}`)
    return customFieldDefs.map((def) => ({ ...def, value: p.customFields[def.key] ?? null }))
  }

  function buildMe(personId: string): Me {
    const p = personById(personId)
    if (!p) throw new Error(`Unknown person ${personId}`)
    // A deactivated person has no access at all, whatever their dates say (DEV-47).
    // The backend treats them as "no person"; here they land on the not-allocated page.
    const deactivated = p.status === 'inactive'
    return {
      person: { id: p.id, firstName: p.firstName, lastName: p.lastName, email: p.email },
      // Active only, like the backend's `/me` (§3.2). History is `getMyMembershipHistory`.
      memberships: deactivated
        ? []
        : db.memberships.filter((m) => m.personId === personId && isActive(m, today())).map(toView),
      permissions: deactivated ? [] : resolvePermissions(personId),
    }
  }

  function requireActor(): { me: Me; actor: Actor } {
    if (!sessionPersonId) throw new Error('Not signed in')
    const me = buildMe(sessionPersonId)
    return { me, actor: actorFromMe(me, today()) }
  }

  const targetOf = (m: DbMembership): TargetRole => ({
    personId: m.personId,
    position: position(m.positionKey),
    lcId: m.lcId,
    functionKey: m.functionKey,
    teamId: m.teamId,
  })

  const reject = (message: string) => ({ status: 'rejected' as const, message })
  const isNameTaken = (name: string, exceptId?: string) =>
    lcs.some((l) => l.id !== exceptId && l.name.toLowerCase() === name.toLowerCase())
  const isKnownState = (state: string) => STATE_TIMEZONES.some((row) => row.state === state)

  // ---- Admin console: people and memberships (DEV-47) ----------------------
  // The same rules as `backend/app/repositories/admin_people.py`.

  const dayBefore = (date: IsoDate) => dayjs(date).subtract(1, 'day').format('YYYY-MM-DD')
  const overlaps = (m: DbMembership, start: IsoDate, end: IsoDate) => m.startDate <= end && m.endDate >= start
  const isIsoDate = (date: string) => dayjs(date, 'YYYY-MM-DD', true).isValid()
  const isEmailTaken = (email: string, exceptId?: string) =>
    db.people.some((p) => p.id !== exceptId && p.email.toLowerCase() === email)
  const personRow = (p: DbPerson): AdminPersonRow => ({
    id: p.id,
    firstName: p.firstName,
    lastName: p.lastName,
    email: p.email,
    active: db.memberships.some((m) => m.personId === p.id && isActive(m, today())),
    status: p.status ?? 'active',
    expaLinked: p.expaLinked ?? false,
  })

  /** §3.4 on the Admin console: never yourself, and the position involved must rank
   * below the actor's. The president exception applies to adding only. */
  function adminRankProblem(actor: Actor, personId: string, pos: Position, lcId: string, adding: boolean): string | null {
    const acting = actingMembership(actor)
    if (!acting) return 'No active membership found.'
    if (personId === actor.personId) return "You can't change your own memberships."
    if (pos.rank < acting.position.rank) return null
    if (adding && acting.position.canAddSameRank && pos.key === acting.position.key && lcId === acting.lc.id) return null
    return "You can't assign or change a position at or above your own."
  }

  /** Editing or deactivating a person needs the actor to outrank every position they
   * hold or are about to hold: their email decides who can sign in as them. */
  function personRankProblem(actor: Actor, personId: string, allowSelf: boolean): string | null {
    if (personId === actor.personId) return allowSelf ? null : "You can't do this to your own record."
    for (const m of db.memberships) {
      if (m.personId !== personId || m.endDate < today()) continue
      const problem = adminRankProblem(actor, personId, position(m.positionKey), m.lcId, false)
      if (problem) return problem
    }
    return null
  }

  /** §3.6 and §5.1, shared by assign and correct. */
  function membershipConflict(
    personId: string,
    lc: Lc,
    functionKey: string | null,
    start: IsoDate,
    end: IsoDate,
    ignoreId?: string,
    detailed = true,
  ): string | null {
    const theirs = db.memberships.filter((m) => m.personId === personId && m.id !== ignoreId)
    if (lc.type === 'lc' && theirs.some((m) => lcOf(m.lcId).type === 'mc' && overlaps(m, start, end))) {
      return "This person can't be added. Contact your MC."
    }
    // Decision 2: a membership in another LC that overlaps and starts on or after the new
    // start would have to be ended before it began, so refuse. Same rule as the backend's
    // `membership_conflict`. Only the admin console may be told which LC and date.
    const upcoming = theirs.find((m) => m.lcId !== lc.id && m.startDate >= start && overlaps(m, start, end))
    if (upcoming) {
      if (!detailed) return 'This person already has a membership coming up elsewhere. Contact your MC.'
      return (
        `This person's membership in ${lcOf(upcoming.lcId).name} starts on ` +
        `${dayjs(upcoming.startDate).format('DD MMM YYYY')}. ` +
        'Correct it first, or end this one before that date.'
      )
    }
    if (functionKey !== null && theirs.some((m) => m.lcId === lc.id && m.functionKey === functionKey && overlaps(m, start, end))) {
      return 'This person already holds that function in this LC for overlapping dates.'
    }
    return null
  }

  const levelProblem = (pos: Position, lc: Lc) =>
    pos.level === lc.type ? null : `${pos.label} can't be used in ${lc.type === 'mc' ? 'the MC' : 'an LC'}.`

  // ---- Api ----------------------------------------------------------------
  return {
    async getMe() {
      await wait()
      return sessionPersonId && personById(sessionPersonId) ? buildMe(sessionPersonId) : null
    },

    async signIn() {
      await wait()
      writeSession(PERSONAS[persona])
    },

    async signOut() {
      await wait()
      writeSession(null)
    },

    async getMyCustomFields() {
      await wait()
      const { me } = requireActor()
      return buildCustomFields(me.person.id)
    },

    async getMyMembershipHistory() {
      await wait()
      const { me } = requireActor()
      return db.memberships
        .filter((m) => m.personId === me.person.id)
        .map(toView)
        .sort((a, b) => (a.startDate < b.startDate ? 1 : -1))
    },

    async updateMyCustomFields(values: Record<string, CustomFieldValue>) {
      await wait()
      const { me } = requireActor()
      const person = personById(me.person.id)!
      // Only catalogued person-level fields are editable (§2A.9). Anything else is ignored.
      for (const def of customFieldDefs) {
        if (def.key in values) person.customFields[def.key] = values[def.key]
      }
      return buildCustomFields(person.id)
    },

    async getReferenceData(): Promise<ReferenceData> {
      await wait()
      const teams = TEAMS.map((t) => ({ ...t, leader: resolveTeamLeader(t.id) }))
      return { lcs: lcs.filter((l) => l.active), positions: activePositions(), functions: functionDefs(), terms: buildTerms(today()), teams }
    },

    async listMembers(query: MemberQuery): Promise<Page<MemberSummaryRow>> {
      await wait()
      const { me, actor } = requireActor()
      const scope = widestScope(me.permissions, 'membership', 'view')
      if (scope === null) return { rows: [], total: 0 }

      // Current members only (§2A.5): someone who moved LC appears only in their new LC.
      const byPerson = new Map<string, DbMembership[]>()
      for (const m of db.memberships) {
        if (!isActive(m, today())) continue
        // LC isolation, applied in the query (§2A.5, §3.1).
        if (!scopeCovers(scope, actor, targetOf(m))) continue
        if (query.lcId && m.lcId !== query.lcId) continue
        byPerson.set(m.personId, [...(byPerson.get(m.personId) ?? []), m])
      }

      let rows: MemberSummaryRow[] = [...byPerson.entries()].map(([personId, ms]) => {
        const p = personById(personId)!
        const roles: MemberRole[] = ms
          .map((m) => ({
            membershipId: m.id,
            position: position(m.positionKey),
            function: functionRef(m.functionKey),
            teamId: m.teamId,
          }))
          .sort((a, b) => b.position.rank - a.position.rank)
        // NOTE: no email here, by design (§2A.5).
        return { personId, firstName: p.firstName, lastName: p.lastName, lc: lcOf(ms[0].lcId), roles }
      })

      const needle = query.search.trim().toLowerCase()
      if (needle) {
        rows = rows.filter((r) =>
          [
            r.firstName,
            r.lastName,
            `${r.firstName} ${r.lastName}`,
            r.lc.name,
            ...r.roles.flatMap((x) => [x.position.label, x.function?.label ?? '']),
          ].some((s) => s.toLowerCase().includes(needle)),
        )
      }

      const sort = query.sort ?? { field: 'lastName' as const, direction: 'asc' as const }
      const value = (r: MemberSummaryRow): string | number =>
        sort.field === 'firstName' ? r.firstName
        : sort.field === 'lastName' ? r.lastName
        : sort.field === 'lc' ? r.lc.name
        : r.roles[0].position.rank // highest position first
      // Natural order, so "Member 2" comes before "Member 10".
      const collator = new Intl.Collator('en', { numeric: true, sensitivity: 'base' })
      rows.sort((a, b) => {
        const av = value(a)
        const bv = value(b)
        const cmp =
          typeof av === 'number' && typeof bv === 'number'
            ? av - bv
            : collator.compare(String(av), String(bv)) || collator.compare(a.firstName + a.lastName, b.firstName + b.lastName)
        return sort.direction === 'asc' ? cmp : -cmp
      })

      const start = query.page * query.pageSize
      return { rows: rows.slice(start, start + query.pageSize), total: rows.length }
    },

    async addMember(input: AddMemberInput): Promise<AddMemberResult> {
      await wait()
      const { me, actor: fullActor } = requireActor()
      // Re-derived server-side, never trusted from the client: which of the actor's own
      // memberships this request is acting under (§3.4 — the hierarchy rule compares the
      // specific membership, not just "the actor" in the abstract).
      const chosenMembershipId = input.membershipId ?? actingMembership(fullActor)?.id
      const actor = chosenMembershipId ? narrowToMembership(fullActor, chosenMembershipId) : fullActor
      const start = input.startDate
      const end = input.endDate

      if (!EMAIL_PATTERN.test(input.email.trim())) return reject('Enter a valid email address.')
      if (!dayjs(start, 'YYYY-MM-DD', true).isValid() || !dayjs(end, 'YYYY-MM-DD', true).isValid()) {
        return reject('Enter a start date and an end date.')
      }
      if (end < start) return reject('The end date must be on or after the start date.')

      // Hierarchy rule, LC-level rule and scope, re-checked on the "server" (§3.4, §3.6).
      const lc = lcs.find((l) => l.id === input.lcId)
      const offeredPositions = activePositions()
      const pos = offeredPositions.find((p) => p.key === input.positionKey)
      if (!lc || !pos || !addableLcs(actor, me.permissions, lcs.filter((l) => l.active)).some((l) => l.id === lc.id)) {
        return reject("You can't add people to that LC.")
      }
      if (!addablePositions(actor, me.permissions, offeredPositions, lc).some((p) => p.key === pos.key)) {
        return reject("You can't add that position.")
      }
      const fn = addableFunctions(actor, me.permissions, functionDefs(), pos).find((f) => f.key === input.functionKey)
      if (!fn) return reject("You can't add that function.")

      // Team pinning (§3.4): a Team-Leader-scope adder is fixed to their own team;
      // anyone broader picks one, re-validated here against the same options they saw.
      const fixed = fixedTeam(actor, me.permissions)
      let teamId: string | null = null
      if (fixed) {
        teamId = fixed.team.id
      } else if (pos.holdsTeam) {
        const chosenTeam = addableTeams(actor, me.permissions, TEAMS, lc, fn.key).find((t) => t.id === input.teamId)
        if (!chosenTeam) return reject('Choose a team.')
        teamId = chosenTeam.id
      }

      const email = input.email.trim().toLowerCase()
      const existing = db.people.find((p) => p.email === email)
      if (existing?.id === me.person.id) return reject("This person can't be added. Contact your MC.")
      // Only the Admin console's Reactivate brings a deactivated person back (DEV-47).
      if (existing?.status === 'inactive') return reject("This person can't be added. Contact your MC.")

      if (!existing) {
        if (!input.firstName?.trim() || !input.lastName?.trim()) return { status: 'needs_name' }
      } else if (!input.confirmedExisting) {
        return { status: 'confirm_existing' }
      }

      if (existing) {
        const theirs = db.memberships.filter((m) => m.personId === existing.id)
        // MC to LC is blocked while the MC membership overlaps the new dates (§3.6).
        // The message is generic and does not say why.
        const blockedByMc = theirs.some(
          (m) => lcOf(m.lcId).type === 'mc' && lc.type === 'lc' && m.startDate <= end && m.endDate >= start,
        )
        if (blockedByMc) return reject("This person can't be added. Contact your MC.")
        const upcomingProblem = membershipConflict(existing.id, lc, fn.key, start, end, undefined, false)
        if (upcomingProblem) return reject(upcomingProblem)
        if (
          theirs.some(
            (m) => m.lcId === lc.id && m.functionKey === fn.key && m.startDate <= end && m.endDate >= start,
          )
        ) {
          return reject('This person already holds that function in this LC for overlapping dates.')
        }
        // Transfer: memberships in OTHER LCs end the day before the new start (§5.1).
        const dayBefore = dayjs(start).subtract(1, 'day').format('YYYY-MM-DD')
        for (const m of theirs) {
          if (m.lcId !== lc.id && m.endDate >= start) m.endDate = dayBefore < m.startDate ? m.startDate : dayBefore
        }
      }

      const personId = existing?.id ?? `p-new-${nextId++}`
      if (!existing) {
        db.people.push({
          id: personId,
          firstName: input.firstName!.trim(),
          lastName: input.lastName!.trim(),
          email,
          customFields: {},
        })
      }
      db.memberships.push({
        id: `m-${nextId++}`,
        personId,
        lcId: lc.id,
        positionKey: pos.key,
        functionKey: fn.key,
        termId: input.termId ?? '',
        startDate: start,
        endDate: end,
        teamId,
      })
      return { status: 'created' }
    },

    async getMembershipDetail(membershipId: string): Promise<MembershipDetail> {
      await wait()
      const { me, actor } = requireActor()
      const m = db.memberships.find((x) => x.id === membershipId)
      if (!m) throw new Error('Membership not found')
      const person = personById(m.personId)!
      const scope = widestScope(me.permissions, 'team_member', 'edit')
      // Only teams in the viewer's scope, in the same LC and function.
      const teamOptions = TEAMS.filter(
        (t) =>
          scope !== null &&
          t.lcId === m.lcId &&
          t.functionKey === m.functionKey &&
          t.id !== m.teamId &&
          scopeCovers(scope, actor, { ...targetOf(m), teamId: t.id }),
      )
      return {
        membershipId,
        personName: [person.firstName, person.lastName].filter(Boolean).join(' '),
        position: position(m.positionKey),
        function: functionRef(m.functionKey),
        lc: lcOf(m.lcId),
        startDate: m.startDate,
        endDate: m.endDate,
        currentTeam: teamRef(m.teamId),
        teamOptions,
      }
    },

    async extendTerm(membershipId: string, newEndDate: IsoDate): Promise<ActionResult> {
      await wait()
      const { me, actor } = requireActor()
      const m = db.memberships.find((x) => x.id === membershipId)
      if (!m || !canExtendTerm(actor, me.permissions, targetOf(m))) {
        return reject("You can't extend this term.")
      }
      if (!dayjs(newEndDate, 'YYYY-MM-DD', true).isValid() || newEndDate <= m.endDate) {
        return reject('Choose an end date after the current end date.')
      }
      m.endDate = newEndDate
      return { status: 'ok' }
    },

    async moveToTeam(membershipId: string, teamId: string): Promise<ActionResult> {
      await wait()
      const { me, actor } = requireActor()
      const m = db.memberships.find((x) => x.id === membershipId)
      const team = TEAMS.find((t) => t.id === teamId)
      if (!m || !team || !canMoveToTeam(actor, me.permissions, targetOf(m))) {
        return reject("You can't move this person.")
      }
      if (team.lcId !== m.lcId || team.functionKey !== m.functionKey) {
        return reject('Choose a team in the same LC and function.')
      }
      m.teamId = team.id
      return { status: 'ok' }
    },

    async getHomeChart(): Promise<HomeChart> {
      await wait()
      const { actor } = requireActor()
      const acting = actingMembership(actor)
      const scope = homeChartScope(acting)
      const where =
        scope === 'team' ? (acting?.team?.name ?? 'your team')
        : scope === 'function' ? (acting?.function ? shortLabel(acting.function.label) : 'your function')
        : 'All LCs'
      // No KPI catalog yet (spec §4.3 TODO), so there is nothing to plot: "No data exists".
      return {
        scope,
        kpi: null,
        availableKpis: [],
        title: `Monthly activity, ${where}`,
        period: 'monthly',
        points: [],
      }
    },

    async getDataChart(query: DataQuery): Promise<DataChart> {
      await wait()
      requireActor()
      return {
        scope: query.scope,
        kpi: null,
        availableKpis: [],
        summaryRows: [],
        period: 'monthly',
        points: [],
      }
    },

    // ---- Admin console: LCs (§1.5, §2A.2) -----------------------------------
    // Same rules as the backend: needs `manage` on `lc`, state must be a known one,
    // no hard delete, and a merge ends memberships and opens new ones (history is kept).

    async listLcsAdmin(): Promise<Lc[]> {
      await wait()
      const { me } = requireActor()
      if (!can(me.permissions, 'lc', 'manage')) return []
      return lcs.map((lc) => ({ ...lc }))
    },

    async listStateTimezones(): Promise<StateTimezone[]> {
      await wait()
      requireActor()
      return STATE_TIMEZONES.map((row) => ({ ...row }))
    },

    async createLc(input: CreateLcInput): Promise<ActionResult> {
      await wait()
      const { me } = requireActor()
      if (!can(me.permissions, 'lc', 'manage')) return reject("You can't manage LCs.")
      const name = input.name.trim()
      if (!name) return reject('Enter a name for the LC.')
      if (isNameTaken(name)) return reject('An LC with that name already exists.')
      if (input.state !== null && !isKnownState(input.state)) return reject('Choose a valid state.')
      lcs.push({ id: `lc-new-${nextId++}`, name, type: 'lc', state: input.state, active: true })
      return { status: 'ok' }
    },

    async updateLc(lcId: string, changes: UpdateLcInput): Promise<ActionResult> {
      await wait()
      const { me } = requireActor()
      if (!can(me.permissions, 'lc', 'manage')) return reject("You can't manage LCs.")
      const lc = lcs.find((l) => l.id === lcId)
      if (!lc) return reject('That LC no longer exists.')
      if (changes.name !== undefined) {
        const name = changes.name.trim()
        if (!name) return reject('Enter a name for the LC.')
        if (isNameTaken(name, lc.id)) return reject('An LC with that name already exists.')
      }
      if (changes.state !== undefined && !isKnownState(changes.state)) return reject('Choose a valid state.')

      if (changes.name !== undefined) lc.name = changes.name.trim()
      if (changes.state !== undefined) lc.state = changes.state
      if (changes.active !== undefined) lc.active = changes.active
      return { status: 'ok' }
    },

    async mergeLc(sourceId: string, targetId: string): Promise<MergeLcResult> {
      await wait()
      const { me } = requireActor()
      if (!can(me.permissions, 'lc', 'manage')) return reject("You can't manage LCs.")
      const source = lcs.find((l) => l.id === sourceId)
      const target = lcs.find((l) => l.id === targetId)
      if (!source || !target) return reject('That LC no longer exists.')
      if (source.id === target.id) return reject('Choose a different LC to merge into.')
      if (!source.active) return reject('That LC is already inactive.')
      if (!target.active) return reject('You cannot merge into an inactive LC.')
      if (source.type === 'mc' || target.type === 'mc') return reject('The MC cannot be merged.')

      const mergeDate = today()
      const dayBefore = dayjs(mergeDate).subtract(1, 'day').format('YYYY-MM-DD')
      let membershipsMoved = 0
      let futureRepointed = 0

      for (const m of db.memberships.filter((x) => x.lcId === source.id && x.endDate >= mergeDate)) {
        if (m.startDate >= mergeDate) {
          // Not started yet, so there is no history to keep: just change the LC.
          m.lcId = target.id
          futureRepointed++
          continue
        }
        // Started already: end it yesterday and open a new one in the target from today.
        // Its past records stay with the old membership, so they still count towards the source.
        const originalEnd = m.endDate
        m.endDate = dayBefore
        db.memberships.push({ ...m, id: `m-merge-${nextId++}`, lcId: target.id, startDate: mergeDate, endDate: originalEnd, teamId: null })
        membershipsMoved++
      }

      source.active = false
      return {
        status: 'ok',
        summary: {
          membershipsMoved,
          futureMembershipsRepointed: futureRepointed,
          teamsCreated: 0,
          teamsReused: 0,
          leadersNotCarried: 0,
        },
      }
    },

    async listPeopleAdmin(query: AdminPersonQuery): Promise<Page<AdminPersonRow>> {
      await wait()
      const { me } = requireActor()
      // Admin-only, all-or-nothing scope (§2A.2): unlike the member list, there is no
      // narrower cut to apply, so a missing grant simply returns nothing (deny by default).
      if (widestScope(me.permissions, 'person', 'manage') === null) return { rows: [], total: 0 }

      let rows: AdminPersonRow[] = db.people.map(personRow)

      const needle = query.search.trim().toLowerCase()
      if (needle) {
        rows = rows.filter((r) =>
          [r.firstName, r.lastName, `${r.firstName} ${r.lastName}`, r.email].some((s) =>
            s.toLowerCase().includes(needle),
          ),
        )
      }

      const collator = new Intl.Collator('en', { numeric: true, sensitivity: 'base' })
      rows.sort((a, b) => collator.compare(a.lastName, b.lastName) || collator.compare(a.firstName, b.firstName))

      const start = query.page * query.pageSize
      return { rows: rows.slice(start, start + query.pageSize), total: rows.length }
    },

    async createPerson(input: AdminPersonInput): Promise<ActionResult> {
      await wait()
      const { me } = requireActor()
      if (!can(me.permissions, 'person', 'manage')) return reject("You can't manage people.")
      const firstName = input.firstName.trim()
      const lastName = input.lastName.trim()
      const email = input.email.trim().toLowerCase()
      if (!firstName || !lastName) return reject('Enter a first name and a last name.')
      if (!EMAIL_PATTERN.test(email)) return reject('Enter a valid email address.')
      if (isEmailTaken(email)) return reject('Someone already has that email address.')
      db.people.push({ id: `p-new-${nextId++}`, firstName, lastName, email, customFields: {}, status: 'active' })
      return { status: 'ok' }
    },

    async updatePerson(personId: string, changes: Partial<AdminPersonInput>): Promise<ActionResult> {
      await wait()
      const { me, actor } = requireActor()
      if (!can(me.permissions, 'person', 'manage')) return reject("You can't manage people.")
      const person = personById(personId)
      if (!person) return reject('That person no longer exists.')
      const problem = personRankProblem(actor, personId, true)
      if (problem) return reject(problem)

      // All or nothing: check every field before changing any.
      const firstName = (changes.firstName ?? person.firstName).trim()
      const lastName = (changes.lastName ?? person.lastName).trim()
      const email = (changes.email ?? person.email).trim().toLowerCase()
      if (!firstName || !lastName) return reject('Enter a first name and a last name.')
      if (!EMAIL_PATTERN.test(email)) return reject('Enter a valid email address.')
      if (isEmailTaken(email, person.id)) return reject('Someone already has that email address.')
      Object.assign(person, { firstName, lastName, email })
      return { status: 'ok' }
    },

    async deactivatePerson(personId: string): Promise<ActionResult> {
      await wait()
      const { me, actor } = requireActor()
      if (!can(me.permissions, 'person', 'manage')) return reject("You can't manage people.")
      const person = personById(personId)
      if (!person) return reject('That person no longer exists.')
      if (person.status === 'inactive') return reject('This person is already deactivated.')
      const problem = personRankProblem(actor, personId, false)
      if (problem) return reject(problem)

      // End what's active today on yesterday (or today, if it only started today).
      // Nothing is removed: the memberships stay, as history (§1.5).
      const yesterday = dayBefore(today())
      for (const m of db.memberships) {
        if (m.personId === personId && isActive(m, today())) m.endDate = yesterday < m.startDate ? m.startDate : yesterday
      }
      person.status = 'inactive'
      return { status: 'ok' }
    },

    async unlinkExpa(personId: string): Promise<ActionResult> {
      await wait()
      const { me, actor } = requireActor()
      if (!can(me.permissions, 'person', 'manage')) return reject("You can't manage people.")
      const person = personById(personId)
      if (!person) return reject('That person no longer exists.')
      if (!person.expaLinked) return reject("This person isn't linked to EXPA.")
      const problem = personRankProblem(actor, personId, false)
      if (problem) return reject(problem)
      person.expaLinked = false
      return { status: 'ok' }
    },

    async reactivatePerson(personId: string): Promise<ActionResult> {
      await wait()
      const { me, actor } = requireActor()
      if (!can(me.permissions, 'person', 'manage')) return reject("You can't manage people.")
      const person = personById(personId)
      if (!person) return reject('That person no longer exists.')
      if (person.status !== 'inactive') return reject('Only a deactivated person can be reactivated.')
      const problem = personRankProblem(actor, personId, false)
      if (problem) return reject(problem)
      person.status = 'active'
      return { status: 'ok' }
    },

    async listPersonMemberships(personId: string): Promise<AdminMembershipRow[]> {
      await wait()
      const { me } = requireActor()
      if (!can(me.permissions, 'membership', 'manage')) return []
      return db.memberships
        .filter((m) => m.personId === personId)
        .sort((a, b) => (a.startDate < b.startDate ? 1 : a.startDate > b.startDate ? -1 : 0))
        .map((m) => {
          const lc = lcOf(m.lcId)
          const pos = position(m.positionKey)
          return {
            id: m.id,
            lc: { id: lc.id, name: lc.name, type: lc.type },
            position: { key: pos.key, label: pos.label },
            function: functionRef(m.functionKey),
            termName: buildTerms(today()).find((t) => t.id === m.termId)?.name ?? null,
            teamName: teamRef(m.teamId)?.name ?? null,
            startDate: m.startDate,
            endDate: m.endDate,
            current: isActive(m, today()),
          }
        })
    },

    async assignMembership(personId: string, input: AssignMembershipInput): Promise<ActionResult> {
      await wait()
      const { me, actor } = requireActor()
      if (!can(me.permissions, 'membership', 'manage')) return reject("You can't manage memberships.")
      const person = personById(personId)
      if (!person) return reject('That person no longer exists.')
      if (person.status === 'inactive') return reject('Reactivate this person before assigning a membership.')
      const { startDate: start, endDate: end } = input
      if (!isIsoDate(start) || !isIsoDate(end)) return reject('Enter a start date and an end date.')
      if (end < start) return reject('The end date must be on or after the start date.')

      const lc = lcs.find((l) => l.id === input.lcId)
      if (!lc) return reject('LC not found.')
      if (!lc.active) return reject('That LC is inactive.')
      const pos = positions.find((p) => p.key === input.positionKey && p.active)
      if (!pos) return reject('Choose a position that is in use.')
      if (input.functionKey !== null && !functions.some((f) => f.key === input.functionKey && f.active)) {
        return reject('Choose a function that is in use.')
      }
      const problem =
        adminRankProblem(actor, personId, pos, lc.id, true) ??
        levelProblem(pos, lc) ??
        membershipConflict(personId, lc, input.functionKey, start, end)
      if (problem) return reject(problem)
      const term = buildTerms(today()).find((t) => t.startDate <= start && t.endDate >= start)
      if (!term) return reject('No term covers that start date.')

      // Transfer (§5.1): memberships in other LCs end the day before the new one starts.
      // None of them starts on or after the new start: `membershipConflict` refused that.
      for (const m of db.memberships) {
        if (m.personId === personId && m.lcId !== lc.id && overlaps(m, start, end)) {
          m.endDate = dayBefore(start)
        }
      }
      db.memberships.push({
        id: `m-${nextId++}`,
        personId,
        lcId: lc.id,
        positionKey: pos.key,
        functionKey: input.functionKey,
        termId: term.id,
        startDate: start,
        endDate: end,
        teamId: null,
      })
      return { status: 'ok' }
    },

    // ---- Admin console: Positions & functions (§1.5, §2A.2) -----------------
    // Same rules as the backend (DEV-0049): `manage` on `position` / `function`; the
    // hierarchy rule for positions; names unique ignoring case; positions that give
    // admin access can't be deactivated; level and rank required and never cleared.

    async listPositionsAdmin(): Promise<AdminPositionRow[]> {
      await wait()
      const { me } = requireActor()
      if (!can(me.permissions, 'position', 'manage')) return []
      return [...positions]
        .sort((a, b) => b.rank - a.rank || a.label.localeCompare(b.label))
        .map((p) => ({
          id: p.id,
          key: p.key,
          label: p.label,
          level: p.level,
          rank: p.rank,
          canAddSameRank: p.canAddSameRank,
          active: p.active,
        }))
    },

    async createPosition(input: CreatePositionInput): Promise<ActionResult> {
      await wait()
      const { me, actor } = requireActor()
      if (!can(me.permissions, 'position', 'manage')) return reject("You don't have permission to manage positions.")
      const label = input.label.trim()
      if (!label) return reject('Enter a name for the position.')
      if (!isValidRank(input.rank)) return reject('Enter a rank of 1 or more.')
      if (!canEditPosition(actor, null, input.rank)) return reject(OUTRANKED_MESSAGE)
      if (labelTaken(positions, label, null)) return reject('A position with that name already exists.')
      positions.push({
        id: nextId++,
        key: uniqueKey(positions, label, RESERVED_POSITION_KEYS),
        label,
        level: input.level,
        rank: input.rank,
        canAddSameRank: input.canAddSameRank ?? false,
        // Frontend-only fields (see `Position`): a new position starts with the
        // narrowest defaults until those become columns.
        presidential: false,
        homeChartScope: 'team',
        holdsTeam: false,
        active: true,
      })
      return { status: 'ok' }
    },

    async correctMembership(membershipId: string, changes: CorrectMembershipInput): Promise<ActionResult> {
      await wait()
      const { me, actor } = requireActor()
      if (!can(me.permissions, 'membership', 'manage')) return reject("You can't manage memberships.")
      const m = db.memberships.find((x) => x.id === membershipId)
      if (!m) return reject('Membership not found.')
      const lc = lcOf(m.lcId)
      const oldPos = position(m.positionKey)
      const ownProblem = adminRankProblem(actor, m.personId, oldPos, m.lcId, false)
      if (ownProblem) return reject(ownProblem)

      const newPos = changes.positionKey === undefined ? oldPos : positions.find((p) => p.key === changes.positionKey && p.active)
      if (!newPos) return reject('Choose a position that is in use.')
      if (newPos.key !== oldPos.key) {
        const problem = adminRankProblem(actor, m.personId, newPos, m.lcId, false) ?? levelProblem(newPos, lc)
        if (problem) return reject(problem)
      }

      const functionKey = changes.functionKey === undefined ? m.functionKey : changes.functionKey
      if (functionKey !== null && functionKey !== m.functionKey && !functions.some((f) => f.key === functionKey && f.active)) {
        return reject('Choose a function that is in use.')
      }
      if (functionKey !== m.functionKey && m.teamId !== null) {
        return reject(
          'This membership has been in a team of its current function. End it and assign a new one instead, so the team history stays right.',
        )
      }

      const start = changes.startDate ?? m.startDate
      const end = changes.endDate ?? m.endDate
      if (!isIsoDate(start) || !isIsoDate(end)) return reject('Enter a start date and an end date.')
      if (end < start) return reject('The end date must be on or after the start date.')
      const datesChanged = start !== m.startDate || end !== m.endDate
      if (
        datesChanged &&
        db.memberships.some((x) => x.personId === m.personId && x.id !== m.id && x.lcId !== m.lcId && overlaps(x, start, end))
      ) {
        return reject("These dates overlap this person's membership in another LC. Correct or end that one first.")
      }
      const conflict = membershipConflict(m.personId, lc, functionKey, start, end, m.id)
      if (conflict) return reject(conflict)

      Object.assign(m, { positionKey: newPos.key, functionKey, startDate: start, endDate: end })
      return { status: 'ok' }
    },

    async endMembership(membershipId: string, endDate: IsoDate): Promise<ActionResult> {
      await wait()
      const { me, actor } = requireActor()
      if (!can(me.permissions, 'membership', 'manage')) return reject("You can't manage memberships.")
      const m = db.memberships.find((x) => x.id === membershipId)
      if (!m) return reject('Membership not found.')
      const problem = adminRankProblem(actor, m.personId, position(m.positionKey), m.lcId, false)
      if (problem) return reject(problem)
      if (!isIsoDate(endDate)) return reject('Enter an end date.')
      if (endDate < m.startDate) return reject("A membership can't end before it started.")
      if (endDate >= m.endDate) return reject('Choose a date before the current end date. To extend, use Correct.')
      m.endDate = endDate
      return { status: 'ok' }
    },


    async updatePosition(positionId: number, changes: UpdatePositionInput): Promise<ActionResult> {
      await wait()
      const { me, actor } = requireActor()
      if (!can(me.permissions, 'position', 'manage')) return reject("You don't have permission to manage positions.")
      const pos = positions.find((p) => p.id === positionId)
      if (!pos) return reject('That position no longer exists.')
      if (!canEditPosition(actor, pos.rank, changes.rank ?? null)) return reject(OUTRANKED_MESSAGE)

      // Validate everything first, so a rejected change leaves the position untouched.
      const label = changes.label?.trim()
      if (label !== undefined) {
        if (!label) return reject('Enter a name for the position.')
        if (labelTaken(positions, label, positionId)) return reject('A position with that name already exists.')
      }
      if (changes.rank !== undefined && !isValidRank(changes.rank)) return reject('Enter a rank of 1 or more.')
      if (changes.active === false && pos.active && adminAccessPositionKeys.has(pos.key)) {
        return reject(
          "This position gives admin access, so it can't be deactivated here. Ask the tech team if it really needs to be retired.",
        )
      }

      if (label !== undefined) pos.label = label
      if (changes.level !== undefined) pos.level = changes.level
      if (changes.rank !== undefined) pos.rank = changes.rank
      if (changes.canAddSameRank !== undefined) pos.canAddSameRank = changes.canAddSameRank
      if (changes.active !== undefined) pos.active = changes.active
      return { status: 'ok' }
    },

    async listFunctionsAdmin(): Promise<AdminFunctionRow[]> {
      await wait()
      const { me } = requireActor()
      if (!can(me.permissions, 'function', 'manage')) return []
      return [...functions]
        .sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }))
        .map((f) => ({ id: f.id, key: f.key, label: f.label, active: f.active }))
    },

    async createFunction(input: CreateFunctionInput): Promise<ActionResult> {
      await wait()
      const { me } = requireActor()
      if (!can(me.permissions, 'function', 'manage')) return reject("You don't have permission to manage functions.")
      const label = input.label.trim()
      if (!label) return reject('Enter a name for the function.')
      if (labelTaken(functions, label, null)) return reject('A function with that name already exists.')
      functions.push({ id: nextId++, key: uniqueKey(functions, label), label, active: true, presidentOnly: false })
      return { status: 'ok' }
    },

    async updateFunction(functionId: number, changes: UpdateFunctionInput): Promise<ActionResult> {
      await wait()
      const { me } = requireActor()
      if (!can(me.permissions, 'function', 'manage')) return reject("You don't have permission to manage functions.")
      const func = functions.find((f) => f.id === functionId)
      if (!func) return reject('That function no longer exists.')
      const label = changes.label?.trim()
      if (label !== undefined) {
        if (!label) return reject('Enter a name for the function.')
        if (labelTaken(functions, label, functionId)) return reject('A function with that name already exists.')
        func.label = label
      }
      if (changes.active !== undefined) func.active = changes.active
      return { status: 'ok' }
    },

    // ---- Admin console: Metrics & custom fields (§1.5, §4.2) ----------------
    // Same rules as the backend: needs `manage` on `attribute`, key and applies-to are
    // fixed at creation, the data type is locked once values exist, an enum option still
    // in use can't be removed, and there is no hard delete.

    async listAttributes(): Promise<CatalogAttribute[]> {
      await wait()
      const { me } = requireActor()
      if (!can(me.permissions, 'attribute', 'manage')) return []
      return attributes.map(toCatalogAttribute)
    },

    async createAttribute(input: CreateAttributeInput): Promise<ActionResult> {
      await wait()
      const { me } = requireActor()
      if (!can(me.permissions, 'attribute', 'manage')) return reject("You can't manage metrics or custom fields.")
      if (!KEY_PATTERN.test(input.key)) {
        return reject('Key must start with a lowercase letter and use only a-z, 0-9 and _')
      }
      if (attributes.some((a) => a.key === input.key)) return reject('An attribute with that key already exists.')
      const problem = definitionProblem(input)
      if (problem) return reject(problem)
      if (input.functionKey !== null && !functions.some((f) => f.key === input.functionKey)) {
        return reject('Choose a valid function.')
      }
      attributes.push(
        copyAttribute({ ...input, label: input.label.trim(), id: `attr-new-${nextId++}`, active: true, recorded: [] }),
      )
      return { status: 'ok' }
    },

    async updateAttribute(attributeId: string, changes: UpdateAttributeInput): Promise<ActionResult> {
      await wait()
      const { me } = requireActor()
      if (!can(me.permissions, 'attribute', 'manage')) return reject("You can't manage metrics or custom fields.")
      const attribute = attributes.find((a) => a.id === attributeId)
      if (!attribute) return reject('That attribute no longer exists.')

      const next = copyAttribute({ ...attribute, ...changes, label: (changes.label ?? attribute.label).trim() })
      const problem = definitionProblem(next)
      if (problem) return reject(problem)
      if (next.functionKey !== attribute.functionKey && next.functionKey !== null) {
        if (!functions.some((f) => f.key === next.functionKey)) return reject('Choose a valid function.')
      }
      if (next.dataType !== attribute.dataType && attribute.recorded.length > 0) {
        return reject(
          "The data type can't change once values have been recorded. Retire this attribute and add a new one instead.",
        )
      }
      const kept = new Set(next.enumOptions ?? [])
      const stillUsed = (attribute.enumOptions ?? []).filter(
        (option) => !kept.has(option) && attribute.recorded.includes(option),
      )
      if (stillUsed.length) return reject(`Still in use, can't remove: ${stillUsed.sort().join(', ')}`)

      Object.assign(attribute, next)
      return { status: 'ok' }
    },
  }
}
