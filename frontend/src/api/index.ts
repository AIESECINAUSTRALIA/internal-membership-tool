/**
 * THE ONE PLACE the app chooses its data source.
 *
 * Membership-summary methods (listMembers, addMember, getMembershipDetail,
 * extendTerm, moveToTeam) now call the real FastAPI backend (Ticket DEV-0043,
 * Spec §2A.5). Everything else still goes through the mock until the
 * corresponding backend tickets land.
 *
 * AUTH stub: The backend uses `X-Actor-Email` (see `backend/app/api/deps.py`).
 * `actorEmailRef` is updated by `AppProviders` once `getMe()` resolves.
 * Ticket 7 (Google OAuth) will replace `actorEmailRef` with a JWT bearer token
 * — only the `headers()` function in `http/httpApi.ts` needs to change then.
 */
import type { Api } from './types'
import { createHttpApi } from './http/httpApi'
import { PERSONAS, type PersonaKey } from './mock/seed'

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

export const api: Api = createHttpApi({
  getActorEmail: () => actorEmailRef.current,
  mockOptions: { persona: personaFromUrl() },
})

export type { Api } from './types'
