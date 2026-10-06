import { Route, Routes } from 'react-router-dom'

import { RedirectIfSignedIn, RequireAllocated, RequirePermission, RequireUnallocated } from './auth/guards'
import { PageMessage } from './components/PageMessage'
import { AppShell } from './layout/AppShell'
import { DataPage } from './pages/DataPage'
import { HomePage } from './pages/HomePage'
import { MembershipPage } from './pages/MembershipPage'
import { NotAllocatedPage } from './pages/NotAllocatedPage'
import { ProfilePage } from './pages/ProfilePage'
import { SettingsPage } from './pages/SettingsPage'
import { SignInPage } from './pages/SignInPage'
import { TrackingPage } from './pages/TrackingPage'

const notAvailable = (
  <PageMessage title="Page not available">
    You don&rsquo;t have access to this page. If you think you should, ask someone in your EB or MC.
  </PageMessage>
)

/**
 * Routes. Guards decide which screen a person may reach from their resolved `me`
 * payload (spec §2A). The server still enforces access on every request.
 *
 * Tracking, Data and Settings are scaffolds: real layout and controls, but the KPI
 * catalog they need (spec §4.3) is still a TODO, so their data stays "No data exists"
 * (see each page's own doc comment). Each route needs the same permission as its menu
 * item in `navigation/navConfig.ts`, and the same minimum scope, where the nav item
 * sets one.
 */
export default function App() {
  return (
    <Routes>
      <Route element={<RedirectIfSignedIn />}>
        <Route path="/sign-in" element={<SignInPage />} />
      </Route>
      <Route element={<RequireUnallocated />}>
        <Route path="/not-allocated" element={<NotAllocatedPage />} />
      </Route>
      <Route element={<RequireAllocated />}>
        <Route element={<AppShell />}>
          <Route index element={<HomePage />} />
          <Route element={<RequirePermission resource="membership" action="view" fallback={notAvailable} />}>
            <Route path="membership" element={<MembershipPage />} />
          </Route>
          <Route element={<RequirePermission resource="kpi_record" action="view" fallback={notAvailable} />}>
            <Route path="tracking" element={<TrackingPage />} />
          </Route>
          <Route element={<RequirePermission resource="analytics_report" action="view" minScope="team" fallback={notAvailable} />}>
            <Route path="data" element={<DataPage />} />
          </Route>
          <Route path="settings" element={<SettingsPage />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="*" element={<PageMessage title="Page not found">This page doesn&rsquo;t exist.</PageMessage>} />
        </Route>
      </Route>
    </Routes>
  )
}
