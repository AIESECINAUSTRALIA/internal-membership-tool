/**
 * THE ONE PLACE the app chooses its data source.
 *
 * To switch to the real backend: write an `Api` implementation (see `types.ts`) that
 * calls it, and replace `createMockApi(...)` below with it. Nothing else changes.
 */
import type { Api } from './types'
import { createMockApi } from './mock/mockApi'
import { PERSONAS, type PersonaKey } from './mock/seed'

/** Development only: `/sign-in?as=tl` signs in as that persona. Removed with the mock. */
function personaFromUrl(): PersonaKey | undefined {
  const requested = new URLSearchParams(window.location.search).get('as')
  return requested && requested in PERSONAS ? (requested as PersonaKey) : undefined
}

export const api: Api = createMockApi({ persona: personaFromUrl() })

export type { Api } from './types'
