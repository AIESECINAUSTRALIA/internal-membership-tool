/**
 * Real sign-in: Google through Supabase Auth, checked by our backend (spec §9).
 * Read docs/auth.md first.
 *
 * `withSupabaseSession(base)` takes another `Api` (today, the mock) and replaces ONLY
 * the session methods: `getMe`, `signIn`, `signOut`, `onSessionChange`. Everything else
 * still comes from `base` until those backend endpoints exist.
 *
 * The flow:
 * 1. `signIn()` sends the browser to Google (via Supabase). Google sends it back to
 *    `/sign-in`, where Supabase finishes the sign-in and stores a session.
 * 2. `getMe()` sends the session's access token to `GET /api/v1/me`. The backend checks
 *    the token and the email domain, and matches the email to a `person`.
 * 3. The answer becomes the same `Me` shape the mock returns, so no page changes.
 */
import type { FunctionRef, Lc, Me, MembershipView, Position } from './types'
import type { Api } from './types'

/** The bit of `supabase.auth` we use. The real client fits it; tests pass a fake. */
export interface SessionAuth {
  getSession(): Promise<{ data: { session: { access_token: string } | null } }>
  signInWithOAuth(credentials: {
    provider: 'google'
    options?: { redirectTo?: string; queryParams?: Record<string, string> }
  }): Promise<{ error: Error | null }>
  signOut(): Promise<unknown>
  onAuthStateChange(callback: (event: string) => void): {
    data: { subscription: { unsubscribe(): void } }
  }
}

export interface SupabaseSessionOptions {
  auth: SessionAuth
  /** The backend's base URL, e.g. http://localhost:8000 (VITE_API_URL). */
  apiUrl: string
  /** Optional Google hint, e.g. "aiesec.net": the account picker shows only that
   * domain's accounts. Only a hint: the backend is what actually enforces the domain. */
  hostedDomain?: string
  /** Where Google sends the browser back to. Defaults to this site's /sign-in. */
  redirectTo?: string
  fetch?: typeof fetch
}

/** The backend said "valid Google account, but not an allowed domain" (HTTP 403). */
export class SignInRejectedError extends Error {
  constructor(message = 'Only AIESEC accounts can sign in. Use your @aiesec.net Google account.') {
    super(message)
    this.name = 'SignInRejectedError'
  }
}

// ---------------------------------------------------------------------------
// GET /api/v1/me, exactly as the backend sends it (backend/app/schemas/me.py)
// ---------------------------------------------------------------------------

interface LookupResponse {
  key: string
  label: string
}

export interface MeResponse {
  email: string
  person: {
    id: number
    full_name: string
    preferred_name: string | null
    aiesec_email: string
  } | null
  memberships: {
    id: number
    position: LookupResponse
    function: LookupResponse | null
    lc: { id: number; name: string; type: string }
    team: { id: number; name: string } | null
    start_date: string
    end_date: string | null
  }[]
  permissions: { resource: string; action: string; scope: string }[]
}

/**
 * Turns the backend's answer into the frontend's `Me`.
 *
 * Positions are looked up by `key` in `positions` (the reference data), because the
 * frontend's `Position` carries fields the backend schema doesn't have yet (level, the
 * spec's rank order, ...; see docs/data-model.md "Known differences"). An unknown key
 * gets the most restrictive defaults.
 *
 * No `person` (the email matched nobody) still gives a `Me`, with no memberships, so
 * the guards show the not-allocated page (§9) rather than the sign-in page.
 */
export function meFromResponse(body: MeResponse, positions: Position[]): Me {
  const [firstWord = '', ...rest] = (body.person?.full_name ?? '').trim().split(/\s+/)
  return {
    person: body.person
      ? {
          id: String(body.person.id),
          firstName: body.person.preferred_name ?? firstWord,
          lastName: rest.join(' '),
          email: body.person.aiesec_email,
          customFields: [],
        }
      : { id: '', firstName: body.email.split('@')[0], lastName: '', email: body.email, customFields: [] },
    memberships: body.memberships.map((m): MembershipView => {
      const lc: Lc = { id: String(m.lc.id), name: m.lc.name, type: m.lc.type === 'MC' ? 'mc' : 'lc' }
      const fn: FunctionRef | null = m.function ? { key: m.function.key, label: m.function.label } : null
      return {
        id: String(m.id),
        position: positions.find((p) => p.key === m.position.key) ?? unknownPosition(m.position, lc),
        function: fn,
        lc,
        team: m.team ? { id: String(m.team.id), name: m.team.name } : null,
        startDate: m.start_date,
        endDate: m.end_date,
      }
    }),
    // Always [] until the backend has a permission matrix (spec §3). Deny by default.
    permissions: body.permissions.map((p) => ({
      resource: p.resource,
      action: p.action as Me['permissions'][number]['action'],
      scope: p.scope as Me['permissions'][number]['scope'],
    })),
  }
}

function unknownPosition(position: LookupResponse, lc: Lc): Position {
  return {
    key: position.key,
    label: position.label,
    level: lc.type,
    rank: 0,
    canAddSameRank: false,
    presidential: false,
    homeChartScope: 'team',
    holdsTeam: false,
  }
}

// ---------------------------------------------------------------------------
// The Api wrapper
// ---------------------------------------------------------------------------

/** Supabase events that mean "who is signed in may have changed". */
const IDENTITY_EVENTS = new Set(['SIGNED_IN', 'SIGNED_OUT', 'USER_UPDATED'])

export function withSupabaseSession(base: Api, options: SupabaseSessionOptions): Api {
  const { auth, hostedDomain } = options
  const apiUrl = options.apiUrl.replace(/\/+$/, '')
  const fetchFn = options.fetch ?? ((...args: Parameters<typeof fetch>) => fetch(...args))

  // When getMe() itself signs the person out (401/403), it already reports the outcome.
  // The "signed out" event that follows must not trigger another getMe(), which would
  // replace the rejection message with a plain "signed out".
  let quietSignOut = false
  const signOutQuietly = async () => {
    quietSignOut = true
    try {
      await auth.signOut()
    } finally {
      quietSignOut = false
    }
  }

  return {
    ...base,
    signInMethod: 'google',

    async getMe() {
      const { data } = await auth.getSession()
      const token = data.session?.access_token
      if (!token) return null

      const response = await fetchFn(`${apiUrl}/api/v1/me`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (response.status === 401) {
        // Expired or revoked: back to the sign-in page (§9). No separate "expired" page.
        await signOutQuietly()
        return null
      }
      if (response.status === 403) {
        await signOutQuietly()
        throw new SignInRejectedError()
      }
      if (!response.ok) throw new Error(`GET /api/v1/me failed with HTTP ${response.status}`)

      const body = (await response.json()) as MeResponse
      const { positions } = await base.getReferenceData()
      return meFromResponse(body, positions)
    },

    async signIn() {
      const queryParams: Record<string, string> = { prompt: 'select_account' }
      if (hostedDomain) queryParams.hd = hostedDomain
      const { error } = await auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: options.redirectTo ?? `${window.location.origin}/sign-in`,
          queryParams,
        },
      })
      if (error) throw error
      // On success the browser is already leaving for Google; nothing else to do here.
    },

    async signOut() {
      await auth.signOut()
    },

    onSessionChange(listener) {
      const { data } = auth.onAuthStateChange((event) => {
        if (IDENTITY_EVENTS.has(event) && !quietSignOut) listener()
      })
      return () => data.subscription.unsubscribe()
    },
  }
}
