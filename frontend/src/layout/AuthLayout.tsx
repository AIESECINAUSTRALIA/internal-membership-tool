import { Box, Typography } from '@mui/material'
import type { ReactNode } from 'react'

/**
 * Frame for the pages you see BEFORE you are in: sign-in and not-allocated.
 *
 * A full-height split. Left: the AIESEC blue panel carrying the product title. Right: a
 * white column with the page's own content and an optional footer note. Below 900px the
 * panel becomes a block above the form.
 *
 * WHITE TEXT ON BLUE, AN EXCEPTION: white on AIESEC blue is 3.98:1. That fails AA for normal
 * text (4.5:1, and the reason the rest of the app uses black on blue, spec §2A.11), but
 * passes AA for LARGE text (3:1). So EVERY line of the title must stay at least 24px, on
 * every screen size. Never put smaller white text on this panel.
 *
 * The title is plain text (not a heading) so each page can own its single <h1>.
 */
export function AuthLayout({ children, footer }: { children: ReactNode; footer?: ReactNode }) {
  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: { xs: 'column', md: 'row' },
        bgcolor: 'background.paper',
      }}
    >
      <Box
        component="header"
        sx={{
          bgcolor: 'primary.main',
          color: 'common.white',
          flex: { md: '0 0 45%' },
          display: 'flex',
          alignItems: 'center',
          px: { xs: 3, md: 6 },
          py: { xs: 5, md: 6 },
        }}
      >
        <Typography component="p" sx={{ textWrap: 'balance' }}>
          <Typography
            variant="display"
            component="span"
            sx={{ display: 'block', fontSize: { xs: '2.5rem', md: '3.75rem' }, lineHeight: 1.1 }}
          >
            AIESEC in Australia
          </Typography>
          <Typography
            variant="displaySm"
            component="span"
            sx={{ display: 'block', mt: 1.5, fontSize: { xs: '1.5rem', md: '2.25rem' } }}
          >
            Internal Membership Tool
          </Typography>
        </Typography>
      </Box>

      <Box
        sx={{
          flex: 1,
          minWidth: 0,
          display: 'flex',
          justifyContent: 'center',
          px: { xs: 3, md: 8 },
          py: 4,
        }}
      >
        {/* One column, so the form and the footer note share a left edge. */}
        <Box sx={{ width: '100%', maxWidth: 400, display: 'flex', flexDirection: 'column' }}>
          <Box component="main" sx={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', py: 6 }}>
            {children}
          </Box>
          {footer && <Box sx={{ color: 'text.secondary' }}>{footer}</Box>}
        </Box>
      </Box>
    </Box>
  )
}
