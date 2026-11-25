/**
 * THE ONE PLACE the app chooses its data source.
 *
 * VITE_AUTH_MODE picks how people sign in (see docs/auth.md and `authMode.ts`):
 * - `mock`: the development sign-in button and personas below. Everything comes from
 *   the in-browser mock; the backend is never called. The default for the dev server
 *   and tests only.
 * - `expa`: real "Sign in with EXPA", checked by the backend's
 *   `GET /api/v1/me`. Always used in production builds. The membership-summary
 *   methods (listMembers, addMember, getMembershipDetail, extendTerm, moveToTeam) and
 *   the LCs/terms/teams in getReferenceData come from the real backend
 *   (`http/httpApi.ts`, ticket DEV-0043, spec §2A.5), as do Profile's custom fields
 *   and position history (getMyCustomFields, updateMyCustomFields,
 *   getMyMembershipHistory, ticket DEV-0045, spec §2A.9).
 *   Other implemented HTTP API methods, including the Admin console endpoints,
 *   also use the real backend. Everything else still comes from the mock until its
 *   endpoints exist.
 *
 *   Authentication uses the backend's HttpOnly `__session` cookie, which the
 *   browser sends with API requests. The frontend never receives or stores
 *   EXPA access tokens.
 *
 * The mock never grants real access: it lives only in the browser, and the backend
 * only accepts valid server-side sessions established through EXPA OAuth.
 */
import { pickAuthMode, type AuthMode } from './authMode'
import { createHttpApi } from './http/httpApi'
import { createMockApi } from './mock/mockApi'
import { PERSONAS, type PersonaKey } from './mock/seed'
import type { Api } from './types'

import { withExpaSession } from './expaSession'
import { createSessionEvents } from './sessionEvents'

export const authMode: AuthMode = pickAuthMode(import.meta.env)

/** Development only: `/sign-in?as=tl` signs in as that persona. Removed with the mock. */
function personaFromUrl(): PersonaKey | undefined {
  const requested = new URLSearchParams(window.location.search).get('as')
  return requested && requested in PERSONAS ? (requested as PersonaKey) : undefined
}


function createApi(): Api {
  if (authMode === 'expa') {
    const apiUrl = ''
    const mock = createMockApi()
    const sessionEvents = createSessionEvents()

    const httpApi = createHttpApi({
      baseUrl: apiUrl,
      fallback: mock,
      onUnauthorized: sessionEvents.notify,
    })

    return withExpaSession(httpApi, {
      apiUrl,
      // Positions still come from the mock. Taking them straight from it keeps
      // sign-in to one backend call (/me): a failing reference endpoint can't
      // lock anyone out.
      getPositions: async () => (await mock.getReferenceData()).positions,
      subscribeToSessionChanges: sessionEvents.subscribe,
    })
  }

  return createMockApi({ persona: personaFromUrl() })
}

export const api: Api = createApi()
export type { Api } from './types'
