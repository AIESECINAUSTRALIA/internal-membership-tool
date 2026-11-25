/**
 * Real sign-in through EXPA OAuth (spec §9, docs/auth.md).
 *
 * The browser visits the backend's login endpoint, which handles the
 * OAuth exchange and redirects back with a server-side session cookie.
 * This wrapper replaces the authentication methods of the underlying API.
 */
import type { FunctionRef, Lc, Me, MembershipView, Position } from './types'
import type { Api } from './types'


export interface ExpaSessionOptions {
  apiUrl: string
  fetch?: typeof fetch
  navigate?: (url: string) => void
  getPositions?: () => Promise<Position[]>
  subscribeToSessionChanges?: (listener: () => void) => () => void
}

/**
 * Adds real EXPA authentication to an existing API implementation.
 *
 * The backend handles OAuth and issues an HttpOnly session cookie.
 * The frontend never receives or stores EXPA access tokens.
 */
export function withExpaSession(
  base: Api,
  options: ExpaSessionOptions,
): Api {
  const apiUrl = options.apiUrl.replace(/\/+$/, '')
  const fetcher = options.fetch ?? globalThis.fetch
  const navigate =
    options.navigate ?? ((url: string) => window.location.assign(url))

  const getPositions =
    options.getPositions ??
    (async () => (await base.getReferenceData()).positions)

  return {
    ...base,
    signInMethod: 'expa',

    async getMe() {
      const response = await fetcher(`${apiUrl}/api/v1/me`, {
        credentials: 'same-origin',
        cache: 'no-store',
      })

      if (response.status === 401) {
        return null
      }

      if (!response.ok) {
        throw new Error(`Could not load session (${response.status})`)
      }

      const body: MeResponse = await response.json()
      return meFromResponse(body, await getPositions())
    },

    async signIn() {
      navigate(`${apiUrl}/api/v1/auth/login`)
    },

    async signOut() {
      const response = await fetcher(`${apiUrl}/api/v1/auth/logout`, {
        method: 'POST',
        credentials: 'same-origin',
      })

      if (!response.ok) {
        throw new Error(`Could not sign out (${response.status})`)
      }
    },

    onSessionChange: options.subscribeToSessionChanges,
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
    lc: {
      id: number
      name: string
      type: string
      state: string | null
      active: boolean
    }
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
 * If the backend returns no person, the resulting `Me` has no memberships,
 * so the guards show the not-allocated page (§9). Initial sign-ins without
 * an allocation are rejected by the OAuth callback before a session is issued.
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
        }
      : { id: '', firstName: body.email.split('@')[0], lastName: '', email: body.email },
    memberships: body.memberships.map((m): MembershipView => {
      const lc: Lc = {id: String(m.lc.id), name: m.lc.name, type: m.lc.type === 'MC' ? 'mc' : 'lc', state: m.lc.state, active: m.lc.active,}
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
    // Permissions are resolved by the backend across active memberships (spec §3).
    // An empty list grants no permissions.
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
