/**
 * Mock database seed. Fictional people, real structure.
 *
 * - POSITIONS and FUNCTIONS are copied from spec §2, including levels and ranks.
 * - PERMISSION_MATRIX is ILLUSTRATIVE. The real seed is a spec TODO (§3.3): it must be
 *   reviewed with the Tech Lead and at least one LCP. Do not treat these rows as policy.
 * - Names and emails are invented. Dates are relative to "today" so the demo never
 *   expires: current memberships always cover today.
 */
import dayjs from 'dayjs'

import type {
  Action,
  CustomField,
  FunctionDef,
  IsoDate,
  Lc,
  Position,
  Scope,
  Team,
  Term,
} from '../types'

// ---------------------------------------------------------------------------
// Lookups from the spec
// ---------------------------------------------------------------------------

/** Spec §2 "Positions". A higher rank is a higher position. */
export const POSITIONS: Position[] = [
  { key: 'member', label: 'Member', level: 'lc', rank: 1, canAddSameRank: false, presidential: false, homeChartScope: 'team' },
  { key: 'team_leader', label: 'Team Leader (TL)', level: 'lc', rank: 2, canAddSameRank: false, presidential: false, homeChartScope: 'team' },
  { key: 'lcvp', label: 'LC Vice President (LCVP)', level: 'lc', rank: 3, canAddSameRank: false, presidential: false, homeChartScope: 'function' },
  { key: 'lcp', label: 'LC President (LCP)', level: 'lc', rank: 4, canAddSameRank: true, presidential: true, homeChartScope: 'function' },
  { key: 'mcd', label: 'MC Director (MCD)', level: 'mc', rank: 5, canAddSameRank: false, presidential: false, homeChartScope: 'all' },
  { key: 'mcvp', label: 'MC Vice President (MCVP)', level: 'mc', rank: 6, canAddSameRank: false, presidential: false, homeChartScope: 'all' },
  { key: 'mcp', label: 'MC President (MCP)', level: 'mc', rank: 7, canAddSameRank: true, presidential: true, homeChartScope: 'all' },
]

/** Spec §2 "Functions". A flat list: functions have no rank. */
export const FUNCTIONS: FunctionDef[] = [
  { key: 'president', label: 'President', active: true, presidentOnly: true },
  { key: 'tm', label: 'Talent Management (TM)', active: true, presidentOnly: false },
  { key: 'fng', label: 'Finance and Governance (FnG)', active: true, presidentOnly: false },
  { key: 'od', label: 'Organisational Development (OD)', active: true, presidentOnly: false },
  { key: 'ogx', label: 'Outgoing Exchange (oGX)', active: true, presidentOnly: false },
  { key: 'ogv', label: 'Outgoing Global Volunteer (oGV)', active: true, presidentOnly: false },
  { key: 'ogta', label: 'Outgoing Global Talent (oGTa)', active: true, presidentOnly: false },
  { key: 'ogte', label: 'Outgoing Global Teacher (oGTe)', active: true, presidentOnly: false },
  { key: 'bnm', label: 'Brand and Marketing (BnM)', active: true, presidentOnly: false },
  { key: 'mac', label: 'Marketing and Communications (MaC)', active: true, presidentOnly: false },
  { key: 'events', label: 'Events', active: true, presidentOnly: false },
  { key: 'pm', label: 'Physical Marketing (PM)', active: true, presidentOnly: false },
  { key: 'dm', label: 'Digital Marketing (DM)', active: true, presidentOnly: false },
  { key: 'bd', label: 'Business Development (BD)', active: true, presidentOnly: false },
  { key: 'er', label: 'External Relations (ER)', active: true, presidentOnly: false },
]

export const LCS: Lc[] = [
  { id: 'lc-usyd', name: 'USYD', type: 'lc' },
  { id: 'lc-mu', name: 'MU', type: 'lc' },
  { id: 'lc-unsw', name: 'UNSW', type: 'lc' },
  { id: 'lc-mc', name: 'MC', type: 'mc' },
]

export const TEAMS: Team[] = [
  { id: 'team-usyd-ogv-a', name: 'oGV Team A', lcId: 'lc-usyd', functionKey: 'ogv' },
  { id: 'team-usyd-ogv-b', name: 'oGV Team B', lcId: 'lc-usyd', functionKey: 'ogv' },
  { id: 'team-usyd-bnm-a', name: 'BnM Team A', lcId: 'lc-usyd', functionKey: 'bnm' },
  { id: 'team-usyd-ogta-a', name: 'oGTa Team A', lcId: 'lc-usyd', functionKey: 'ogta' },
  { id: 'team-usyd-tm-a', name: 'TM Team A', lcId: 'lc-usyd', functionKey: 'tm' },
  { id: 'team-mu-ogv-a', name: 'oGV Team A', lcId: 'lc-mu', functionKey: 'ogv' },
  { id: 'team-mu-bnm-a', name: 'BnM Team A', lcId: 'lc-mu', functionKey: 'bnm' },
  { id: 'team-unsw-ogv-a', name: 'oGV Team A', lcId: 'lc-unsw', functionKey: 'ogv' },
]

/** Terms are named periods (§5.3). Built around today so one is always current. */
export function buildTerms(today: IsoDate): Term[] {
  const t = dayjs(today)
  const fmt = (d: dayjs.Dayjs) => d.format('YYYY-MM-DD')
  const yy = (d: dayjs.Dayjs) => d.format('YY')
  const y = t.startOf('year') // Jan-Jul is term .1, Aug-Dec is term .2
  const thisYearFirst: Term = { id: 'term-1', name: `${yy(y)}.1`, startDate: fmt(y), endDate: fmt(y.month(6).endOf('month')) }
  const thisYearSecond: Term = { id: 'term-2', name: `${yy(y)}.2`, startDate: fmt(y.month(7).startOf('month')), endDate: fmt(y.endOf('year')) }
  const next = y.add(1, 'year')
  const nextFirst: Term = { id: 'term-3', name: `${yy(next)}.1`, startDate: fmt(next), endDate: fmt(next.month(6).endOf('month')) }
  return [thisYearFirst, thisYearSecond, nextFirst]
}

// ---------------------------------------------------------------------------
// Illustrative permission matrix (position x resource x action -> max scope)
// ---------------------------------------------------------------------------

export interface MatrixRow {
  positionKey: string
  resource: string
  action: Action
  scope: Scope
}

const row = (positionKey: string, resource: string, action: Action, scope: Scope): MatrixRow => ({
  positionKey,
  resource,
  action,
  scope,
})

const mc = (positionKey: string): MatrixRow[] => [
  row(positionKey, 'member_record', 'view', 'all'),
  row(positionKey, 'member_record', 'edit', 'own'),
  row(positionKey, 'membership', 'view', 'all'),
  row(positionKey, 'membership', 'create', 'all'),
  row(positionKey, 'membership', 'edit', 'all'),
  row(positionKey, 'team_member', 'edit', 'all'),
  row(positionKey, 'kpi_record', 'view', 'all'),
  row(positionKey, 'kpi_record', 'create', 'all'),
  row(positionKey, 'kpi_record', 'edit', 'all'),
  row(positionKey, 'analytics_report', 'view', 'all'),
  row(positionKey, 'analytics_report', 'export', 'all'),
  row(positionKey, 'function', 'manage', 'all'), // spec §2A.8: every MC position
]

export const PERMISSION_MATRIX: MatrixRow[] = [
  // Member: their own record and own tracking. No Membership summary.
  row('member', 'member_record', 'view', 'own'),
  row('member', 'member_record', 'edit', 'own'),
  row('member', 'kpi_record', 'view', 'own'),
  row('member', 'kpi_record', 'create', 'own'),
  // Team Leader: their team. May add and extend, but NOT move people between teams.
  row('team_leader', 'member_record', 'view', 'own'),
  row('team_leader', 'member_record', 'edit', 'own'),
  row('team_leader', 'membership', 'view', 'team'),
  row('team_leader', 'membership', 'create', 'team'),
  row('team_leader', 'membership', 'edit', 'team'),
  row('team_leader', 'kpi_record', 'view', 'team'),
  row('team_leader', 'kpi_record', 'create', 'team'),
  row('team_leader', 'kpi_record', 'edit', 'team'),
  row('team_leader', 'analytics_report', 'view', 'function'),
  // LC Vice President: read the whole LC, write their own function, add to any function.
  row('lcvp', 'member_record', 'view', 'own'),
  row('lcvp', 'member_record', 'edit', 'own'),
  row('lcvp', 'membership', 'view', 'lc'),
  row('lcvp', 'membership', 'create', 'lc'),
  row('lcvp', 'membership', 'edit', 'function'),
  row('lcvp', 'team_member', 'edit', 'function'),
  row('lcvp', 'kpi_record', 'view', 'lc'),
  row('lcvp', 'kpi_record', 'create', 'function'),
  row('lcvp', 'kpi_record', 'edit', 'function'),
  row('lcvp', 'analytics_report', 'view', 'function'),
  // LC President: everything in their LC.
  row('lcp', 'member_record', 'view', 'own'),
  row('lcp', 'member_record', 'edit', 'own'),
  row('lcp', 'membership', 'view', 'lc'),
  row('lcp', 'membership', 'create', 'lc'),
  row('lcp', 'membership', 'edit', 'lc'),
  row('lcp', 'team_member', 'edit', 'lc'),
  row('lcp', 'kpi_record', 'view', 'lc'),
  row('lcp', 'kpi_record', 'create', 'lc'),
  row('lcp', 'kpi_record', 'edit', 'lc'),
  row('lcp', 'analytics_report', 'view', 'lc'),
  row('lcp', 'analytics_report', 'export', 'lc'),
  ...mc('mcd'),
  ...mc('mcvp'),
  ...mc('mcp'),
]

// ---------------------------------------------------------------------------
// People and memberships
// ---------------------------------------------------------------------------

export interface DbPerson {
  id: string
  firstName: string
  lastName: string
  email: string
  customFields: Record<string, string | number | boolean | null>
}

export interface DbMembership {
  id: string
  personId: string
  lcId: string
  positionKey: string
  functionKey: string | null
  termId: string
  startDate: IsoDate
  endDate: IsoDate
  /** Current team (the mock keeps one current `team_member` row per membership). */
  teamId: string | null
}

export interface MockDb {
  people: DbPerson[]
  memberships: DbMembership[]
}

/** Persona keys: dev-only shortcuts to sign in as a given role (see `api/index.ts`). */
export type PersonaKey = 'lcvp' | 'lcp' | 'tl' | 'member' | 'mcvp' | 'unallocated'

/** Persona -> person id. The default persona (LCVP) shows every action. */
export const PERSONAS: Record<PersonaKey, string> = {
  lcvp: 'p-jordan',
  lcp: 'p-morgan',
  tl: 'p-ava',
  member: 'p-sam',
  mcvp: 'p-riley',
  unallocated: 'p-casey',
}

/**
 * Person-level custom field catalog (§4.2, `attribute.applies_to = 'person'`). EMPTY on
 * purpose: the real catalog is not decided yet, so Profile shows no "About you" box.
 * Adding a row here (or passing `customFieldDefs` to `createMockApi`) makes the box appear.
 */
export const CUSTOM_FIELD_DEFS: Omit<CustomField, 'value'>[] = []

export function buildSeed(today: IsoDate): MockDb {
  const t = dayjs(today)
  const terms = buildTerms(today)
  const current = terms.find((x) => x.startDate <= today && x.endDate >= today) ?? terms[1]
  const previous = terms[Math.max(0, terms.indexOf(current) - 1)]

  const people: DbPerson[] = []
  const memberships: DbMembership[] = []
  let m = 0
  // Everyone is a numbered placeholder ("Member 1", "Member 2", ...), assigned in creation
  // order. The one exception is the default demo person, who is passed an explicit name.
  let memberNumber = 0
  const person = (id: string, override?: { firstName: string; lastName: string; email: string }) => {
    if (!override) memberNumber += 1
    people.push({
      id,
      firstName: override?.firstName ?? 'Member',
      lastName: override?.lastName ?? String(memberNumber),
      email: override?.email ?? `${id.replace(/^p-/, '')}@aiesec.example`,
      customFields: {},
    })
  }
  const membership = (
    personId: string,
    lcId: string,
    positionKey: string,
    functionKey: string | null,
    teamId: string | null,
    window: { start: IsoDate; end: IsoDate; termId: string } = { start: current.startDate, end: current.endDate, termId: current.id },
  ) => {
    m += 1
    memberships.push({
      id: `m-${m}`,
      personId,
      lcId,
      positionKey,
      functionKey,
      termId: window.termId,
      startDate: window.start,
      endDate: window.end,
      teamId,
    })
  }
  const previousWindow = { start: previous.startDate, end: previous.endDate, termId: previous.id }

  // --- Named personas (see PERSONAS) ---------------------------------------
  person('p-jordan', { firstName: 'temp_oGV', lastName: '', email: 'temp_ogv@aiesec.example' })
  membership('p-jordan', 'lc-usyd', 'lcvp', 'ogv', null)
  membership('p-jordan', 'lc-usyd', 'team_leader', 'ogv', 'team-usyd-ogv-a', previousWindow) // past

  person('p-morgan')
  membership('p-morgan', 'lc-usyd', 'lcp', 'president', null)

  person('p-taylor') // president-elect: overlaps early, may be added by Morgan (§2)
  membership('p-taylor', 'lc-usyd', 'lcp', 'president', null, {
    start: t.subtract(3, 'day').format('YYYY-MM-DD'),
    end: t.add(300, 'day').format('YYYY-MM-DD'),
    termId: current.id,
  })

  person('p-ava')
  membership('p-ava', 'lc-usyd', 'team_leader', 'ogv', 'team-usyd-ogv-a')
  membership('p-ava', 'lc-usyd', 'member', 'bnm', 'team-usyd-bnm-a') // TL in oGV, Member in BnM

  person('p-sam')
  membership('p-sam', 'lc-usyd', 'member', 'ogv', 'team-usyd-ogv-a')

  person('p-riley')
  membership('p-riley', 'lc-mc', 'mcvp', 'ogv', null)

  person('p-casey') // term ended: signs in, sees the not-allocated page
  membership('p-casey', 'lc-usyd', 'member', 'tm', 'team-usyd-tm-a', previousWindow)

  person('p-priya')
  membership('p-priya', 'lc-usyd', 'team_leader', 'ogta', 'team-usyd-ogta-a')
  membership('p-priya', 'lc-usyd', 'member', 'bnm', 'team-usyd-bnm-a')

  // --- Other exec and MC ---------------------------------------------------
  person('p-lcvp-bnm')
  membership('p-lcvp-bnm', 'lc-usyd', 'lcvp', 'bnm', null)
  person('p-lcvp-ogta')
  membership('p-lcvp-ogta', 'lc-usyd', 'lcvp', 'ogta', null)
  person('p-mcp')
  membership('p-mcp', 'lc-mc', 'mcp', 'president', null)
  person('p-mcd')
  membership('p-mcd', 'lc-mc', 'mcd', 'tm', null)

  // --- Generated members so the table paginates ---------------------------
  const spread: { lcId: string; fn: string; team: string | null; count: number; leader: boolean }[] = [
    { lcId: 'lc-usyd', fn: 'ogv', team: 'team-usyd-ogv-a', count: 5, leader: false },
    { lcId: 'lc-usyd', fn: 'ogv', team: 'team-usyd-ogv-b', count: 6, leader: true },
    { lcId: 'lc-usyd', fn: 'bnm', team: 'team-usyd-bnm-a', count: 5, leader: true },
    { lcId: 'lc-usyd', fn: 'ogta', team: 'team-usyd-ogta-a', count: 4, leader: false },
    { lcId: 'lc-usyd', fn: 'tm', team: 'team-usyd-tm-a', count: 4, leader: true },
    { lcId: 'lc-mu', fn: 'ogv', team: 'team-mu-ogv-a', count: 6, leader: true },
    { lcId: 'lc-mu', fn: 'bnm', team: 'team-mu-bnm-a', count: 4, leader: true },
    { lcId: 'lc-unsw', fn: 'ogv', team: 'team-unsw-ogv-a', count: 5, leader: true },
  ]
  let n = 0
  for (const group of spread) {
    for (let i = 0; i < group.count; i += 1) {
      const id = `p-gen-${n}`
      person(id)
      membership(id, group.lcId, group.leader && i === 0 ? 'team_leader' : 'member', group.fn, group.team)
      n += 1
    }
  }
  // An MU president, so the MC has someone to add to other LCs.
  person('p-mu-lcp')
  membership('p-mu-lcp', 'lc-mu', 'lcp', 'president', null)

  return { people, memberships }
}
