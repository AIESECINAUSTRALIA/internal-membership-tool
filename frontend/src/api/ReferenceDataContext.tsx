import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { useApi } from './ApiContext'
import type { ReferenceData } from './types'
import { useAuth } from '../auth/authContext'

interface ReferenceDataValue {
  reference: ReferenceData | null
  /** Re-fetches, replacing the cached value once it resolves. Call after a mutation
   * that can change reference data (e.g. adding a member can change who leads a team,
   * `Team.leader`) — reference data otherwise rarely changes within a session. */
  invalidate: () => void
}

const ReferenceDataContext = createContext<ReferenceDataValue>({ reference: null, invalidate: () => {} })

/**
 * Fetches reference data (LCs, positions, functions, terms, teams) once and shares it
 * with every page that needs it (Data, Settings, Membership), instead of each page
 * fetching its own copy on every visit. Only fetched once signed in — the real backend
 * requires auth — and re-fetched on sign-in (nested inside `AuthProvider` so it can see
 * `me`, but keyed on signed-in/out rather than `me` itself so a profile edit, which also
 * calls `setMe`, doesn't trigger a spurious re-fetch).
 */
export function ReferenceDataProvider({ children }: { children: ReactNode }) {
  const api = useApi()
  const { me } = useAuth()
  const signedIn = me !== null
  const [reference, setReference] = useState<ReferenceData | null>(null)
  // Guards against a stale in-flight fetch overwriting a newer one (e.g. invalidate()
  // called again before the previous fetch resolved, or a sign-out during the fetch).
  const requestId = useRef(0)

  const fetchNow = useCallback(() => {
    const id = ++requestId.current
    api.getReferenceData().then((data) => {
      if (id === requestId.current) setReference(data)
    })
  }, [api])

  useEffect(() => {
    if (signedIn) {
      fetchNow()
    } else {
      // Discards any fetch still in flight from the previous session; the `reference:
      // null` below (not a setState call here) is what actually hides stale data.
      requestId.current++
    }
  }, [signedIn, fetchNow])

  // Signed-out consumers always see `null`, even for the instant before the effect
  // above discards a stale in-flight fetch.
  const value = useMemo<ReferenceDataValue>(
    () => ({ reference: signedIn ? reference : null, invalidate: fetchNow }),
    [signedIn, reference, fetchNow],
  )

  return <ReferenceDataContext.Provider value={value}>{children}</ReferenceDataContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useReferenceData(): ReferenceDataValue {
  return useContext(ReferenceDataContext)
}
