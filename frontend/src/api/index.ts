/**
 * THE ONE PLACE the app chooses its data source.
 *
 * VITE_AUTH_MODE picks how people sign in (see docs/auth.md and `authMode.ts`):
 * - `mock`: the development sign-in button and personas below.
 *   The default for the dev server and tests only.
 * - `supabase`: real "Sign in with Google" (aiesec.net), checked by the backend's
 *   `GET /api/v1/me`. The default for production builds.
 *
 * The mock never grants real access: it lives only in the browser, and the backend
 * only trusts Supabase-signed tokens.
 *
 * Data: membership-summary methods (listMembers, addMember, getMembershipDetail,
 * extendTerm, moveToTeam) call the real FastAPI backend through `createHttpApi`
 * (Ticket DEV-0043, Spec §2A.5). Everything else still goes through the mock until
 * the corresponding backend tickets land.
 *
 * AUTH stub: `httpApi` still sends `X-Actor-Email`, read from `actorEmailRef`
 * (updated by `AppProviders` once `getMe()` resolves). The backend now only accepts
 * a Supabase bearer token, so `headers()` in `http/httpApi.ts` must switch to that.
 */
import { createSupabaseClient } from '../auth/supabaseClient'
import { pickAuthMode, type AuthMode } from './authMode'
import type { Api } from './types'
import { createHttpApi } from './http/httpApi'
import { PERSONAS, type PersonaKey } from './mock/seed'
import { withSupabaseSession } from './supabaseSession'

export const authMode: AuthMode = pickAuthMode(import.meta.env)

/** Development only: `/sign-in?as=tl` signs in as that persona. Removed with the mock. */
function personaFromUrl(): PersonaKey | undefined {
  const requested = new URLSearchParams(window.location.search).get('as')
  return requested && requested in PERSONAS ? (requested as PersonaKey) : undefined
}

/**
 * Mutable ref updated by `AppProviders` after auth resolves.
 * The httpApi reads this on every request, so it always uses the latest email.
 */
export const actorEmailRef: { current: string | null } = { current: null }

function createApi(): Api {
  if (authMode === 'supabase') {
    const httpApi = createHttpApi({ getActorEmail: () => actorEmailRef.current })
    return withSupabaseSession(httpApi, {
      auth: createSupabaseClient().auth,
      apiUrl: import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
      hostedDomain: import.meta.env.VITE_GOOGLE_HOSTED_DOMAIN || undefined,
    })
  }
  return createHttpApi({
    getActorEmail: () => actorEmailRef.current,
    mockOptions: { persona: personaFromUrl() },
  })
}

export const api: Api = createApi()

export type { Api } from './types'
