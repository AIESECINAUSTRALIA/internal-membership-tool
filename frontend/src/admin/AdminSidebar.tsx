import { Box, Drawer, List, ListItem, ListItemButton, ListItemIcon, ListItemText, Stack, Typography } from '@mui/material'
import AdminPanelSettingsOutlined from '@mui/icons-material/AdminPanelSettingsOutlined'
import ApartmentOutlined from '@mui/icons-material/ApartmentOutlined'
import PeopleAltOutlined from '@mui/icons-material/PeopleAltOutlined'
import BadgeOutlined from '@mui/icons-material/BadgeOutlined'
import GroupsOutlined from '@mui/icons-material/GroupsOutlined'
import AccountTreeOutlined from '@mui/icons-material/AccountTreeOutlined'
import BarChartOutlined from '@mui/icons-material/BarChartOutlined'
import EventOutlined from '@mui/icons-material/EventOutlined'
import TuneOutlined from '@mui/icons-material/TuneOutlined'
import LockOutlined from '@mui/icons-material/LockOutlined'
import HistoryOutlined from '@mui/icons-material/HistoryOutlined'
import type { ReactElement } from 'react'
import { Link as RouterLink, useLocation } from 'react-router-dom'

import logo from '../assets/aiesec-logo-black.png'
import { useAuth } from '../auth/authContext'
import { visibleNavItems } from '../auth/permissions'
import { ADMIN_NAV_ITEMS, type AdminNavItem } from './adminNavConfig'
import { HEADER_HEIGHT, SIDEBAR_WIDTH } from '../layout/Sidebar'

const ICONS: Record<AdminNavItem['key'], ReactElement> = {
  lcs: <ApartmentOutlined />,
  people: <PeopleAltOutlined />,
  memberships: <BadgeOutlined />,
  teams: <GroupsOutlined />,
  positions_functions: <AccountTreeOutlined />,
  kpis: <BarChartOutlined />,
  terms: <EventOutlined />,
  custom_fields: <TuneOutlined />,
  permission_matrix: <LockOutlined />,
  auditing: <HistoryOutlined />,
}

function isCurrent(item: AdminNavItem, pathname: string): boolean {
  return pathname === item.path || pathname.startsWith(`${item.path}/`)
}

/** Same brand row as the main app's sidebar — same height, so its bottom border still
 * lines up with the header. The "Admin console" label gets its OWN row below, full
 * width, rather than squeezing in beside the logo: at 272px wide the logo alone
 * (1189x169, so ~197px at this height) leaves no room for anything next to it. */
function BrandRow() {
  return (
    <Box
      sx={{
        height: HEADER_HEIGHT,
        borderBottom: 1,
        borderColor: 'divider',
        display: 'flex',
        alignItems: 'center',
        px: 4,
      }}
    >
      <Box
        component={RouterLink}
        to="/admin"
        aria-label="AIESEC Membership tool admin console, home"
        sx={{ display: 'inline-flex', borderRadius: 1 }}
      >
        <Box component="img" src={logo} alt="" sx={{ display: 'block', height: 28, width: 'auto' }} />
      </Box>
    </Box>
  )
}

/** Labels the area as the Admin console, below the brand row and full width so it
 * never clips regardless of sidebar width or logo size. */
function AdminBanner() {
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', px: 4, py: 1.5, borderBottom: 1, borderColor: 'divider' }}>
      <AdminPanelSettingsOutlined fontSize="small" color="primary" />
      <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.5, lineHeight: 1 }}>
        Admin console
      </Typography>
    </Stack>
  )
}

function AdminSidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { me } = useAuth()
  const { pathname } = useLocation()
  const items = visibleNavItems(ADMIN_NAV_ITEMS, me?.permissions ?? [])

  return (
    <Box sx={{ height: '100%', bgcolor: 'background.paper' }}>
      <BrandRow />
      <AdminBanner />
      <Box component="nav" aria-label="Admin console" sx={{ px: 2, pt: 3 }}>
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

/** Permanent from 900px up; a slide-in drawer (opened from the header) below that —
 * same responsive treatment as the main app's `Sidebar`. */
export function AdminSidebar({ mobileOpen, onClose }: { mobileOpen: boolean; onClose: () => void }) {
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
        <AdminSidebarContent onNavigate={onClose} />
      </Drawer>
      <Drawer variant="permanent" open sx={{ display: { xs: 'none', md: 'block' }, '& .MuiDrawer-paper': paper }}>
        <AdminSidebarContent />
      </Drawer>
    </Box>
  )
}
