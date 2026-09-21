/**
 * Route guards, driven entirely by the `me` payload.
 *
 * These decide which SCREEN to show. They are a convenience: the server enforces access
 * on every request and denies by default (§2A).
 */
import { Navigate, Outlet } from 'react-router-dom'

import type { Action } from '../api/types'
import { LoadingScreen } from '../components/LoadingScreen'
import { useAuth } from './authContext'
import { can } from './permissions'

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

/** A page that needs one permission. Without it, the person sees "not available". */
export function RequirePermission({
  resource,
  action,
  fallback,
}: {
  resource: string
  action: Action
  fallback: React.ReactNode
}) {
  const { me } = useAuth()
  if (!me || !can(me.permissions, resource, action)) return <>{fallback}</>
  return <Outlet />
}
