/**
 * Real sign-in (VITE_AUTH_MODE=expa): the Api wrapper on its own, then the whole app
 * with a fake backend. No network or browser navigation: `fetch` and `navigate`
 * are stand-ins for the real browser operations.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { act } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App'
import { AppProviders } from '../AppProviders'
import { createMockApi } from '../api/mock/mockApi'
import { POSITIONS } from '../api/mock/seed'
import { createSessionEvents } from '../api/sessionEvents'
import {
  meFromResponse,
  withExpaSession,
  type MeResponse,
} from '../api/expaSession'


// ---------------------------------------------------------------------------
// Fakes
// ---------------------------------------------------------------------------


const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const ACTIVE_LCVP: MeResponse = {
  email: 'ada@aiesec.net',
  person: { id: 7, full_name: 'Ada King Lovelace', preferred_name: null, aiesec_email: 'ada@aiesec.net' },
  memberships: [
    {
      id: 11,
      position: { key: 'lcvp', label: 'LC Vice President' },
      function: { key: 'ogv', label: 'Outgoing Global Volunteer' },
      lc: { id: 3, name: 'USYD', type: 'LC', state: 'NSW', active: true },
      team: { id: 5, name: 'oGV Team 1' },
      start_date: '2020-01-01',
      end_date: null,
    },
  ],
  permissions: [],
}

const NO_PERSON: MeResponse = { email: 'new@aiesec.net', person: null, memberships: [], permissions: [] }


function build(
  options: {
    signedIn?: boolean
    fetch?: typeof fetch
  } = {},
) {
  let signedIn = options.signedIn ?? false
  const sessionEvents = createSessionEvents()
  const navigate = vi.fn<(url: string) => void>()

  const fetchFn = vi.fn(
    options.fetch ??
      (async (input: RequestInfo | URL) => {
        const url = String(input)

        if (url.endsWith('/api/v1/auth/logout')) {
          signedIn = false
          return new Response(null, { status: 204 })
        }

        if (url.endsWith('/api/v1/me')) {
          return signedIn
            ? json(200, ACTIVE_LCVP)
            : json(401, { detail: 'Invalid or expired session' })
        }

        throw new Error(`Unexpected request: ${url}`)
      }),
  )

  const base = createMockApi({ latencyMs: 0 })

  const api = withExpaSession(base, {
    apiUrl: 'http://api.test/',
    fetch: fetchFn,
    navigate,
    getPositions: async () => POSITIONS,
    subscribeToSessionChanges: sessionEvents.subscribe,
  })

  return {
    api,
    base,
    fetchFn,
    navigate,
    sessionEvents,

    expireSession() {
      signedIn = false
      sessionEvents.notify()
    },
  }
}

beforeEach(() => sessionStorage.clear())

// ---------------------------------------------------------------------------
// meFromResponse
// ---------------------------------------------------------------------------

describe('meFromResponse', () => {
  it('maps the person, and takes positions from the reference data by key', () => {
    const me = meFromResponse(ACTIVE_LCVP, POSITIONS)

    expect(me.person).toEqual({
      id: '7',
      firstName: 'Ada',
      lastName: 'King Lovelace',
      email: 'ada@aiesec.net',
    })
    expect(me.memberships).toEqual([
      {
        id: '11',
        position: POSITIONS.find((p) => p.key === 'lcvp'),
        function: { key: 'ogv', label: 'Outgoing Global Volunteer' },
        lc: { id: '3', name: 'USYD', type: 'lc', state: 'NSW', active: true,},
        team: { id: '5', name: 'oGV Team 1' },
        startDate: '2020-01-01',
        endDate: null,
      },
    ])
    expect(me.permissions).toEqual([])
  })

  it('prefers the preferred name as first name', () => {
    const me = meFromResponse(
      { ...ACTIVE_LCVP, person: { ...ACTIVE_LCVP.person!, preferred_name: 'Addy' } },
      POSITIONS,
    )
    expect(me.person.firstName).toBe('Addy')
  })

  it('gives an unknown position the most restrictive defaults', () => {
    const body: MeResponse = {
      ...ACTIVE_LCVP,
      memberships: [{ ...ACTIVE_LCVP.memberships[0], position: { key: 'mystery', label: 'Mystery' }, lc: { id: 1, name: 'MC', type: 'MC', state: null, active: true } }],
    }
    const [membership] = meFromResponse(body, POSITIONS).memberships
    expect(membership.position).toEqual({
      key: 'mystery',
      label: 'Mystery',
      level: 'mc',
      rank: 0,
      canAddSameRank: false,
      presidential: false,
      homeChartScope: 'team',
      holdsTeam: false,
    })
    expect(membership.lc.type).toBe('mc')
  })

  it('still returns a person, with no memberships, when the email matched nobody', () => {
    const me = meFromResponse(NO_PERSON, POSITIONS)
    expect(me.person).toEqual({ id: '', firstName: 'new', lastName: '', email: 'new@aiesec.net' })
    expect(me.memberships).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// withExpaSession
// ---------------------------------------------------------------------------


describe('withExpaSession', () => {
  it('says it signs in with EXPA', () => {
    expect(build().api.signInMethod).toBe('expa')
    expect(createMockApi().signInMethod).toBeUndefined()
  })

  it('checks the backend even when the browser has no session', async () => {
    const { api, fetchFn } = build()

    expect(await api.getMe()).toBeNull()
    expect(fetchFn).toHaveBeenCalledWith('http://api.test/api/v1/me', {
      credentials: 'same-origin',
      cache: 'no-store',
    })
  })

  it('loads the authenticated person using the session cookie', async () => {
    const { api, fetchFn } = build({ signedIn: true })

    const me = await api.getMe()

    expect(me?.person.email).toBe('ada@aiesec.net')
    expect(fetchFn).toHaveBeenCalledWith('http://api.test/api/v1/me', {
      credentials: 'same-origin',
      cache: 'no-store',
    })
  })

  it('takes positions from getPositions, so sign-in never depends on reference data', async () => {
    const base = {
      ...createMockApi({ latencyMs: 0 }),
      getReferenceData: vi.fn(() =>
        Promise.reject(new Error('GET /api/v1/reference → 500')),
      ),
    }

    const api = withExpaSession(base, {
      apiUrl: 'http://api.test/',
      fetch: vi.fn(async () => json(200, ACTIVE_LCVP)),
      getPositions: async () => POSITIONS,
    })

    const me = await api.getMe()

    expect(me?.memberships[0].position.key).toBe(
      ACTIVE_LCVP.memberships[0].position.key,
    )
    expect(base.getReferenceData).not.toHaveBeenCalled()
  })

  it('returns null on 401 without making a logout request', async () => {
    const { api, fetchFn } = build({
      fetch: async () => json(401, {}),
    })

    expect(await api.getMe()).toBeNull()
    expect(fetchFn).toHaveBeenCalledOnce()
  })

  it.each([403, 500])('throws on HTTP %i', async (status) => {
    const { api } = build({
      fetch: async () => json(status, {}),
    })

    await expect(api.getMe()).rejects.toThrow(String(status))
  })

  it('starts EXPA sign-in through browser navigation', async () => {
    const { api, navigate, fetchFn } = build()

    await api.signIn()

    expect(navigate).toHaveBeenCalledWith(
      'http://api.test/api/v1/auth/login',
    )
    expect(fetchFn).not.toHaveBeenCalled()
  })

  it('uses a relative login URL for same-origin deployments', async () => {
    const navigate = vi.fn()
    const api = withExpaSession(createMockApi(), {
      apiUrl: '',
      navigate,
    })

    await api.signIn()

    expect(navigate).toHaveBeenCalledWith('/api/v1/auth/login')
  })

  it('revokes the session through the backend on sign-out', async () => {
    const { api, fetchFn } = build({ signedIn: true })

    await api.signOut()

    expect(fetchFn).toHaveBeenCalledWith(
      'http://api.test/api/v1/auth/logout',
      {
        method: 'POST',
        credentials: 'same-origin',
      },
    )

    expect(await api.getMe()).toBeNull()
  })

  it('throws when the backend cannot complete sign-out', async () => {
    const { api } = build({
      fetch: async () => json(500, {}),
    })

    await expect(api.signOut()).rejects.toThrow('500')
  })

  it('reports session changes and supports unsubscribing', () => {
    const { api, sessionEvents } = build()
    const listener = vi.fn()
    const unsubscribe = api.onSessionChange!(listener)

    sessionEvents.notify()
    expect(listener).toHaveBeenCalledOnce()

    unsubscribe()
    sessionEvents.notify()
    expect(listener).toHaveBeenCalledOnce()
  })

  it('keeps every non-session method from the wrapped Api', () => {
    const { api, base } = build()

    expect(api.getReferenceData).toBe(base.getReferenceData)
    expect(api.listMembers).toBe(base.listMembers)
  })
})

// ---------------------------------------------------------------------------
// The whole app in EXPA mode
// ---------------------------------------------------------------------------

function renderApp(options: Parameters<typeof build>[0], path = '/') {
  const built = build(options)
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppProviders api={built.api}>
        <App />
      </AppProviders>
    </MemoryRouter>,
  )
  return built
}


describe('the app with EXPA sign-in', () => {
  it('shows only a "Sign in with EXPA" button when signed out', async () => {
    const { navigate } = renderApp({}, '/membership')

    const button = await screen.findByRole('button', {
      name: 'Sign in with EXPA',
    })

    expect(screen.queryByRole('button', { name: 'Sign in' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Development sign-in/)).not.toBeInTheDocument()

    fireEvent.click(button)

    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith(
        'http://api.test/api/v1/auth/login',
      ),
    )
  })

  it('lands an allocated person on the homepage', async () => {
    renderApp({ signedIn: true }, '/sign-in')

    expect(await screen.findByRole('heading', { name: 'Home' })).toBeInTheDocument()
    expect(screen.getByText('Welcome back, Ada.')).toBeInTheDocument()

    // Chart data is still mock-only and has no mock session:
    // empty state, not a spinner.
    expect(await screen.findByText('No data exists')).toBeInTheDocument()
  })

  it('denies by default when the server grants no permissions', async () => {
    renderApp({ signedIn: true }, '/membership')

    expect(
      await screen.findByRole('heading', { name: 'Page not available' }),
    ).toBeInTheDocument()

    expect(
      screen.getByRole('navigation', { name: 'Main' }),
    ).not.toHaveTextContent('Membership')
  })

  it('shows an error, not an endless spinner, where page data is still mock-only', async () => {
    const withPermissions: MeResponse = {
      ...ACTIVE_LCVP,
      permissions: [{ resource: 'membership', action: 'view', scope: 'lc' }],
    }

    renderApp(
      { fetch: async () => json(200, withPermissions) },
      '/membership',
    )

    expect(
      await screen.findByRole('heading', { name: 'Membership' }),
    ).toBeInTheDocument()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The member list could not be loaded',
    )
  })

  it('shows the not-allocated page when an existing session has no active membership', async () => {
    renderApp({
      fetch: async () =>
        json(200, { ...ACTIVE_LCVP, memberships: [], permissions: [] }),
    })

    expect(
      await screen.findByRole('heading', {
        name: 'You have not been allocated yet, please contact someone in your EB or MC',
      }),
    ).toBeInTheDocument()
  })

  it.each([
    ['denied', 'Sign-in was cancelled. Please try again.'],
    ['expired', 'Your sign-in attempt expired. Please try again.'],
    ['expa', 'We could not reach EXPA. Please try again in a moment.'],
    ['domain', 'Please sign in with your AIESEC account.'],
    [
      'not_allocated',
      'You have not been allocated yet, please contact someone in your EB or MC',
    ],
    ['unknown', 'Sign-in failed. Please try again.'],
  ])('explains callback failure: %s', async (code, message) => {
    renderApp({}, `/sign-in?error=${code}`)

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(
      screen.getByRole('button', { name: 'Sign in with EXPA' }),
    ).toBeInTheDocument()
  })

  it('sends someone with an expired session back to sign-in', async () => {
    renderApp({
      fetch: async () => json(401, {}),
    })

    expect(
      await screen.findByRole('button', { name: 'Sign in with EXPA' }),
    ).toBeInTheDocument()

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('says so when the backend cannot be reached', async () => {
    renderApp({
      fetch: async () => Promise.reject(new TypeError('Failed to fetch')),
    })

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'could not check your sign-in',
    )
  })

  it('returns to sign-in when an active session expires or is revoked', async () => {
    const { expireSession } = renderApp({ signedIn: true })

    expect(await screen.findByRole('heading', { name: 'Home' })).toBeInTheDocument()

    act(() => expireSession())

    expect(
      await screen.findByRole('button', { name: 'Sign in with EXPA' }),
    ).toBeInTheDocument()
  })

  it('signs out from the profile menu and returns to sign-in', async () => {
    const { fetchFn } = renderApp({ signedIn: true })

    fireEvent.click(
      await screen.findByRole('button', { name: 'Open profile menu' }),
    )
    fireEvent.click(screen.getByRole('menuitem', { name: 'Sign out' }))

    expect(
      await screen.findByRole('button', { name: 'Sign in with EXPA' }),
    ).toBeInTheDocument()

    expect(fetchFn).toHaveBeenCalledWith(
      'http://api.test/api/v1/auth/logout',
      {
        method: 'POST',
        credentials: 'same-origin',
      },
    )
  })
})
