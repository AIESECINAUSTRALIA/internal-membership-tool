import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { useApi } from '../api/ApiContext'
import type { Me } from '../api/types'
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

  useEffect(() => {
    let cancelled = false
    api.getMe().then((result) => {
      if (cancelled) return
      setMe(result)
      setStatus('ready')
    })
    return () => {
      cancelled = true
    }
  }, [api])

  const signIn = useCallback(async () => {
    await api.signIn()
    setMe(await api.getMe())
  }, [api])

  const signOut = useCallback(async () => {
    await api.signOut()
    setMe(null)
  }, [api])

  const value = useMemo<AuthState>(() => {
    const today = todayIso()
    return {
      status,
      me,
      actor: me ? actorFromMe(me, today) : null,
      allocated: me ? hasActiveMembership(me, today) : false,
      signIn,
      signOut,
      setMe,
    }
  }, [status, me, signIn, signOut])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
