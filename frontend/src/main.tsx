import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
// Fonts are self-hosted through @fontsource (no CDN). See theme/theme.ts for how they are used.
import '@fontsource/lato/400.css'
import '@fontsource/lato/700.css'
import '@fontsource/marcellus'

import App from './App'
import { AppProviders } from './AppProviders'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AppProviders>
        <App />
      </AppProviders>
    </BrowserRouter>
  </StrictMode>,
)
