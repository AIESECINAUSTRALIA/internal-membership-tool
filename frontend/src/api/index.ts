/**
 * THE ONE PLACE the app chooses its data source.
 *
 * VITE_AUTH_MODE picks how people sign in (see docs/auth.md and `authMode.ts`):
 * - `mock`: the development sign-in button and personas below. Everything comes from
 *   the in-browser mock; the backend is never called. The default for the dev server
 *   and tests only.
 * - `supabase`: real "Sign in with Google" (aiesec.net), checked by the backend's
 *   `GET /api/v1/me`. The default for production builds. The membership-summary
 *   methods (listMembers, addMember, getMembershipDetail, extendTerm, moveToTeam) and
 *   the LCs/terms/teams in getReferenceData come from the real backend
 *   (`http/httpApi.ts`, ticket DEV-0043, spec §2A.5), sent with the Supabase access
 *   token. Everything else still comes from the mock until its endpoints exist.
 *
 * The mock never grants real access: it lives only in the browser, and the backend
 * only trusts Supabase-signed tokens.
 */
import { createSupabaseClient } from '../auth/supabaseClient'
import { pickAuthMode, type AuthMode } from './authMode'
import { createHttpApi } from './http/httpApi'
import { createMockApi } from './mock/mockApi'
import { PERSONAS, type PersonaKey } from './mock/seed'
import { bearerFrom, withSupabaseSession } from './supabaseSession'
import type { Api } from './types'

export const authMode: AuthMode = pickAuthMode(import.meta.env)

/** Development only: `/sign-in?as=tl` signs in as that persona. Removed with the mock. */
function personaFromUrl(): PersonaKey | undefined {
  const requested = new URLSearchParams(window.location.search).get('as')
  return requested && requested in PERSONAS ? (requested as PersonaKey) : undefined
}

function createApi(): Api {
  if (authMode === 'supabase') {
    const { auth } = createSupabaseClient()
    // '' = same origin. Locally, VITE_API_URL points at the backend container.
    const apiUrl = import.meta.env.VITE_API_URL ?? ''
    const mock = createMockApi()
    const httpApi = createHttpApi({
      getAuthHeaders: bearerFrom(auth),
      baseUrl: apiUrl,
      fallback: mock,
    })
    return withSupabaseSession(httpApi, {
      auth,
      apiUrl,
      hostedDomain: import.meta.env.VITE_GOOGLE_HOSTED_DOMAIN || undefined,
      // Positions still come from the mock. Taking them straight from it keeps
      // sign-in to one backend call (/me): a failing reference endpoint can't
      // lock anyone out.
      getPositions: async () => (await mock.getReferenceData()).positions,
    })
  }
  return createMockApi({ persona: personaFromUrl() })
}

export const api: Api = createApi()

export type { Api } from './types'
