/**
 * Route guards for the Admin console (spec §2A.2): its own entry point, kept separate
 * from `auth/guards.tsx`'s `RequireAllocated` tree. There is no separate identity
 * provider — "separate login" means a separate entry point and session that demands
 * the `admin_console` permission, still via the same managed Google sign-in (§9) and
 * the same `me` payload as the main app.
 *
 * As with the main app's guards, these only decide what the UI SHOWS. The server
 * enforces access on every request and denies by default.
 */
import { Navigate, Outlet } from 'react-router-dom'

import { useAuth } from '../auth/authContext'
import { can } from '../auth/permissions'
import { LoadingScreen } from '../components/LoadingScreen'
import { PageMessage } from '../components/PageMessage'

/** Signed in AND holds `admin_console:view`. Otherwise: the admin sign-in page, or a
 * plain denial — never the main app's "not allocated" page, which is unrelated. */
export function RequireAdminConsole() {
  const { status, me } = useAuth()
  if (status === 'loading') return <LoadingScreen />
  if (!me) return <Navigate to="/admin/sign-in" replace />
  if (!can(me.permissions, 'admin_console', 'view')) {
    return (
      <PageMessage title="Admin console">
        You don&rsquo;t have access to the admin console. If you think you should, ask someone in your MC.
      </PageMessage>
    )
  }
  return <Outlet />
}

/** The admin sign-in page: anyone already signed in is sent onward, whether or not
 * they hold the admin permission — `RequireAdminConsole` decides what they see there. */
export function RedirectIfSignedInAdmin() {
  const { status, me } = useAuth()
  if (status === 'loading') return <LoadingScreen />
  if (me) return <Navigate to="/admin" replace />
  return <Outlet />
}
