import { Box } from '@mui/material'
import { useState } from 'react'
import { Outlet } from 'react-router-dom'

import { AdminHeader } from './AdminHeader'
import { AdminSidebar } from './AdminSidebar'

/**
 * The signed-in Admin console frame (spec §2A.2): same split as the main app's
 * `AppShell` (sidebar, slim header, page below it), kept as its own component tree so
 * the console stays a genuinely separate area rather than a mode of the main shell.
 */
export function AdminShell() {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      {/* Keyboard users can jump past the menu (WCAG 2.4.1). Visible only when focused. */}
      <Box
        component="a"
        href="#admin-main-content"
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
      <AdminSidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
      <Box sx={{ flexGrow: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <AdminHeader onMenuClick={() => setMobileOpen(true)} />
        <Box
          component="main"
          id="admin-main-content"
          tabIndex={-1}
          sx={{ flexGrow: 1, px: { xs: 2, md: 4 }, pt: 4, pb: 8, '&:focus': { outline: 'none' } }}
        >
          <Outlet />
        </Box>
      </Box>
    </Box>
  )
}
