import { CssBaseline, ThemeProvider } from '@mui/material'
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider'
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs'
import 'dayjs/locale/en-au'
import type { ReactNode } from 'react'

import { ApiProvider } from './api/ApiContext'
import { ReferenceDataProvider } from './api/ReferenceDataContext'
import type { Api } from './api/types'
import { AuthProvider } from './auth/AuthProvider'
import { theme } from './theme/theme'

/** Everything the app needs around the routes. Tests reuse it with a fake `api`. */
export function AppProviders({ api, children }: { api?: Api; children: ReactNode }) {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <LocalizationProvider dateAdapter={AdapterDayjs} adapterLocale="en-au">
        <ApiProvider api={api}>
          <AuthProvider>
            <ReferenceDataProvider>{children}</ReferenceDataProvider>
          </AuthProvider>
        </ApiProvider>
      </LocalizationProvider>
    </ThemeProvider>
  )
}
