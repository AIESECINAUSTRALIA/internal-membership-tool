/**
 * Tests for permission gating and the hierarchy rule (spec §3.4).
 *
 * They run against the mock API's seed data, so they double as a check that the seed
 * matches the spec's positions and ranks. Everything is driven by a fixed "today".
 */
import { beforeEach, describe, expect, it } from 'vitest'

import { createMockApi } from '../api/mock/mockApi'
import type { PersonaKey } from '../api/mock/seed'
import type { MemberSummaryRow, Me, Permission, Scope } from '../api/types'
import {
  actingMembership,
  actingMembershipCandidates,
  actorFromMe,
  addableFunctions,
  addableLcs,
  addablePositions,
  addableTeams,
  availableDataScopes,
  can,
  canTrackOthers,
  distinctFunctions,
  fixedTeam,
  hasActiveMembership,
  hasMinScope,
  homeChartScope,
  narrowToMembership,
  rowActions,
  trackableRoleIds,
  visibleNavItems,
  widestScope,
} from '../auth/permissions'
import { NAV_ITEMS } from '../navigation/navConfig'

const TODAY = '2026-09-22'

async function signInAs(persona: PersonaKey) {
  const api = createMockApi({ persona, latencyMs: 0, today: () => TODAY })
  await api.signIn()
  const me = (await api.getMe()) as Me
  const ref = await api.getReferenceData()
  const { rows } = await api.listMembers({ search: '', sort: null, page: 0, pageSize: 500, lcId: null })
  return { api, me, actor: actorFromMe(me, TODAY), ref, rows }
}

// People are looked up by their stable id, not their (placeholder) name.
const rowFor = (rows: MemberSummaryRow[], personId: string) => {
  const row = rows.find((r) => r.personId === personId)
  if (!row) throw new Error(`No row for ${personId}`)
  return row
}

beforeEach(() => sessionStorage.clear())

describe('permission resolution', () => {
  const grants: Permission[] = [
    { resource: 'membership', action: 'view', scope: 'team' },
    { resource: 'membership', action: 'view', scope: 'lc' },
    { resource: 'kpi_record', action: 'view', scope: 'own' },
  ]

  it('takes the widest scope for a resource and action', () => {
    expect(widestScope(grants, 'membership', 'view')).toBe('lc')
  })

  it('denies by default when nothing matches', () => {
    expect(widestScope(grants, 'membership', 'create')).toBeNull()
    expect(can(grants, 'audit_log', 'view')).toBe(false)
    expect(can([], 'membership', 'view')).toBe(false)
  })
})

describe('hasMinScope', () => {
  it('is true when the widest grant is exactly the minimum', () => {
    expect(hasMinScope([{ resource: 'analytics_report', action: 'view', scope: 'team' }], 'analytics_report', 'view', 'team')).toBe(true)
  })

  it('is true when the widest grant is wider than the minimum', () => {
    expect(hasMinScope([{ resource: 'analytics_report', action: 'view', scope: 'all' }], 'analytics_report', 'view', 'team')).toBe(true)
  })

  it('is false when the widest grant is narrower than the minimum', () => {
    expect(hasMinScope([{ resource: 'analytics_report', action: 'view', scope: 'own' }], 'analytics_report', 'view', 'team')).toBe(false)
  })

  it('is false when there is no grant at all', () => {
    expect(hasMinScope([], 'analytics_report', 'view', 'team')).toBe(false)
  })

  it("with minScope 'own', matches can() exactly", () => {
    const grants: Permission[] = [{ resource: 'analytics_report', action: 'view', scope: 'own' }]
    expect(hasMinScope(grants, 'analytics_report', 'view', 'own')).toBe(can(grants, 'analytics_report', 'view'))
    expect(hasMinScope(grants, 'analytics_report', 'view', 'own')).toBe(true)
  })
})

describe('allocation', () => {
  it('treats a person whose term has ended as not allocated', async () => {
    const { me } = await signInAs('unallocated')
    expect(me.memberships.length).toBeGreaterThan(0) // history exists...
    expect(hasActiveMembership(me, TODAY)).toBe(false) // ...but none is active
  })

  it('treats a person with an active membership as allocated', async () => {
    const { me } = await signInAs('lcvp')
    expect(hasActiveMembership(me, TODAY)).toBe(true)
  })
})

describe('navigation gating', () => {
  const keys = (me: Me, includeUnbuilt: boolean) =>
    visibleNavItems(NAV_ITEMS, me.permissions, { includeUnbuilt }).map((i) => i.key)

  it.each<[PersonaKey, string[]]>([
    ['member', ['home', 'tracking', 'settings']], // no Membership, no Data
    ['tl', ['home', 'membership', 'tracking', 'data', 'settings']],
    ['lcvp', ['home', 'membership', 'tracking', 'data', 'settings']],
    ['lcp', ['home', 'membership', 'tracking', 'data', 'settings']],
    ['mcvp', ['home', 'membership', 'tracking', 'data', 'settings']],
  ])('%s sees the right pages once they are all built', async (persona, expected) => {
    const { me } = await signInAs(persona)
    expect(keys(me, true)).toEqual(expected)
  })

  it('hides an item whose grant does not reach its minimum scope', () => {
    const items = [{ key: 'a', built: true, requires: { resource: 'x', action: 'view' as const, minScope: 'team' as const } }]
    expect(visibleNavItems(items, [{ resource: 'x', action: 'view', scope: 'own' }]).map((i) => i.key)).toEqual([])
    expect(visibleNavItems(items, [{ resource: 'x', action: 'view', scope: 'team' }]).map((i) => i.key)).toEqual(['a'])
  })

  it('shows every page a person may open, now that all five exist', async () => {
    expect(keys((await signInAs('member')).me, false)).toEqual(['home', 'tracking', 'settings'])
    expect(keys((await signInAs('lcvp')).me, false)).toEqual(['home', 'membership', 'tracking', 'data', 'settings'])
  })

  it('hides an item whose page is not built yet, unless asked to include it', () => {
    const items = [
      { key: 'a', built: true },
      { key: 'b', built: false },
    ]
    expect(visibleNavItems(items, []).map((i) => i.key)).toEqual(['a'])
    expect(visibleNavItems(items, [], { includeUnbuilt: true }).map((i) => i.key)).toEqual(['a', 'b'])
  })
})

describe('which actions show for which position (hierarchy rule, §3.4)', () => {
  it('Member has no Membership summary at all', async () => {
    const { rows } = await signInAs('member')
    expect(rows).toHaveLength(0)
  })

  it('Team Leader can extend a member of their team, but can NOT move them', async () => {
    const { me, actor, rows } = await signInAs('tl')
    const sam = rowFor(rows, 'p-sam') // Member in the Team Leader's oGV team
    const actions = rowActions(actor, me.permissions, sam)
    expect(actions.extendRoleIds).toHaveLength(1)
    expect(actions.moveRoleIds).toHaveLength(0) // Move to team: LCVP and above only
  })

  it('Team Leader only sees their own team, so nobody outside it is offered', async () => {
    const { rows } = await signInAs('tl')
    // The Team Leader leads oGV Team A and is a Member of BnM Team A. Nobody from oGV Team B or other LCs.
    expect(rows.every((r) => r.lc.name === 'USYD')).toBe(true)
    expect(rows.some((r) => r.personId === 'p-jordan')).toBe(false)
  })

  it('nobody can act on their own membership, so nobody extends their own term', async () => {
    for (const persona of ['tl', 'lcvp', 'lcp', 'mcvp'] as PersonaKey[]) {
      const { me, actor, rows } = await signInAs(persona)
      const own = rows.find((r) => r.personId === me.person.id)
      if (!own) continue
      expect(rowActions(actor, me.permissions, own)).toEqual({ extendRoleIds: [], moveRoleIds: [] })
    }
  })

  it('LC Vice President can extend and move people below them in their own function', async () => {
    const { me, actor, rows } = await signInAs('lcvp') // the default LCVP, oGV
    const sam = rowFor(rows, 'p-sam') // Member, oGV
    expect(rowActions(actor, me.permissions, sam).extendRoleIds).toHaveLength(1)
    expect(rowActions(actor, me.permissions, sam).moveRoleIds).toHaveLength(1)
    const ava = rowFor(rows, 'p-ava') // TL, oGV (and Member, BnM)
    const avaActions = rowActions(actor, me.permissions, ava)
    expect(avaActions.extendRoleIds).toHaveLength(1) // only the oGV membership, not BnM
    expect(avaActions.moveRoleIds).toHaveLength(1)
  })

  it('LC Vice President has read-only access to other functions and cannot touch equals or above', async () => {
    const { me, actor, rows } = await signInAs('lcvp') // the default LCVP, oGV
    const priya = rowFor(rows, 'p-priya') // TL oGTa, Member BnM: other functions
    expect(rowActions(actor, me.permissions, priya)).toEqual({ extendRoleIds: [], moveRoleIds: [] })
    const dana = rowFor(rows, 'p-lcvp-bnm') // LCVP BnM: equal rank
    expect(rowActions(actor, me.permissions, dana)).toEqual({ extendRoleIds: [], moveRoleIds: [] })
    const morgan = rowFor(rows, 'p-morgan') // LCP: higher
    expect(rowActions(actor, me.permissions, morgan)).toEqual({ extendRoleIds: [], moveRoleIds: [] })
  })

  it('LC President acts on the whole LC below them, but not on another LCP', async () => {
    const { me, actor, rows } = await signInAs('lcp') // the LCP
    expect(rowActions(actor, me.permissions, rowFor(rows, 'p-priya')).moveRoleIds).toHaveLength(2)
    expect(rowActions(actor, me.permissions, rowFor(rows, 'p-lcvp-bnm')).extendRoleIds).toHaveLength(1)
    // The president exception is for ADDING only: no extend or move for a peer LCP.
    const taylor = rowFor(rows, 'p-taylor')
    expect(rowActions(actor, me.permissions, taylor)).toEqual({ extendRoleIds: [], moveRoleIds: [] })
  })

  it('MC positions act across LCs and only on positions below their own', async () => {
    const { me, actor, rows } = await signInAs('mcvp') // MCVP, rank 6
    expect(new Set(rows.map((r) => r.lc.name)).size).toBeGreaterThan(1) // sees every LC
    expect(rowActions(actor, me.permissions, rowFor(rows, 'p-mu-lcp')).extendRoleIds).toHaveLength(1) // MU LCP
    expect(rowActions(actor, me.permissions, rowFor(rows, 'p-mcd')).extendRoleIds).toHaveLength(1) // MCD below
    expect(rowActions(actor, me.permissions, rowFor(rows, 'p-mcp'))).toEqual({
      extendRoleIds: [],
      moveRoleIds: [],
    }) // MCP above
  })
})

describe('Add member: what each position may offer (§3.4, §3.6)', () => {
  const keys = <T extends { key: string }>(list: T[]) => list.map((x) => x.key)

  it('a Member cannot add anyone', async () => {
    const { me, actor, ref } = await signInAs('member')
    expect(addableLcs(actor, me.permissions, ref.lcs)).toEqual([])
  })

  it('a Team Leader is fixed to their own LC, team and function, and can add Members only', async () => {
    const { me, actor, ref } = await signInAs('tl')
    const lcs = addableLcs(actor, me.permissions, ref.lcs)
    expect(lcs.map((l) => l.name)).toEqual(['USYD'])
    expect(keys(addablePositions(actor, me.permissions, ref.positions, lcs[0]))).toEqual(['member'])
    expect(fixedTeam(actor, me.permissions)?.team.name).toBe('oGV Team A')
    const member = ref.positions.find((p) => p.key === 'member')!
    expect(keys(addableFunctions(actor, me.permissions, ref.functions, member))).toEqual(['ogv'])
  })

  it('an LC Vice President adds Members and Team Leaders in any function of their LC', async () => {
    const { me, actor, ref } = await signInAs('lcvp')
    const lcs = addableLcs(actor, me.permissions, ref.lcs)
    expect(lcs.map((l) => l.name)).toEqual(['USYD'])
    expect(keys(addablePositions(actor, me.permissions, ref.positions, lcs[0]))).toEqual(['member', 'team_leader'])
    const tl = ref.positions.find((p) => p.key === 'team_leader')!
    const fns = addableFunctions(actor, me.permissions, ref.functions, tl)
    expect(fns.length).toBe(14) // every function except President
    expect(keys(fns)).not.toContain('president')
  })

  it('an LC President may add another LC President, in their own LC only', async () => {
    const { me, actor, ref } = await signInAs('lcp')
    const lcs = addableLcs(actor, me.permissions, ref.lcs)
    expect(lcs.map((l) => l.name)).toEqual(['USYD']) // not MU, UNSW or the MC
    expect(keys(addablePositions(actor, me.permissions, ref.positions, lcs[0]))).toEqual([
      'member',
      'team_leader',
      'lcvp',
      'lcp', // president exception
    ])
    const lcp = ref.positions.find((p) => p.key === 'lcp')!
    expect(keys(addableFunctions(actor, me.permissions, ref.functions, lcp))).toEqual(['president'])
  })

  it('an MC Vice President adds LC-level positions in any LC, and only the MC Director in the MC', async () => {
    const { me, actor, ref } = await signInAs('mcvp')
    const mc = ref.lcs.find((l) => l.type === 'mc')!
    const usyd = ref.lcs.find((l) => l.name === 'USYD')!
    expect(addableLcs(actor, me.permissions, ref.lcs)).toHaveLength(4) // every LC and the MC
    expect(keys(addablePositions(actor, me.permissions, ref.positions, usyd))).toEqual(['member', 'team_leader', 'lcvp', 'lcp'])
    // §2: the MCVP can add the MCD, and nobody at or above the MCVP.
    expect(keys(addablePositions(actor, me.permissions, ref.positions, mc))).toEqual(['mcd'])
  })

  it('never offers a position whose level does not match the LC type (§3.6)', async () => {
    const { me, actor, ref } = await signInAs('mcvp')
    for (const lc of addableLcs(actor, me.permissions, ref.lcs)) {
      for (const p of addablePositions(actor, me.permissions, ref.positions, lc)) {
        expect(p.level).toBe(lc.type)
      }
    }
  })

  it('an LC Vice President can pick any team in their own LC + function, unlike a fixed Team Leader', async () => {
    const { me, actor, ref } = await signInAs('lcvp')
    const usyd = ref.lcs.find((l) => l.name === 'USYD')!
    expect(addableTeams(actor, me.permissions, ref.teams, usyd, 'ogv').map((t) => t.name)).toEqual([
      'oGV Team A',
      'oGV Team B',
    ])
  })

  it('an MC Vice President can pick a team in ANY LC, not just their own', async () => {
    const { me, actor, ref } = await signInAs('mcvp')
    const mu = ref.lcs.find((l) => l.name === 'MU')!
    expect(addableTeams(actor, me.permissions, ref.teams, mu, 'ogv').map((t) => t.name)).toEqual(['oGV Team A'])
  })

  it('a Member (no create grant at all) is offered no teams', async () => {
    const { me, actor, ref } = await signInAs('member')
    const usyd = ref.lcs.find((l) => l.name === 'USYD')!
    expect(addableTeams(actor, me.permissions, ref.teams, usyd, 'ogv')).toEqual([])
  })
})

describe('Add member: choosing which of the actor\'s own memberships to act as (§3.4)', () => {
  it('offers just the one candidate for a single-membership actor, matching actingMembership', async () => {
    const { actor } = await signInAs('tl')
    const candidates = actingMembershipCandidates(actor)
    expect(candidates).toEqual([actingMembership(actor)])
  })

  it('offers both memberships for a Team Leader of two teams, with the first matching actingMembership', async () => {
    const { actor } = await signInAs('dualTl')
    const candidates = actingMembershipCandidates(actor)
    expect(new Set(candidates.map((m) => m.team?.name))).toEqual(new Set(['oGV Team A', 'oGTa Team A']))
    expect(candidates[0]).toEqual(actingMembership(actor))
  })

  it('fixedTeam follows whichever membership the actor is narrowed to, not just the first', async () => {
    const { me, actor } = await signInAs('dualTl')
    const [first, second] = actingMembershipCandidates(actor)
    expect(fixedTeam(narrowToMembership(actor, first.id), me.permissions)?.team.name).toBe(first.team?.name)
    expect(fixedTeam(narrowToMembership(actor, second.id), me.permissions)?.team.name).toBe(second.team?.name)
  })
})

describe('Tracking (§2A.6): the function switcher and "Track someone"', () => {
  it("Team Leader Ava holds two functions, so both show in her switcher", async () => {
    const { actor } = await signInAs('tl') // signs in as p-ava: TL oGV, Member BnM
    const keys = distinctFunctions(actor).map((f) => f.key)
    expect(keys.sort()).toEqual(['bnm', 'ogv'])
  })

  it('a Member has no "Track someone", a Team Leader does (kpi_record.edit at team scope)', async () => {
    const { me: memberMe } = await signInAs('member')
    expect(canTrackOthers(memberMe.permissions)).toBe(false)
    const { me: tlMe } = await signInAs('tl')
    expect(canTrackOthers(tlMe.permissions)).toBe(true)
  })

  it('Team Leader can track their own team, but not themselves or another LC', async () => {
    const { me, actor, rows } = await signInAs('tl')
    expect(trackableRoleIds(actor, me.permissions, rowFor(rows, 'p-sam'))).toHaveLength(1) // their team
    expect(trackableRoleIds(actor, me.permissions, rowFor(rows, 'p-ava'))).toHaveLength(0) // themselves
  })

  it('LC Vice President can track their own function only, not other functions in the LC', async () => {
    const { me, actor, rows } = await signInAs('lcvp') // the default LCVP, oGV
    expect(trackableRoleIds(actor, me.permissions, rowFor(rows, 'p-sam'))).toHaveLength(1) // Member, oGV
    expect(trackableRoleIds(actor, me.permissions, rowFor(rows, 'p-priya'))).toHaveLength(0) // TL oGTa + Member BnM
  })
})

describe('Data page scope tabs (§2A.7, §6)', () => {
  it.each<[PersonaKey, Scope[]]>([
    ['member', []], // no analytics_report.view at all
    ['tl', ['team', 'function']],
    ['lcvp', ['team', 'function']],
    ['lcp', ['team', 'function', 'lc']],
    ['mcvp', ['team', 'function', 'lc', 'all']],
  ])('%s may see up to %s', async (persona, expected) => {
    const { me } = await signInAs(persona)
    expect(availableDataScopes(me.permissions)).toEqual(expected)
  })
})

describe('homepage chart follows the position', () => {
  it.each<[PersonaKey, string]>([
    ['member', 'team'],
    ['tl', 'team'],
    ['lcvp', 'function'],
    ['lcp', 'function'],
    ['mcvp', 'all'],
  ])('%s sees a %s chart', async (persona, scope) => {
    const { actor } = await signInAs(persona)
    expect(homeChartScope(actingMembership(actor))).toBe(scope)
  })
})
