/**
 * Route guards, driven entirely by the `me` payload.
 *
 * These decide which SCREEN to show. They are a convenience: the server enforces access
 * on every request and denies by default (§2A).
 */
import { Navigate, Outlet } from 'react-router-dom'

import type { Action, Scope } from '../api/types'
import { LoadingScreen } from '../components/LoadingScreen'
import { useAuth } from './authContext'
import { hasMinScope } from './permissions'

/** Signed in AND allocated. Otherwise: sign in, or the not-allocated page. */
export function RequireAllocated() {
  const { status, me, allocated } = useAuth()
  if (status === 'loading') return <LoadingScreen />
  if (!me) return <Navigate to="/sign-in" replace />
  if (!allocated) return <Navigate to="/not-allocated" replace />
  return <Outlet />
}

/** Sign-in page: people who are already in are sent onward. */
export function RedirectIfSignedIn() {
  const { status, me, allocated } = useAuth()
  if (status === 'loading') return <LoadingScreen />
  if (me) return <Navigate to={allocated ? '/' : '/not-allocated'} replace />
  return <Outlet />
}

/** Not-allocated page: only for signed-in people with no active membership. */
export function RequireUnallocated() {
  const { status, me, allocated } = useAuth()
  if (status === 'loading') return <LoadingScreen />
  if (!me) return <Navigate to="/sign-in" replace />
  if (allocated) return <Navigate to="/" replace />
  return <Outlet />
}

/** A page that needs one permission, at least `minScope` wide (default 'own', i.e. any
 * scope qualifies — unchanged from before this prop existed). Without it, the person
 * sees "not available". */
export function RequirePermission({
  resource,
  action,
  minScope = 'own',
  fallback,
}: {
  resource: string
  action: Action
  minScope?: Scope
  fallback: React.ReactNode
}) {
  const { me } = useAuth()
  if (!me || !hasMinScope(me.permissions, resource, action, minScope)) return <>{fallback}</>
  return <Outlet />
}
