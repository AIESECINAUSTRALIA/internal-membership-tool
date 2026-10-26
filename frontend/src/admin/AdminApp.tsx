import { Navigate, Route, Routes } from 'react-router-dom'

import { RequirePermission } from '../auth/guards'
import { PageMessage } from '../components/PageMessage'
import { AdminSignInPage } from './AdminSignInPage'
import { AdminShell } from './AdminShell'
import { RedirectIfSignedInAdmin, RequireAdminConsole } from './guards'
import { AdminAuditingPage } from './pages/AdminAuditingPage'
import { AdminLcsPage } from './pages/AdminLcsPage'
import { AdminPeoplePage } from './pages/AdminPeoplePage'

const notAvailable = (
  <PageMessage title="Page not available">You don&rsquo;t have access to this screen.</PageMessage>
)

/**
 * The Admin console (spec §2A.2): a separate area of the app, mounted at `/admin/*`,
 * with its own sign-in and its own guard (`RequireAdminConsole`) — entirely apart from
 * the main app's `RequireAllocated` tree in `App.tsx`. A normal user never sees a link
 * to this; reaching it means typing the address.
 *
 * Only LCs, People and Auditing are built (see `adminNavConfig.ts` for the rest, which
 * are ticketed separately). Each screen also needs its own `manage`/`view` grant, same
 * as the main app's per-route `RequirePermission`.
 */
export function AdminApp() {
  return (
    <Routes>
      <Route element={<RedirectIfSignedInAdmin />}>
        <Route path="sign-in" element={<AdminSignInPage />} />
      </Route>
      <Route element={<RequireAdminConsole />}>
        <Route element={<AdminShell />}>
          <Route index element={<Navigate to="lcs" replace />} />
          <Route element={<RequirePermission resource="lc" action="manage" fallback={notAvailable} />}>
            <Route path="lcs" element={<AdminLcsPage />} />
          </Route>
          <Route element={<RequirePermission resource="person" action="manage" fallback={notAvailable} />}>
            <Route path="people" element={<AdminPeoplePage />} />
          </Route>
          <Route element={<RequirePermission resource="audit_log" action="view" fallback={notAvailable} />}>
            <Route path="auditing" element={<AdminAuditingPage />} />
          </Route>
          <Route path="*" element={<PageMessage title="Page not found">This page doesn&rsquo;t exist.</PageMessage>} />
        </Route>
      </Route>
    </Routes>
  )
}
