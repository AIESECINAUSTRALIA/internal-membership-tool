import { createContext, useContext } from 'react'

import type { Actor } from './permissions'
import type { Me } from '../api/types'

export interface AuthState {
  /** 'loading' until the first `getMe()` answers. */
  status: 'loading' | 'ready'
  /** The signed-in person, or null when signed out or the session expired (§2A.3). */
  me: Me | null
  /** Derived from `me`: their ACTIVE memberships. Null when signed out. */
  actor: Actor | null
  /** False when signed in but with no active membership: sees the not-allocated page (§9). */
  allocated: boolean
  signIn: () => Promise<void>
  signOut: () => Promise<void>
  /** Replace `me` after an edit, so every page sees the new values. */
  setMe: (me: Me) => void
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>')
  return value
}
