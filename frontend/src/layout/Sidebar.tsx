import { Box, Drawer, List, ListItem, ListItemButton, ListItemIcon, ListItemText } from '@mui/material'
import HomeOutlined from '@mui/icons-material/HomeOutlined'
import GroupsOutlined from '@mui/icons-material/GroupsOutlined'
import PlaylistAddCheckOutlined from '@mui/icons-material/PlaylistAddCheckOutlined'
import InsightsOutlined from '@mui/icons-material/InsightsOutlined'
import SettingsOutlined from '@mui/icons-material/SettingsOutlined'
import type { ReactElement } from 'react'
import { Link as RouterLink, useLocation } from 'react-router-dom'

import logo from '../assets/aiesec-logo-black.png'
import { useAuth } from '../auth/authContext'
import { visibleNavItems } from '../auth/permissions'
import { NAV_ITEMS, type NavItem } from '../navigation/navConfig'

export const SIDEBAR_WIDTH = 272
export const HEADER_HEIGHT = 64

const ICONS: Record<NavItem['key'], ReactElement> = {
  home: <HomeOutlined />,
  membership: <GroupsOutlined />,
  tracking: <PlaylistAddCheckOutlined />,
  data: <InsightsOutlined />,
  settings: <SettingsOutlined />,
}

function isCurrent(item: NavItem, pathname: string): boolean {
  return item.path === '/' ? pathname === '/' : pathname === item.path || pathname.startsWith(`${item.path}/`)
}

/**
 * The logo (Black-Logo.png, padding trimmed) sits top-left and links
 * home. Its left edge lines up with the nav icons below. The row is as tall as the
 * header, so their bottom borders form one line across the page.
 */
function BrandRow() {
  return (
    <Box
      sx={{
        height: HEADER_HEIGHT,
        borderBottom: 1,
        borderColor: 'divider',
        display: 'flex',
        alignItems: 'center',
        px: 4, // 32px: same left edge as the nav icons (16px gutter + 16px button padding)
      }}
    >
      <Box
        component={RouterLink}
        to="/"
        aria-label="AIESEC Membership tool, home"
        sx={{ display: 'inline-flex', borderRadius: 1 }}
      >
        <Box component="img" src={logo} alt="" sx={{ display: 'block', height: 28, width: 'auto' }} />
      </Box>
    </Box>
  )
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { me } = useAuth()
  const { pathname } = useLocation()
  const items = visibleNavItems(NAV_ITEMS, me?.permissions ?? [])

  return (
    <Box sx={{ height: '100%', bgcolor: 'background.paper' }}>
      <BrandRow />
      <Box component="nav" aria-label="Main" sx={{ px: 2, pt: 3 }}>
        <List disablePadding sx={{ display: 'grid', gap: 0.5 }}>
          {items.map((item) => {
            const current = isCurrent(item, pathname)
            return (
              <ListItem key={item.key} disablePadding>
                <ListItemButton
                  component={RouterLink}
                  to={item.path}
                  selected={current}
                  aria-current={current ? 'page' : undefined}
                  onClick={onNavigate}
                >
                  <ListItemIcon>{ICONS[item.key]}</ListItemIcon>
                  <ListItemText primary={item.label} />
                </ListItemButton>
              </ListItem>
            )
          })}
        </List>
      </Box>
    </Box>
  )
}

/** Permanent from 900px up; a slide-in drawer (opened from the header) below that. */
export function Sidebar({ mobileOpen, onClose }: { mobileOpen: boolean; onClose: () => void }) {
  const paper = { width: SIDEBAR_WIDTH, borderRight: 1, borderColor: 'divider', boxSizing: 'border-box' } as const
  return (
    <Box component="aside" sx={{ width: { md: SIDEBAR_WIDTH }, flexShrink: { md: 0 } }}>
      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={onClose}
        ModalProps={{ keepMounted: true }}
        sx={{ display: { xs: 'block', md: 'none' }, '& .MuiDrawer-paper': paper }}
      >
        <SidebarContent onNavigate={onClose} />
      </Drawer>
      <Drawer
        variant="permanent"
        open
        sx={{ display: { xs: 'none', md: 'block' }, '& .MuiDrawer-paper': paper }}
      >
        <SidebarContent />
      </Drawer>
    </Box>
  )
}
