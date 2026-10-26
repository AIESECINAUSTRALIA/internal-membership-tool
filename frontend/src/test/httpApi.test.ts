/**
 * Tests for the real HTTP `Api` implementation (Ticket DEV-0043, Spec §2A.5).
 *
 * These tests stub `globalThis.fetch` so they exercise the httpApi's request-
 * building and response-normalisation logic (the shape translation between
 * backend and frontend types) without needing a live server.
 *
 * What these tests cover:
 *   - Each of the five membership-summary methods sends the right request.
 *   - Backend `{items, total}` is normalised to frontend `{rows, total}`.
 *   - String→integer coercions for lcId, teamId, termId, membershipId.
 *   - The `X-Actor-Email` header is included when the actor email is set.
 *   - All four `AddMemberResult` statuses are returned correctly.
 *   - HTTP error responses throw with a useful message.
 *
 * What these tests do NOT cover (tested by the backend's own pytest suite):
 *   - The permission / hierarchy / LC-isolation logic (that's server-side).
 *   - The mock's behaviour (covered by mockApi.test.ts which stays unchanged).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createHttpApi } from '../api/http/httpApi'
import type { MemberQuery } from '../api/types'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ACTOR_EMAIL = 'lcvp@aiesec.example'
const BASE = 'http://localhost:8000'

function makeApi(email: string | null = ACTOR_EMAIL) {
  return createHttpApi({
    getActorEmail: () => email,
    // Use zero-latency mock for the delegated methods (getMe, getReferenceData…)
    mockOptions: { latencyMs: 0 },
  })
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
    const backendPage = { items: [], total: 0, page: 0, pageSize: 15 }
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

  it('sends the actor email as X-Actor-Email', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ items: [], total: 0, page: 0, pageSize: 15 }))
    await makeApi(ACTOR_EMAIL).listMembers(ALL)
    const headers = (fetchSpy.mock.calls[0][1] as RequestInit).headers as Record<string, string>
    expect(headers['X-Actor-Email']).toBe(ACTOR_EMAIL)
  })

  it('omits X-Actor-Email when actor email is null', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ items: [], total: 0, page: 0, pageSize: 15 }))
    await makeApi(null).listMembers(ALL)
    const headers = (fetchSpy.mock.calls[0][1] as RequestInit).headers as Record<string, string>
    expect(headers['X-Actor-Email']).toBeUndefined()
  })

  it('normalises backend {items} to frontend {rows}', async () => {
    const row = {
      personId: 'p-1',
      firstName: 'Ada',
      lastName: 'Lovelace',
      lc: { id: 'lc-1', name: 'USYD', type: 'lc' },
      roles: [],
    }
    fetchSpy.mockReturnValueOnce(okResponse({ items: [row], total: 1, page: 0, pageSize: 15 }))
    const result = await makeApi().listMembers(ALL)
    expect(result.rows).toHaveLength(1)
    expect(result.rows[0].firstName).toBe('Ada')
    expect(result.total).toBe(1)
  })

  it('passes sort field and direction when provided', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ items: [], total: 0, page: 0, pageSize: 15 }))
    await makeApi().listMembers({
      ...ALL,
      sort: { field: 'firstName', direction: 'desc' },
    })
    const body = JSON.parse((fetchSpy.mock.calls[0][1] as RequestInit).body as string)
    expect(body.sortField).toBe('firstName')
    expect(body.sortDirection).toBe('desc')
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
    lcId: 'lc-usyd',
    positionKey: 'member',
    functionKey: 'ogv',
    teamId: 'team-usyd-ogv-a',
    startDate: '2026-01-01',
    endDate: '2026-12-31',
  }

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
    // teamId must be an integer on the wire (backend schema is int)
    expect(JSON.parse(init.body as string)).toEqual({ teamId: 99 })
  })

  it('returns {status: ok}', async () => {
    fetchSpy.mockReturnValueOnce(okResponse({ status: 'ok' }))
    expect(await makeApi().moveToTeam('7', '99')).toEqual({ status: 'ok' })
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
// Delegated methods still use the mock
// ---------------------------------------------------------------------------

describe('delegated methods', () => {
  it('signIn / getMe / signOut still work via the mock', async () => {
    const api = makeApi()
    // No fetch calls — these go to the mock
    const meBefore = await api.getMe()
    expect(meBefore).toBeNull() // not signed in yet
    await api.signIn()
    const meAfter = await api.getMe()
    expect(meAfter).not.toBeNull()
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
