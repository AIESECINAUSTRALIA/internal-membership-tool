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
  canExtendTerm,
  canMoveToTeam,
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
  Api,
  CustomField,
  CustomFieldValue,
  HomeChart,
  IsoDate,
  Lc,
  MemberQuery,
  MemberRole,
  MemberSummaryRow,
  Me,
  MembershipDetail,
  MembershipView,
  Page,
  Permission,
  Position,
  ReferenceData,
} from '../types'
import { shortLabel } from '../../lib/labels'
import {
  buildSeed,
  buildTerms,
  CUSTOM_FIELD_DEFS,
  FUNCTIONS,
  LCS,
  PERMISSION_MATRIX,
  PERSONAS,
  POSITIONS,
  TEAMS,
  type DbMembership,
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

export function createMockApi(options: MockApiOptions = {}): Api {
  const latencyMs = options.latencyMs ?? 150
  const today = options.today ?? (() => dayjs().format('YYYY-MM-DD'))
  const persona = options.persona ?? 'lcvp'
  const customFieldDefs = options.customFieldDefs ?? CUSTOM_FIELD_DEFS

  const db: MockDb = buildSeed(today())
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
  const position = (key: string): Position => {
    const found = POSITIONS.find((p) => p.key === key)
    if (!found) throw new Error(`Unknown position ${key}`)
    return found
  }
  const lcOf = (id: string): Lc => {
    const found = LCS.find((l) => l.id === id)
    if (!found) throw new Error(`Unknown LC ${id}`)
    return found
  }
  const functionRef = (key: string | null) => {
    if (key === null) return null
    const f = FUNCTIONS.find((x) => x.key === key)
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

  function buildMe(personId: string): Me {
    const p = personById(personId)
    if (!p) throw new Error(`Unknown person ${personId}`)
    const customFields: CustomField[] = customFieldDefs.map((def) => ({
      ...def,
      value: p.customFields[def.key] ?? null,
    }))
    return {
      person: { id: p.id, firstName: p.firstName, lastName: p.lastName, email: p.email, customFields },
      memberships: db.memberships
        .filter((m) => m.personId === personId)
        .map(toView)
        .sort((a, b) => (a.startDate < b.startDate ? 1 : -1)),
      permissions: resolvePermissions(personId),
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

    async updateMyCustomFields(values: Record<string, CustomFieldValue>) {
      await wait()
      const { me } = requireActor()
      const person = personById(me.person.id)!
      // Only catalogued person-level fields are editable (§2A.9). Anything else is ignored.
      for (const def of customFieldDefs) {
        if (def.key in values) person.customFields[def.key] = values[def.key]
      }
      return buildMe(person.id)
    },

    async getReferenceData(): Promise<ReferenceData> {
      await wait()
      const teams = TEAMS.map((t) => ({ ...t, leader: resolveTeamLeader(t.id) }))
      return { lcs: LCS, positions: POSITIONS, functions: FUNCTIONS, terms: buildTerms(today()), teams }
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
      const lc = LCS.find((l) => l.id === input.lcId)
      const pos = POSITIONS.find((p) => p.key === input.positionKey)
      if (!lc || !pos || !addableLcs(actor, me.permissions, LCS).some((l) => l.id === lc.id)) {
        return reject("You can't add people to that LC.")
      }
      if (!addablePositions(actor, me.permissions, POSITIONS, lc).some((p) => p.key === pos.key)) {
        return reject("You can't add that position.")
      }
      const fn = addableFunctions(actor, me.permissions, FUNCTIONS, pos).find((f) => f.key === input.functionKey)
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
      return { scope, title: `Monthly activity, ${where}`, period: 'monthly', points: [] }
    },
  }
}
