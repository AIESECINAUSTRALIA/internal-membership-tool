import { Box } from '@mui/material'
import { useState } from 'react'
import { Outlet } from 'react-router-dom'

import { Header } from './Header'
import { Sidebar } from './Sidebar'

/**
 * The signed-in app frame: sidebar navigation on the left, a slim header on top, the
 * page below it. Content fills the available width — pages that need a readable line
 * length (body text) already cap it themselves, e.g. `sx={{ maxWidth: '65ch' }}` on
 * description text, so a table or grid isn't left with unused space on a wide screen.
 */
export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      {/* Keyboard users can jump past the menu (WCAG 2.4.1). Visible only when focused. */}
      <Box
        component="a"
        href="#main-content"
        sx={{
          position: 'absolute',
          left: 8,
          top: -80,
          zIndex: 'tooltip',
          px: 2,
          py: 1,
          bgcolor: 'background.paper',
          color: 'text.primary',
          fontWeight: 700,
          borderRadius: 1,
          '&:focus': { top: 8 },
        }}
      >
        Skip to main content
      </Box>
      <Sidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
      <Box sx={{ flexGrow: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <Header onMenuClick={() => setMobileOpen(true)} />
        <Box
          component="main"
          id="main-content"
          tabIndex={-1}
          sx={{ flexGrow: 1, px: { xs: 2, md: 4 }, pt: 4, pb: 8, '&:focus': { outline: 'none' } }}
        >
          <Outlet />
        </Box>
      </Box>
    </Box>
  )
}
