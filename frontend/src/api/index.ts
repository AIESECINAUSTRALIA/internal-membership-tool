/**
 * THE ONE PLACE the app chooses its data source.
 *
 * VITE_AUTH_MODE picks how people sign in (see docs/auth.md and `authMode.ts`):
 * - `mock`: the development sign-in button and personas below. No backend.
 *   The default for the dev server and tests only.
 * - `supabase`: real "Sign in with Google" (aiesec.net), checked by the backend's
 *   `GET /api/v1/me`. The default for production builds. Other data still comes from
 *   the mock until its endpoints exist.
 *
 * The mock never grants real access: it lives only in the browser, and the backend
 * only trusts Supabase-signed tokens.
 *
 * To switch the rest of the data to the real backend: write an `Api` implementation
 * (see `types.ts`) that calls it, and use it in place of `createMockApi(...)` below.
 */
import { createSupabaseClient } from '../auth/supabaseClient'
import { pickAuthMode, type AuthMode } from './authMode'
import type { Api } from './types'
import { createMockApi } from './mock/mockApi'
import { PERSONAS, type PersonaKey } from './mock/seed'
import { withSupabaseSession } from './supabaseSession'

export const authMode: AuthMode = pickAuthMode(import.meta.env)

/** Development only: `/sign-in?as=tl` signs in as that persona. Removed with the mock. */
function personaFromUrl(): PersonaKey | undefined {
  const requested = new URLSearchParams(window.location.search).get('as')
  return requested && requested in PERSONAS ? (requested as PersonaKey) : undefined
}

function createApi(): Api {
  if (authMode === 'supabase') {
    return withSupabaseSession(createMockApi(), {
      auth: createSupabaseClient().auth,
      apiUrl: import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
      hostedDomain: import.meta.env.VITE_GOOGLE_HOSTED_DOMAIN || undefined,
    })
  }
  return createMockApi({ persona: personaFromUrl() })
}

export const api: Api = createApi()

export type { Api } from './types'
