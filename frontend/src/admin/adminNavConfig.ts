/**
 * The Admin console's own sidebar menu (spec §2A.2, §1.5) — separate from
 * `navigation/navConfig.ts`, which a normal user never sees a link to.
 *
 * Every screen from §1.5 is listed here so the pattern for adding the next one is
 * obvious, but only LCs, People and Auditing are built this term; the rest are
 * `built: false` (hidden by `visibleNavItems`) until their own tickets land.
 */
import type { Gated } from '../auth/permissions'

export interface AdminNavItem extends Gated {
  key:
    | 'lcs'
    | 'people'
    | 'memberships'
    | 'teams'
    | 'positions_functions'
    | 'kpis'
    | 'terms'
    | 'custom_fields'
    | 'permission_matrix'
    | 'auditing'
  label: string
  path: string
}

export const ADMIN_NAV_ITEMS: readonly AdminNavItem[] = [
  { key: 'lcs', label: 'LCs', path: '/admin/lcs', requires: { resource: 'lc', action: 'manage' }, built: true },
  { key: 'people', label: 'People', path: '/admin/people', requires: { resource: 'person', action: 'manage' }, built: true },
  {
    key: 'memberships',
    label: 'Memberships',
    path: '/admin/memberships',
    requires: { resource: 'membership', action: 'manage' },
    built: false,
  },
  { key: 'teams', label: 'Teams', path: '/admin/teams', requires: { resource: 'team_member', action: 'manage' }, built: false },
  {
    key: 'positions_functions',
    label: 'Positions & functions',
    path: '/admin/positions-functions',
    requires: { resource: 'position', action: 'manage' },
    built: false,
  },
  { key: 'kpis', label: 'KPIs', path: '/admin/kpis', requires: { resource: 'attribute', action: 'manage' }, built: false },
  { key: 'terms', label: 'Terms', path: '/admin/terms', requires: { resource: 'term', action: 'manage' }, built: false },
  {
    key: 'custom_fields',
    label: 'Custom fields',
    path: '/admin/custom-fields',
    requires: { resource: 'attribute', action: 'manage' },
    built: false,
  },
  {
    key: 'permission_matrix',
    label: 'Permission matrix',
    path: '/admin/permission-matrix',
    requires: { resource: 'permission_matrix', action: 'manage' },
    built: false,
  },
  {
    key: 'auditing',
    label: 'Auditing',
    path: '/admin/auditing',
    requires: { resource: 'audit_log', action: 'view' },
    built: true,
  },
]
