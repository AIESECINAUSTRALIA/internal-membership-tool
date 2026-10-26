/**
 * Real sign-in (VITE_AUTH_MODE=supabase): the Api wrapper on its own, then the whole app
 * with a fake Supabase and a fake backend. No network: `auth` and `fetch` are stand-ins.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { act } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App'
import { AppProviders } from '../AppProviders'
import { createMockApi } from '../api/mock/mockApi'
import { POSITIONS } from '../api/mock/seed'
import {
  meFromResponse,
  SignInRejectedError,
  withSupabaseSession,
  type MeResponse,
  type SessionAuth,
} from '../api/supabaseSession'

// ---------------------------------------------------------------------------
// Fakes
// ---------------------------------------------------------------------------

/** A stand-in for `supabase.auth`, holding at most one session token. */
function fakeAuth(initialToken: string | null = null) {
  let token = initialToken
  const listeners = new Set<(event: string) => void>()
  const emit = (event: string) => listeners.forEach((listener) => listener(event))
  const auth = {
    getSession: vi.fn(async () => ({ data: { session: token ? { access_token: token } : null } })),
    signInWithOAuth: vi.fn<SessionAuth['signInWithOAuth']>(async () => ({ error: null })),
    signOut: vi.fn(async () => {
      token = null
      emit('SIGNED_OUT')
    }),
    onAuthStateChange: vi.fn((callback: (event: string) => void) => {
      listeners.add(callback)
      return { data: { subscription: { unsubscribe: () => listeners.delete(callback) } } }
    }),
  } satisfies SessionAuth
  return {
    auth,
    listenerCount: () => listeners.size,
    /** Simulate coming back from Google signed in. */
    signInExternally(newToken: string) {
      token = newToken
      emit('SIGNED_IN')
    },
    emit,
  }
}

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
      lc: { id: 3, name: 'USYD', type: 'LC' },
      team: { id: 5, name: 'oGV Team 1' },
      start_date: '2020-01-01',
      end_date: null,
    },
  ],
  permissions: [],
}

const NO_PERSON: MeResponse = { email: 'new@aiesec.net', person: null, memberships: [], permissions: [] }

function build(options: { token?: string | null; fetch?: typeof fetch; hostedDomain?: string } = {}) {
  const fake = fakeAuth(options.token ?? null)
  const fetchFn = vi.fn(options.fetch ?? (async () => json(200, ACTIVE_LCVP)))
  const base = createMockApi({ latencyMs: 0 })
  const api = withSupabaseSession(base, {
    auth: fake.auth,
    apiUrl: 'http://api.test/',
    hostedDomain: options.hostedDomain,
    redirectTo: 'http://app.test/sign-in',
    fetch: fetchFn,
  })
  return { api, base, fake, fetchFn }
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
      customFields: [],
    })
    expect(me.memberships).toEqual([
      {
        id: '11',
        position: POSITIONS.find((p) => p.key === 'lcvp'),
        function: { key: 'ogv', label: 'Outgoing Global Volunteer' },
        lc: { id: '3', name: 'USYD', type: 'lc' },
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
      memberships: [{ ...ACTIVE_LCVP.memberships[0], position: { key: 'mystery', label: 'Mystery' }, lc: { id: 1, name: 'MC', type: 'MC' } }],
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
    expect(me.person).toEqual({ id: '', firstName: 'new', lastName: '', email: 'new@aiesec.net', customFields: [] })
    expect(me.memberships).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// withSupabaseSession
// ---------------------------------------------------------------------------

describe('withSupabaseSession', () => {
  it('says it signs in with Google', () => {
    expect(build().api.signInMethod).toBe('google')
    expect(createMockApi().signInMethod).toBeUndefined()
  })

  it('returns null without a session, and never calls the backend', async () => {
    const { api, fetchFn } = build()
    expect(await api.getMe()).toBeNull()
    expect(fetchFn).not.toHaveBeenCalled()
  })

  it('sends the access token to GET /api/v1/me', async () => {
    const { api, fetchFn } = build({ token: 'tok-1' })
    const me = await api.getMe()
    expect(fetchFn).toHaveBeenCalledWith('http://api.test/api/v1/me', {
      headers: { Authorization: 'Bearer tok-1' },
    })
    expect(me?.person.email).toBe('ada@aiesec.net')
  })

  it('signs out and returns null on 401 (expired session goes back to sign-in)', async () => {
    const { api, fake } = build({ token: 'old', fetch: async () => json(401, { detail: 'Invalid or expired token' }) })
    expect(await api.getMe()).toBeNull()
    expect(fake.auth.signOut).toHaveBeenCalled()
  })

  it('signs out and throws SignInRejectedError on 403 (not an allowed domain)', async () => {
    const { api, fake } = build({ token: 'gmail', fetch: async () => json(403, { detail: 'nope' }) })
    await expect(api.getMe()).rejects.toBeInstanceOf(SignInRejectedError)
    expect(fake.auth.signOut).toHaveBeenCalled()
  })

  it('throws on other server errors, without signing out', async () => {
    const { api, fake } = build({ token: 't', fetch: async () => json(500, {}) })
    await expect(api.getMe()).rejects.toThrow('HTTP 500')
    expect(fake.auth.signOut).not.toHaveBeenCalled()
  })

  it('starts Google sign-in with the redirect and the hosted-domain hint', async () => {
    const { api, fake } = build({ hostedDomain: 'aiesec.net' })
    await api.signIn()
    expect(fake.auth.signInWithOAuth).toHaveBeenCalledWith({
      provider: 'google',
      options: {
        redirectTo: 'http://app.test/sign-in',
        queryParams: { prompt: 'select_account', hd: 'aiesec.net' },
      },
    })
  })

  it('leaves out the hosted-domain hint when none is configured', async () => {
    const { api, fake } = build()
    await api.signIn()
    expect(fake.auth.signInWithOAuth.mock.calls[0][0].options?.queryParams).toEqual({ prompt: 'select_account' })
  })

  it('throws when Supabase cannot start sign-in', async () => {
    const { api, fake } = build()
    fake.auth.signInWithOAuth.mockResolvedValueOnce({ error: new Error('provider disabled') })
    await expect(api.signIn()).rejects.toThrow('provider disabled')
  })

  it('reports identity changes only, and can unsubscribe', () => {
    const { api, fake } = build()
    const listener = vi.fn()
    const unsubscribe = api.onSessionChange!(listener)

    fake.emit('INITIAL_SESSION')
    fake.emit('TOKEN_REFRESHED')
    expect(listener).not.toHaveBeenCalled()
    fake.emit('SIGNED_IN')
    fake.emit('SIGNED_OUT')
    expect(listener).toHaveBeenCalledTimes(2)

    unsubscribe()
    expect(fake.listenerCount()).toBe(0)
  })

  it('does not report its own sign-out after a rejection (the message must survive)', async () => {
    const { api } = build({ token: 'gmail', fetch: async () => json(403, {}) })
    const listener = vi.fn()
    api.onSessionChange!(listener)
    await expect(api.getMe()).rejects.toBeInstanceOf(SignInRejectedError)
    expect(listener).not.toHaveBeenCalled()
  })

  it('still reports a sign-out the person asked for', async () => {
    const { api } = build({ token: 'tok' })
    const listener = vi.fn()
    api.onSessionChange!(listener)
    await api.signOut()
    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('keeps every non-session method from the wrapped Api', () => {
    const { api, base } = build()
    expect(api.getReferenceData).toBe(base.getReferenceData)
    expect(api.listMembers).toBe(base.listMembers)
  })
})

// ---------------------------------------------------------------------------
// The whole app in Google mode
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

describe('the app with Google sign-in', () => {
  it('shows only a "Sign in with Google" button when signed out, and starts Google sign-in', async () => {
    const { fake } = renderApp({}, '/membership')

    const button = await screen.findByRole('button', { name: 'Sign in with Google' })
    expect(screen.queryByRole('button', { name: 'Sign in' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Development sign-in/)).not.toBeInTheDocument()

    fireEvent.click(button)
    await waitFor(() => expect(fake.auth.signInWithOAuth).toHaveBeenCalledTimes(1))
  })

  it('lands an allocated person on the homepage', async () => {
    renderApp({ token: 'tok' }, '/sign-in')
    expect(await screen.findByRole('heading', { name: 'Home' })).toBeInTheDocument()
    expect(screen.getByText('Welcome back, Ada.')).toBeInTheDocument()
    // Chart data is still mock-only and has no mock session: empty state, not a spinner.
    expect(await screen.findByText('No data exists')).toBeInTheDocument()
  })

  it('denies by default: with no permissions from the server, Membership is not offered', async () => {
    renderApp({ token: 'tok' }, '/membership')
    expect(await screen.findByRole('heading', { name: 'Page not available' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Main' })).not.toHaveTextContent('Membership')
  })

  it('shows an error, not an endless spinner, where page data is still mock-only', async () => {
    const withPermissions: MeResponse = {
      ...ACTIVE_LCVP,
      permissions: [{ resource: 'membership', action: 'view', scope: 'lc' }],
    }
    renderApp({ token: 'tok', fetch: async () => json(200, withPermissions) }, '/membership')
    expect(await screen.findByRole('heading', { name: 'Membership' })).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toHaveTextContent('The member list could not be loaded')
  })

  it('shows the not-allocated page when the email matches no person', async () => {
    renderApp({ token: 'tok', fetch: async () => json(200, NO_PERSON) })
    expect(
      await screen.findByRole('heading', {
        name: 'You have not been allocated yet, please contact someone in your EB or MC',
      }),
    ).toBeInTheDocument()
  })

  it('explains the rejection when the account is not an AIESEC one', async () => {
    renderApp({ token: 'gmail', fetch: async () => json(403, { detail: 'Only AIESEC accounts can sign in' }) })
    expect(await screen.findByRole('alert')).toHaveTextContent('Only AIESEC accounts can sign in')
    expect(screen.getByRole('button', { name: 'Sign in with Google' })).toBeInTheDocument()
  })

  it('sends someone with an expired session back to sign-in, with no extra page', async () => {
    const { fake } = renderApp({ token: 'expired', fetch: async () => json(401, {}) })
    expect(await screen.findByRole('button', { name: 'Sign in with Google' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fake.auth.signOut).toHaveBeenCalled()
  })

  it('says so when the backend cannot be reached', async () => {
    renderApp({ token: 'tok', fetch: async () => Promise.reject(new TypeError('Failed to fetch')) })
    expect(await screen.findByRole('alert')).toHaveTextContent('could not check your sign-in')
  })

  it('picks up a sign-in that finishes after the page loaded (returning from Google)', async () => {
    const { fake } = renderApp({}, '/sign-in')
    await screen.findByRole('button', { name: 'Sign in with Google' })

    act(() => fake.signInExternally('fresh'))
    expect(await screen.findByRole('heading', { name: 'Home' })).toBeInTheDocument()
  })

  it('signs out from the profile menu and returns to sign-in', async () => {
    const { fake } = renderApp({ token: 'tok' })
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile menu' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Sign out' }))
    expect(await screen.findByRole('button', { name: 'Sign in with Google' })).toBeInTheDocument()
    expect(fake.auth.signOut).toHaveBeenCalled()
  })
})
