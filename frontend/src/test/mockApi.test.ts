/**
 * The mock API stands in for the server, so it must enforce what the spec says the
 * server enforces. These tests pin those rules so the real backend can be checked
 * against the same expectations later.
 */
import { beforeEach, describe, expect, it } from 'vitest'

import { createMockApi } from '../api/mock/mockApi'
import type { PersonaKey } from '../api/mock/seed'
import type { AddMemberInput, MemberQuery } from '../api/types'

const TODAY = '2026-09-22'
const ALL: MemberQuery = { search: '', sort: null, page: 0, pageSize: 500, lcId: null }

async function apiAs(persona: PersonaKey) {
  const api = createMockApi({ persona, latencyMs: 0, today: () => TODAY })
  await api.signIn()
  return api
}

/** One person's row from the full list, by stable id (names are placeholders). */
async function rowOf(api: Awaited<ReturnType<typeof apiAs>>, personId: string) {
  const row = (await api.listMembers(ALL)).rows.find((r) => r.personId === personId)
  if (!row) throw new Error(`No row for ${personId}`)
  return row
}

const add = (overrides: Partial<AddMemberInput>): AddMemberInput => ({
  email: 'someone.new@aiesec.example',
  lcId: 'lc-usyd',
  positionKey: 'member',
  functionKey: 'ogv',
  // Starts today, so the new membership is CURRENT and appears in the member list (§2A.5).
  startDate: TODAY,
  endDate: '2026-12-31',
  ...overrides,
})

beforeEach(() => sessionStorage.clear())

describe('membership summary data', () => {
  it('never sends an email address (§2A.5)', async () => {
    const api = await apiAs('lcp')
    const { rows } = await api.listMembers(ALL)
    expect(rows.length).toBeGreaterThan(0)
    expect(JSON.stringify(rows)).not.toMatch(/@/)
  })

  it('isolates LCs in the query: an LC user cannot see other LCs, MC sees all (§2A.5)', async () => {
    const lc = (await (await apiAs('lcp')).listMembers(ALL)).rows
    expect(new Set(lc.map((r) => r.lc.name))).toEqual(new Set(['USYD']))
    const mc = (await (await apiAs('mcvp')).listMembers(ALL)).rows
    expect(new Set(mc.map((r) => r.lc.name)).size).toBeGreaterThan(2)
  })

  it('lists a person with several functions once, with every pair (§2A.5)', async () => {
    const { rows } = await (await apiAs('lcp')).listMembers(ALL)
    expect(rows.filter((r) => r.personId === 'p-priya')).toHaveLength(1) // once, not once per function
    expect(rows.find((r) => r.personId === 'p-priya')!.roles).toHaveLength(2)
  })

  it('searches, sorts and paginates in the query', async () => {
    const api = await apiAs('lcp')
    const page1 = await api.listMembers({ ...ALL, pageSize: 5, sort: { field: 'firstName', direction: 'asc' } })
    const page2 = await api.listMembers({ ...ALL, page: 1, pageSize: 5, sort: { field: 'firstName', direction: 'asc' } })
    expect(page1.rows).toHaveLength(5)
    expect(page1.total).toBeGreaterThan(5)
    expect(page1.rows[4].firstName.localeCompare(page2.rows[0].firstName)).toBeLessThanOrEqual(0)
    expect((await api.listMembers({ ...ALL, search: 'zzzz' })).total).toBe(0)
  })
})

describe('placeholder names in the mock data', () => {
  it('names the default LC Vice President temp_oGV and everyone else "Member N"', async () => {
    const api = await apiAs('lcvp')
    const me = (await api.getMe())!
    expect(me.person.firstName).toBe('temp_oGV')
    const { rows } = await (await apiAs('mcvp')).listMembers(ALL)
    const others = rows.filter((r) => r.personId !== 'p-jordan')
    expect(others.length).toBeGreaterThan(10)
    for (const r of others) expect(`${r.firstName} ${r.lastName}`).toMatch(/^Member \d+$/)
    // No two people share a name.
    expect(new Set(rows.map((r) => `${r.firstName} ${r.lastName}`)).size).toBe(rows.length)
  })

  it('sorts numbered names naturally: Member 2 before Member 10', async () => {
    const api = await apiAs('mcvp')
    const { rows } = await api.listMembers({ ...ALL, sort: { field: 'lastName', direction: 'asc' } })
    const numbers = rows.filter((r) => r.firstName === 'Member').map((r) => Number(r.lastName))
    expect(numbers).toEqual([...numbers].sort((a, b) => a - b))
  })
})

describe('adding a member on the server (§2A.5, §3.4, §3.6, §5.1)', () => {
  it('rejects a position above the adder: a Team Leader cannot add an LC Vice President', async () => {
    const result = await (await apiAs('tl')).addMember(add({ positionKey: 'lcvp' }))
    expect(result.status).toBe('rejected')
  })

  it('rejects a position whose level does not match the LC (§3.6)', async () => {
    const result = await (await apiAs('mcvp')).addMember(add({ lcId: 'lc-usyd', positionKey: 'mcd' }))
    expect(result.status).toBe('rejected')
  })

  it('asks for a name when nobody has the email, then creates the person', async () => {
    const api = await apiAs('lcvp')
    expect(await api.addMember(add({}))).toEqual({ status: 'needs_name' })
    expect(await api.addMember(add({ firstName: 'Nova', lastName: 'Zed' }))).toEqual({ status: 'created' })
    expect((await api.listMembers({ ...ALL, search: 'Nova Zed' })).total).toBe(1)
  })

  it('asks to confirm when the email exists, and only then attaches the membership', async () => {
    const api = await apiAs('lcvp')
    const request = add({ email: 'sam@aiesec.example', functionKey: 'bnm' })
    expect(await api.addMember(request)).toEqual({ status: 'confirm_existing' })
    expect(await api.addMember({ ...request, confirmedExisting: true })).toEqual({ status: 'created' })
    const sam = (await api.listMembers(ALL)).rows.filter((r) => r.personId === 'p-sam')
    expect(sam).toHaveLength(1) // still one person...
    expect(sam[0].roles).toHaveLength(2) // ...now with two functions, nothing ended
  })

  it('a transfer ends the old LC membership, so the person moves LC (§5.1)', async () => {
    const mcApi = await apiAs('mcvp')
    const request = add({ email: 'mu-lcp@aiesec.example', lcId: 'lc-usyd', positionKey: 'member', functionKey: 'ogv' })
    expect(await mcApi.addMember(request)).toEqual({ status: 'confirm_existing' })
    expect(await mcApi.addMember({ ...request, confirmedExisting: true })).toEqual({ status: 'created' })
    const moved = (await mcApi.listMembers(ALL)).rows.filter((r) => r.personId === 'p-mu-lcp')
    expect(moved).toHaveLength(1)
    expect(moved[0].lc.name).toBe('USYD') // only in the new LC now
  })

  it('blocks adding an MC member to an LC, with a message that does not say why (§3.6)', async () => {
    const api = await apiAs('lcp')
    const request = add({ email: 'mcd@aiesec.example' })
    await api.addMember(request) // confirm_existing
    const result = await api.addMember({ ...request, confirmedExisting: true })
    expect(result).toEqual({ status: 'rejected', message: "This person can't be added. Contact your MC." })
  })

  it('rejects an end date before the start date', async () => {
    const result = await (await apiAs('lcvp')).addMember(add({ startDate: '2026-12-31', endDate: '2026-09-23' }))
    expect(result.status).toBe('rejected')
  })
})

describe('extend term and move to team on the server', () => {
  it('nobody can extend their own term (§2A.5)', async () => {
    const api = await apiAs('lcvp')
    const me = (await api.getMe())!
    const own = me.memberships.find((m) => m.endDate! >= TODAY)!
    expect((await api.extendTerm(own.id, '2027-12-31')).status).toBe('rejected')
  })

  it('a Team Leader cannot move people between teams (LCVP and above only)', async () => {
    const tl = await apiAs('tl')
    const membershipId = (await rowOf(tl, 'p-sam')).roles[0].membershipId
    expect((await tl.moveToTeam(membershipId, 'team-usyd-ogv-b')).status).toBe('rejected')
  })

  it('an LC Vice President can extend and move someone below them in their function', async () => {
    const api = await apiAs('lcvp')
    const id = (await rowOf(api, 'p-sam')).roles[0].membershipId
    expect((await api.extendTerm(id, '2027-12-31')).status).toBe('ok')
    expect((await api.extendTerm(id, '2027-01-01')).status).toBe('rejected') // must move forward
    expect((await api.moveToTeam(id, 'team-usyd-ogv-b')).status).toBe('ok')
    expect((await api.getMembershipDetail(id)).currentTeam?.name).toBe('oGV Team B')
  })
})

describe('profile', () => {
  const pronouns = { key: 'pronouns', label: 'Pronouns', dataType: 'text' as const }

  it('has no person-level custom fields until a catalog exists', async () => {
    const me = (await (await apiAs('lcvp')).getMe())!
    expect(me.person.customFields).toEqual([])
  })

  it('only edits catalogued person-level fields; name and email stay locked (§2A.9)', async () => {
    const api = createMockApi({ persona: 'lcvp', latencyMs: 0, today: () => TODAY, customFieldDefs: [pronouns] })
    await api.signIn()
    const before = (await api.getMe())!
    const after = await api.updateMyCustomFields({ pronouns: 'they/them', firstName: 'Hacked', email: 'x@y.z' })
    expect(after.person.customFields.find((f) => f.key === 'pronouns')?.value).toBe('they/them')
    expect(after.person.firstName).toBe(before.person.firstName)
    expect(after.person.email).toBe(before.person.email)
  })
})
