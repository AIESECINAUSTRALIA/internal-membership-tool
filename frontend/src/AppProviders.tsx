import { CssBaseline, ThemeProvider } from '@mui/material'
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider'
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs'
import 'dayjs/locale/en-au'
import { useEffect, type ReactNode } from 'react'

import { ApiProvider } from './api/ApiContext'
import { actorEmailRef } from './api/index'
import { ReferenceDataProvider } from './api/ReferenceDataContext'
import type { Api } from './api/types'
import { AuthProvider } from './auth/AuthProvider'
import { useAuth } from './auth/authContext'
import { theme } from './theme/theme'

/**
 * Keeps the shared `actorEmailRef` in sync with the signed-in user so the
 * httpApi can attach `X-Actor-Email` on every request without coupling to
 * React's render cycle. This component is intentionally minimal — it just
 * reads from the auth context and writes to the ref.
 */
function ActorEmailSync() {
  const { me } = useAuth()
  useEffect(() => {
    actorEmailRef.current = me?.person.email ?? null
  }, [me])
  return null
}

/** Everything the app needs around the routes. Tests reuse it with a fake `api`. */
export function AppProviders({ api, children }: { api?: Api; children: ReactNode }) {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <LocalizationProvider dateAdapter={AdapterDayjs} adapterLocale="en-au">
        <ApiProvider api={api}>
          <AuthProvider>
            <ActorEmailSync />
            <ReferenceDataProvider>{children}</ReferenceDataProvider>
          </AuthProvider>
        </ApiProvider>
      </LocalizationProvider>
    </ThemeProvider>
  )
}
