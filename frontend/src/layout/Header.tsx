import { Avatar, Box, Divider, IconButton, Menu, MenuItem, Typography } from '@mui/material'
import MenuIcon from '@mui/icons-material/Menu'
import { useState } from 'react'
import { Link as RouterLink, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/authContext'
import { actingMembership } from '../auth/permissions'
import { fullName, roleLabel } from '../lib/labels'
import { HEADER_HEIGHT } from './Sidebar'

/** Where the signed-in person sits, e.g. "TL – oGV, USYD". */
function useContextLine(): string {
  const { actor } = useAuth()
  const acting = actor ? actingMembership(actor) : null
  return acting ? `${roleLabel(acting.position, acting.function)}, ${acting.lc.name}` : ''
}

/**
 * Slim header: a menu button on small screens, the person's context, and the profile
 * icon. The profile menu has Profile and Sign out (spec §2A, §2A.9).
 */
export function Header({ onMenuClick }: { onMenuClick: () => void }) {
  const { me, signOut } = useAuth()
  const navigate = useNavigate()
  const contextLine = useContextLine()
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)

  if (!me) return null
  const { firstName, lastName } = me.person
  const initials = `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase()

  const handleSignOut = async () => {
    setAnchor(null)
    await signOut()
    navigate('/sign-in', { replace: true })
  }

  return (
    <Box
      component="header"
      sx={{
        position: 'sticky',
        top: 0,
        zIndex: 'appBar',
        height: HEADER_HEIGHT,
        display: 'flex',
        alignItems: 'center',
        gap: 1,
        px: { xs: 1, md: 4 },
        bgcolor: 'background.paper',
        borderBottom: 1,
        borderColor: 'divider',
      }}
    >
      <IconButton
        aria-label="Open navigation menu"
        onClick={onMenuClick}
        sx={{ display: { md: 'none' } }}
      >
        <MenuIcon />
      </IconButton>
      <Typography sx={{ display: { xs: 'none', sm: 'block' } }} color="text.secondary">
        {contextLine}
      </Typography>
      <Box sx={{ flexGrow: 1 }} />
      <IconButton
        aria-label="Open profile menu"
        aria-haspopup="menu"
        aria-expanded={anchor ? true : undefined}
        onClick={(event) => setAnchor(event.currentTarget)}
      >
        <Avatar sx={{ width: 36, height: 36, fontSize: '0.9375rem' }}>{initials}</Avatar>
      </IconButton>
      <Menu
        anchorEl={anchor}
        open={Boolean(anchor)}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { sx: { minWidth: 240, mt: 1 } } }}
      >
        <Box sx={{ px: 2, py: 1.5 }}>
          <Typography sx={{ fontWeight: 700 }}>
            {fullName(firstName, lastName)}
          </Typography>
          {contextLine && (
            <Typography variant="body2" color="text.secondary">
              {contextLine}
            </Typography>
          )}
        </Box>
        <Divider />
        <MenuItem component={RouterLink} to="/profile" onClick={() => setAnchor(null)}>
          Profile
        </MenuItem>
        <MenuItem onClick={handleSignOut}>Sign out</MenuItem>
      </Menu>
    </Box>
  )
}
