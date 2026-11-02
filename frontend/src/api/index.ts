/**
 * THE ONE PLACE the app chooses its data source.
 *
 * To switch to the real backend: write an `Api` implementation (see `types.ts`) that
 * calls it, and replace `createMockApi(...)` below with it. Nothing else changes.
 *
 * Partway there: when `VITE_DEV_ACTOR_EMAIL` is set, Profile's two methods (`getMe`,
 * `updateMyCustomFields`) come from the real backend (`http/httpApi.ts`) and everything
 * else stays on the mock. When it is not set, the whole app runs on the mock as before.
 * See docs/frontend.md, "Swapping the mock for the real backend".
 */
import type { Api } from './types'
import { createHttpApi } from './http/httpApi'
import { createMockApi } from './mock/mockApi'
import { PERSONAS, type PersonaKey } from './mock/seed'

/** Development only: `/sign-in?as=tl` signs in as that persona. Removed with the mock. */
function personaFromUrl(): PersonaKey | undefined {
  const requested = new URLSearchParams(window.location.search).get('as')
  return requested && requested in PERSONAS ? (requested as PersonaKey) : undefined
}

function createApi(): Api {
  const mock = createMockApi({ persona: personaFromUrl() })
  const actorEmail = import.meta.env.VITE_DEV_ACTOR_EMAIL as string | undefined
  if (!actorEmail) return mock

  const http = createHttpApi({
    baseUrl: (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000',
    actorEmail,
  })
  return {
    ...mock,
    // Sign-in and sign-out still go through the mock until ticket 7, so ask the
    // backend who you are only while the mock says you're signed in.
    getMe: async () => ((await mock.getMe()) ? http.getMe() : null),
    updateMyCustomFields: http.updateMyCustomFields,
  }
}

export const api: Api = createApi()

export type { Api } from './types'
