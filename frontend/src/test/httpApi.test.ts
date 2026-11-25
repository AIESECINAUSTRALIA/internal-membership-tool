/**
 * Tests for the real HTTP `Api` implementation (Ticket DEV-0043, Spec §2A.5).
 *
 * These tests stub `globalThis.fetch` so they exercise the httpApi's request-
 * building and response-normalisation logic (the shape translation between
 * backend and frontend types) without needing a live server.
 *
 * What these tests cover:
 *   - Each of the five membership-summary methods sends the right request.
 *   - Backend returns `{rows, total}` matching frontend Page type.
 *   - Numeric-string ids (lcId, teamId, termId) become integers; any other id is
 *     refused without calling the backend.
 *   - getReferenceData: LCs/terms/teams from the backend, positions/functions from
 *     the fallback.
 *   - Every request includes credentials for cookie-based authentication.
 *   - A 401 notifies the authentication provider; a 403 does not.
 *   - All four `AddMemberResult` statuses are returned correctly.
 *   - Read methods throw on an HTTP error; write methods (addMember, extendTerm,
 *     moveToTeam) never throw — failures come back as a plain-English rejection.
 *
 * What these tests do NOT cover (tested by the backend's own pytest suite):
 *   - The permission / hierarchy / LC-isolation logic (that's server-side).
 *   - The mock's behaviour (covered by mockApi.test.ts which stays unchanged).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createHttpApi } from '../api/http/httpApi'
import { createMockApi } from '../api/mock/mockApi'
import type { MemberQuery } from '../api/types'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const BASE = 'http://localhost:8000'

function makeApi() {
  return createHttpApi({
    baseUrl: BASE,
    // Zero-latency mock for the methods that aren't real yet (getMe, signIn, …).
    fallback: createMockApi({ latencyMs: 0 }),
  })
}

function headersOf(spy: ReturnType<typeof vi.spyOn>, call = 0): Record<string, string> {
  return (spy.mock.calls[call][1] as RequestInit).headers as Record<string, string>
}

/** A stub fetch response. */
function okResponse(body: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

function errorResponse(status: number, message: string) {
  return Promise.resolve(new Response(message, { status }))
}

const ALL: MemberQuery = { search: '', sort: null, page: 0, pageSize: 15, lcId: null }

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

let fetchSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  fetchSpy = vi.spyOn(globalThis, 'fetch')
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// listMembers
// ---------------------------------------------------------------------------

describe('listMembers', () => {
  it('POSTs to /api/v1/members/summary with the right body', async () => {
    const backendPage = { rows: [], total: 0 }
    fetchSpy.mockReturnValueOnce(okResponse(backendPage))

    await makeApi().listMembers(ALL)

    expect(fetchSpy).toHaveBeenCalledOnce()
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/api/v1/members/summary`)
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toMatchObject({
      search: '',
      page: 0,
      pageSize: 15,
      lcId: null,
    })
  })


  it('includes credentials on every request without bearer or actor headers', async () => {
    fetchSpy.mockImplementation(() => okResponse({ rows: [], total: 0 }))
    const api = makeApi()

    await api.listMembers(ALL)
    await api.listMembers(ALL)

    expect(fetchSpy).toHaveBeenCalledTimes(2)

    for (let i = 0; i < 2; i++) {
      const init = fetchSpy.mock.calls[i][1] as RequestInit

      expect(init.credentials).toBe('same-origin')
      expect(headersOf(fetchSpy, i).Authorization).toBeUndefined()
      expect(headersOf(fetchSpy, i)['X-Actor-Email']).toBeUndefined()
    }
  })

  it('notifies the authentication provider when the session is rejected', async () => {
    const onUnauthorized = vi.fn()
    const api = createHttpApi({
      baseUrl: BASE,
      fallback: createMockApi({ latencyMs: 0 }),
      onUnauthorized,
    })

    fetchSpy.mockReturnValueOnce(errorResponse(401, 'Unauthorized'))

    await expect(api.listMembers(ALL)).rejects.toThrow(/401/)
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  it('does not notify the authentication provider on a permission refusal', async () => {
    const onUnauthorized = vi.fn()
    const api = createHttpApi({
      baseUrl: BASE,
      fallback: createMockApi({ latencyMs: 0 }),
      onUnauthorized,
    })

    fetchSpy.mockReturnValueOnce(errorResponse(403, 'Forbidden'))

    await expect(api.listMembers(ALL)).rejects.toThrow(/403/)
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('uses a relative URL when baseUrl is empty', async () => {
    // '' = same origin: Firebase Hosting forwards /api/** to the backend.
    fetchSpy.mockReturnValueOnce(okResponse({ rows: [], total: 0 }))
    const api = createHttpApi({
      baseUrl: '',
      fallback: createMockApi({ latencyMs: 0 }),
    })
    await api.listMembers(ALL)
    expect(fetchSpy.mock.calls[0][0]).toBe('/api/v1/members/summary')
  })

  it('returns backend rows and total', async () => {
    const row = {
      personId: 'p-1',
      firstName: 'Ada',
      lastName: 'Lovelace',
      lc: { id: 'lc-1', name: 'USYD', type: 'lc' },
      roles: [],
    }
    fetchSpy.mockReturnValueOnce(okResponse({ rows: [row], total: 1 }))
    const result = await makeApi().listMembers(ALL)
    expect(result.rows).toHaveLength(1)
    expect(result.rows[0].firstName).toBe('Ada')
    expect(result.total).toBe(1)
  })

  it('passes sort object when provided', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ rows: [], total: 0 }))
    await makeApi().listMembers({
      ...ALL,
      sort: { field: 'firstName', direction: 'desc' },
    })
    const body = JSON.parse((fetchSpy.mock.calls[0][1] as RequestInit).body as string)
    expect(body.sort).toEqual({ field: 'firstName', direction: 'desc' })
  })

  it('throws when the server returns an error status', async () => {
    fetchSpy.mockReturnValueOnce(errorResponse(403, 'Forbidden'))
    await expect(makeApi().listMembers(ALL)).rejects.toThrow(/403/)
  })
})

// ---------------------------------------------------------------------------
// addMember
// ---------------------------------------------------------------------------

describe('addMember', () => {
  const base = {
    email: 'new@aiesec.example',
    lcId: '3',
    positionKey: 'member',
    functionKey: 'ogv',
    teamId: '12',
    termId: '7',
    startDate: '2026-01-01',
    endDate: '2026-12-31',
  }

  it('sends numeric-string ids as integers', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ status: 'created' }))
    await makeApi().addMember(base)
    const body = JSON.parse((fetchSpy.mock.calls[0][1] as RequestInit).body as string)
    expect(body).toMatchObject({ lcId: 3, teamId: 12, termId: 7 })
  })

  it('rejects a non-numeric lcId without calling the backend', async () => {
    const result = await makeApi().addMember({ ...base, lcId: 'lc-usyd' })
    expect(result).toEqual({ status: 'rejected', message: 'The form is out of date. Close it and try again.' })
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('rejects a non-numeric teamId or termId without calling the backend', async () => {
    const stale = { status: 'rejected', message: 'The form is out of date. Close it and try again.' }
    expect(await makeApi().addMember({ ...base, teamId: 'team-usyd-ogv-a' })).toEqual(stale)
    expect(await makeApi().addMember({ ...base, termId: 'term-1' })).toEqual(stale)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('sends teamId/termId/membershipId as null when not chosen', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ status: 'created' }))
    await makeApi().addMember({ ...base, teamId: undefined, termId: undefined })
    const body = JSON.parse((fetchSpy.mock.calls[0][1] as RequestInit).body as string)
    expect(body.teamId).toBeNull()
    expect(body.termId).toBeNull()
    expect(body.membershipId).toBeNull()
  })

  it("sends the actor's acting membershipId as an integer", async () => {
    // membershipId = which of the ACTOR's own memberships the add is made under.
    fetchSpy.mockReturnValueOnce(okResponse({ status: 'created' }))
    await makeApi().addMember({ ...base, membershipId: '5' })
    const body = JSON.parse((fetchSpy.mock.calls[0][1] as RequestInit).body as string)
    expect(body.membershipId).toBe(5)
  })

  it('POSTs to /api/v1/members', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ status: 'created' }))
    await makeApi().addMember(base)
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/api/v1/members`)
    expect(init.method).toBe('POST')
  })

  it('returns {status: created} for a successful add', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ status: 'created' }))
    const result = await makeApi().addMember(base)
    expect(result).toEqual({ status: 'created' })
  })

  it('returns {status: needs_name}', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ status: 'needs_name' }))
    expect(await makeApi().addMember(base)).toEqual({ status: 'needs_name' })
  })

  it('returns {status: confirm_existing}', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ status: 'confirm_existing' }))
    expect(await makeApi().addMember(base)).toEqual({ status: 'confirm_existing' })
  })

  it('returns {status: rejected, message}', async () => {
    fetchSpy.mockReturnValueOnce(
      okResponse({ status: 'rejected', message: "You can't add that." }),
    )
    expect(await makeApi().addMember(base)).toEqual({
      status: 'rejected',
      message: "You can't add that.",
    })
  })
})

// ---------------------------------------------------------------------------
// getMembershipDetail
// ---------------------------------------------------------------------------

describe('getMembershipDetail', () => {
  const detail = {
    membershipId: '42',
    personName: 'Ada Lovelace',
    position: {
      key: 'member',
      label: 'Member',
      level: 'lc',
      rank: 1,
      canAddSameRank: false,
      presidential: false,
      homeChartScope: 'team',
      holdsTeam: true,
    },
    function: { key: 'ogv', label: 'oGV' },
    lc: { id: 'lc-usyd', name: 'USYD', type: 'lc' },
    startDate: '2026-01-01',
    endDate: '2026-12-31',
    currentTeam: { id: 'team-1', name: 'oGV Team A' },
    teamOptions: [],
  }

  it('GETs /api/v1/members/:id', async () => {
    fetchSpy.mockReturnValueOnce(okResponse(detail))
    await makeApi().getMembershipDetail('42')
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/api/v1/members/42`)
    expect(init.method).toBe('GET')
  })

  it('encodes the membership id in the path', async () => {
    fetchSpy.mockReturnValueOnce(okResponse(detail))
    await makeApi().getMembershipDetail('a/b')
    expect(fetchSpy.mock.calls[0][0]).toBe(`${BASE}/api/v1/members/a%2Fb`)
  })

  it('returns the detail payload', async () => {
    fetchSpy.mockReturnValueOnce(okResponse(detail))
    const result = await makeApi().getMembershipDetail('42')
    expect(result.membershipId).toBe('42')
    expect(result.personName).toBe('Ada Lovelace')
    expect(result.currentTeam?.name).toBe('oGV Team A')
  })
})

// ---------------------------------------------------------------------------
// extendTerm
// ---------------------------------------------------------------------------

describe('extendTerm', () => {
  it('POSTs to /api/v1/members/:id/extend-term with {newEndDate}', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ status: 'ok' }))
    await makeApi().extendTerm('7', '2027-06-30')
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/api/v1/members/7/extend-term`)
    expect(JSON.parse(init.body as string)).toEqual({ newEndDate: '2027-06-30' })
  })

  it('returns {status: ok}', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ status: 'ok' }))
    expect(await makeApi().extendTerm('7', '2027-06-30')).toEqual({ status: 'ok' })
  })

  it('returns {status: rejected, message}', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ status: 'rejected', message: 'Denied.' }))
    expect(await makeApi().extendTerm('7', '2027-01-01')).toEqual({
      status: 'rejected',
      message: 'Denied.',
    })
  })
})

// ---------------------------------------------------------------------------
// moveToTeam
// ---------------------------------------------------------------------------

describe('moveToTeam', () => {
  it('POSTs to /api/v1/members/:id/move-to-team with integer teamId', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ status: 'ok' }))
    await makeApi().moveToTeam('7', '99')
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/api/v1/members/7/move-to-team`)
    expect(JSON.parse(init.body as string)).toEqual({ teamId: 99 })
  })

  it('returns {status: ok}', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ status: 'ok' }))
    expect(await makeApi().moveToTeam('7', '99')).toEqual({ status: 'ok' })
  })

  it('rejects a non-numeric teamId without calling the backend', async () => {
    expect(await makeApi().moveToTeam('7', 'team-usyd-ogv-a')).toEqual({
      status: 'rejected',
      message: 'The form is out of date. Close it and try again.',
    })
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('returns {status: rejected}', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ status: 'rejected', message: 'Wrong LC.' }))
    expect(await makeApi().moveToTeam('7', '99')).toEqual({
      status: 'rejected',
      message: 'Wrong LC.',
    })
  })
})

// ---------------------------------------------------------------------------
// Write methods: failures become rejections, never exceptions
// ---------------------------------------------------------------------------

describe('write failures', () => {
  it.each([
    [401, 'Your session has expired. Sign in again.'],
    [403, "You don't have permission to do that."],
    [404, 'That membership no longer exists. Refresh the page.'],
    [500, 'Something went wrong. Try again.'],
  ])('maps %i on extendTerm to a rejection', async (status, message) => {
    fetchSpy.mockReturnValueOnce(errorResponse(status, 'x'))
    expect(await makeApi().extendTerm('5', '2027-01-01')).toEqual({ status: 'rejected', message })
  })

  it('maps a network error on moveToTeam to a rejection', async () => {
    fetchSpy.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    expect(await makeApi().moveToTeam('5', '12')).toEqual({
      status: 'rejected',
      message: 'Something went wrong. Try again.',
    })
  })

  it('maps 401 on addMember to a session-expired rejection', async () => {
    fetchSpy.mockReturnValueOnce(errorResponse(401, 'x'))
    const input = {
      email: 'a@aiesec.net',
      lcId: '3',
      positionKey: 'member',
      functionKey: 'ogv',
      startDate: '2026-01-01',
      endDate: '2026-12-31',
    }
    expect(await makeApi().addMember(input)).toEqual({
      status: 'rejected',
      message: 'Your session has expired. Sign in again.',
    })
  })
})

// ---------------------------------------------------------------------------
// getReferenceData
// ---------------------------------------------------------------------------

describe('getReferenceData', () => {
  const LC_3 = { id: '3', name: 'USYD', type: 'lc', state: 'NSW', active: true }
  const TERM_7 = { id: '7', name: '26.2', startDate: '2026-08-01', endDate: '2026-12-31' }
  const TEAM_12 = { id: '12', name: 'oGV Team A', lcId: '3', functionKey: 'ogv', leader: null }

  it('takes lcs/terms/teams from the backend and positions/functions from the fallback', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ lcs: [LC_3], terms: [TERM_7], teams: [TEAM_12] }))
    const ref = await makeApi().getReferenceData()
    expect(fetchSpy.mock.calls[0][0]).toBe(`${BASE}/api/v1/reference/membership-options`)
    expect((fetchSpy.mock.calls[0][1] as RequestInit).credentials).toBe('same-origin')
    expect(ref.lcs).toEqual([LC_3])
    expect(ref.terms).toEqual([TERM_7])
    expect(ref.teams).toEqual([TEAM_12])
    expect(ref.positions.length).toBeGreaterThan(0)
    expect(ref.functions.length).toBeGreaterThan(0)
  })
})

// ---------------------------------------------------------------------------
// Delegated methods still use the mock
// ---------------------------------------------------------------------------

describe('delegated methods', () => {
  it('signIn / getMe / signOut still work via the mock', async () => {
    const api = makeApi()
    const meBefore = await api.getMe()
    expect(meBefore).toBeNull()
    await api.signIn()
    const meAfter = await api.getMe()
    expect(meAfter).not.toBeNull()
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// Admin console: People and Memberships (DEV-47)
// ---------------------------------------------------------------------------

describe('admin people', () => {
  const PERSON_ROW = {
    id: '5',
    firstName: 'Ada',
    lastName: 'Lovelace',
    email: 'ada@aiesec.net',
    active: false,
    status: 'active',
  }
  const NEW_PERSON = { firstName: 'Ada', lastName: 'Lovelace', email: 'ada@aiesec.net' }

  function jsonResponse(status: number, body: unknown) {
    return Promise.resolve(new Response(JSON.stringify(body), { status }))
  }

  it('createPerson maps 201 to ok', async () => {
    fetchSpy.mockReturnValueOnce(jsonResponse(201, PERSON_ROW))
    const result = await makeApi().createPerson(NEW_PERSON)
    expect(result).toEqual({ status: 'ok' })
    expect(fetchSpy.mock.calls[0][0]).toBe(`${BASE}/api/v1/people`)
    expect((fetchSpy.mock.calls[0][1] as RequestInit).method).toBe('POST')
  })

  it("createPerson shows the server's 409 detail", async () => {
    fetchSpy.mockReturnValueOnce(jsonResponse(409, { detail: 'Someone already has that email address.' }))
    const result = await makeApi().createPerson(NEW_PERSON)
    expect(result).toEqual({ status: 'rejected', message: 'Someone already has that email address.' })
  })

  it('deactivatePerson 404 says the person no longer exists', async () => {
    fetchSpy.mockReturnValueOnce(jsonResponse(404, { detail: 'Person not found' }))
    const result = await makeApi().deactivatePerson('5')
    expect(result).toEqual({
      status: 'rejected',
      message: 'That person no longer exists. Refresh the page.',
    })
    expect(fetchSpy.mock.calls[0][0]).toBe(`${BASE}/api/v1/people/5/deactivate`)
  })

  it('listPeopleAdmin sends the query as URL parameters and returns the page', async () => {
    fetchSpy.mockReturnValueOnce(jsonResponse(200, { rows: [PERSON_ROW], total: 1 }))
    const page = await makeApi().listPeopleAdmin({ search: 'ada l', page: 2, pageSize: 10 })
    expect(page).toEqual({ rows: [PERSON_ROW], total: 1 })
    expect(fetchSpy.mock.calls[0][0]).toBe(`${BASE}/api/v1/people?search=ada+l&page=2&pageSize=10`)
  })

  it('assignMembership maps ok', async () => {
    fetchSpy.mockReturnValueOnce(jsonResponse(200, { status: 'ok', membershipId: '9' }))
    const result = await makeApi().assignMembership('5', {
      lcId: '3',
      positionKey: 'member',
      functionKey: 'ogv',
      startDate: '2026-08-01',
      endDate: '2026-12-31',
    })
    expect(result).toEqual({ status: 'ok' })
    expect(fetchSpy.mock.calls[0][0]).toBe(`${BASE}/api/v1/people/5/memberships`)
    const body = JSON.parse((fetchSpy.mock.calls[0][1] as RequestInit).body as string)
    expect(body.lcId).toBe(3)
  })

  it('assignMembership passes a rejection message through', async () => {
    fetchSpy.mockReturnValueOnce(jsonResponse(200, { status: 'rejected', message: 'Nope.' }))
    const result = await makeApi().assignMembership('5', {
      lcId: '3',
      positionKey: 'member',
      functionKey: null,
      startDate: '2026-08-01',
      endDate: '2026-12-31',
    })
    expect(result).toEqual({ status: 'rejected', message: 'Nope.' })
  })

  it('correctMembership PATCHes and endMembership POSTs', async () => {
    fetchSpy.mockReturnValueOnce(jsonResponse(200, { status: 'ok' }))
    fetchSpy.mockReturnValueOnce(jsonResponse(200, { status: 'ok' }))
    const api = makeApi()
    expect(await api.correctMembership('9', { functionKey: null })).toEqual({ status: 'ok' })
    expect(await api.endMembership('9', '2026-10-01')).toEqual({ status: 'ok' })
    expect(fetchSpy.mock.calls[0][0]).toBe(`${BASE}/api/v1/memberships/9`)
    expect((fetchSpy.mock.calls[0][1] as RequestInit).method).toBe('PATCH')
    expect(JSON.parse((fetchSpy.mock.calls[0][1] as RequestInit).body as string)).toEqual({ functionKey: null })
    expect(fetchSpy.mock.calls[1][0]).toBe(`${BASE}/api/v1/memberships/9/end`)
    expect(JSON.parse((fetchSpy.mock.calls[1][1] as RequestInit).body as string)).toEqual({ endDate: '2026-10-01' })
  })

  it('updatePerson PATCHes, reactivatePerson POSTs, listPersonMemberships throws on error', async () => {
    fetchSpy.mockReturnValueOnce(jsonResponse(200, PERSON_ROW))
    fetchSpy.mockReturnValueOnce(jsonResponse(200, PERSON_ROW))
    fetchSpy.mockReturnValueOnce(jsonResponse(403, { detail: 'no' }))
    const api = makeApi()
    expect(await api.updatePerson('5', { firstName: 'Ada' })).toEqual({ status: 'ok' })
    expect(await api.reactivatePerson('5')).toEqual({ status: 'ok' })
    expect(fetchSpy.mock.calls[0][0]).toBe(`${BASE}/api/v1/people/5`)
    expect(fetchSpy.mock.calls[1][0]).toBe(`${BASE}/api/v1/people/5/reactivate`)
    await expect(api.listPersonMemberships('5')).rejects.toThrow()
  })

  it("shows the server's detail on a 403 from a People write", async () => {
    fetchSpy.mockReturnValueOnce(jsonResponse(403, { detail: "You can't do this to your own record." }))
    expect(await makeApi().deactivatePerson('5')).toEqual({
      status: 'rejected',
      message: "You can't do this to your own record.",
    })
  })

  it('unlinkExpa maps a person row to ok', async () => {
    fetchSpy.mockReturnValueOnce(jsonResponse(200, { ...PERSON_ROW, expaLinked: false }))
    expect(await makeApi().unlinkExpa('5')).toEqual({ status: 'ok' })
    expect(fetchSpy.mock.calls[0][0]).toBe(`${BASE}/api/v1/people/5/unlink-expa`)
    expect((fetchSpy.mock.calls[0][1] as RequestInit).method).toBe('POST')
  })

  it('unlinkExpa shows the server reason, and a 404 says the person no longer exists', async () => {
    fetchSpy.mockReturnValueOnce(jsonResponse(400, { detail: "This person isn't linked to EXPA." }))
    expect(await makeApi().unlinkExpa('5')).toEqual({ status: 'rejected', message: "This person isn't linked to EXPA." })
    fetchSpy.mockReturnValueOnce(jsonResponse(404, { detail: 'Not found' }))
    const gone = await makeApi().unlinkExpa('5')
    expect(gone.status === 'rejected' && gone.message).toMatch(/no longer exists/)
  })

  it('unlinkExpa with an id that is not a database id is refused without calling the backend', async () => {
    expect((await makeApi().unlinkExpa('p-ada')).status).toBe('rejected')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('a person id that is not a database id is refused without calling the backend', async () => {
    const result = await makeApi().deactivatePerson('p-ada')
    expect(result.status).toBe('rejected')
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
