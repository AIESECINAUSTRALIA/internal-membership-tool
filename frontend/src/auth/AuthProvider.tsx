import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { useApi } from '../api/ApiContext'
import { SignInRejectedError } from '../api/supabaseSession'
import type { Api, Me } from '../api/types'
import { AuthContext, type AuthState } from './authContext'
import { actorFromMe, hasActiveMembership } from './permissions'
import { todayIso } from './today'

/**
 * Holds the signed-in person for the whole app. Everything else (nav, guards, page
 * actions) is derived from this one `me` payload, so the UI always agrees with what
 * the server resolved (§2A.9).
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const api = useApi()
  const [me, setMe] = useState<Me | null>(null)
  const [status, setStatus] = useState<AuthState['status']>('loading')
  const [error, setError] = useState<string | null>(null)
  // Several loads can overlap (page load + "signed in" event). Only the newest one wins:
  // each load takes a ticket, and a result is applied only if its ticket is still the latest.
  const latestTicket = useRef(0)
  const reload = useRef<() => Promise<void>>(async () => {})

  useEffect(() => {
    let mounted = true
    const load = async () => {
      const ticket = ++latestTicket.current
      const { result, failure } = await fetchMe(api)
      if (!mounted || ticket !== latestTicket.current) return
      setMe(result)
      // A later "signed out" event loads `null` without an error: keep the message until
      // the person tries again, or actually gets in.
      if (failure || result) setError(failure)
      setStatus('ready')
    }
    reload.current = load
    void load()
    const unsubscribe = api.onSessionChange?.(() => void load())
    return () => {
      mounted = false
      unsubscribe?.()
    }
  }, [api])

  const signIn = useCallback(async () => {
    setError(null)
    await api.signIn()
    await reload.current()
  }, [api])

  const signOut = useCallback(async () => {
    await api.signOut()
    latestTicket.current++ // a load still in flight must not sign the person back in
    setMe(null)
  }, [api])

  const value = useMemo<AuthState>(() => {
    const today = todayIso()
    return {
      status,
      me,
      actor: me ? actorFromMe(me, today) : null,
      allocated: me ? hasActiveMembership(me, today) : false,
      error,
      signIn,
      signOut,
      setMe,
    }
  }, [status, me, error, signIn, signOut])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

/** `api.getMe()`, with failures turned into a message for the sign-in page. */
async function fetchMe(api: Api): Promise<{ result: Me | null; failure: string | null }> {
  try {
    return { result: await api.getMe(), failure: null }
  } catch (e) {
    return {
      result: null,
      failure:
        e instanceof SignInRejectedError
          ? e.message
          : 'We could not check your sign-in right now. Please try again in a moment.',
    }
  }
}
