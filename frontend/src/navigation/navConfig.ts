/**
 * The sidebar menu, as data. Each item names the permission needed to see it
 * (`requires`), so what shows is driven by the signed-in person's resolved permissions
 * (spec §2A, §2A.1), not by a hardcoded list of roles.
 *
 * Hiding an item is a convenience only. The server enforces access on every request.
 *
 * `built: false` hides an item whose page does not exist yet. Every item is built now
 * (Tracking, Data and Settings are placeholders), but the flag stays for the next feature.
 */
import type { Gated } from '../auth/permissions'

export interface NavItem extends Gated {
  key: 'home' | 'membership' | 'tracking' | 'data' | 'settings'
  label: string
  path: string
}

export const NAV_ITEMS: readonly NavItem[] = [
  // Everyone signed in and allocated (§2A.4).
  { key: 'home', label: 'Home', path: '/', built: true },
  // Anyone with `view` on `membership` (§2A.1).
  { key: 'membership', label: 'Membership', path: '/membership', requires: { resource: 'membership', action: 'view' }, built: true },
  // Own tracking or tracking others: needs `view` on `kpi_record` at any scope (§2A.6).
  { key: 'tracking', label: 'Tracking', path: '/tracking', requires: { resource: 'kpi_record', action: 'view' }, built: true },
  // Anyone with `view` on dashboards/analytics (§2A.7), at team scope or wider — an
  // 'own'-only grant has no group rollup to show (see availableDataScopes).
  {
    key: 'data',
    label: 'Data',
    path: '/data',
    requires: { resource: 'analytics_report', action: 'view', minScope: 'team' },
    built: true,
  },
  // Everyone signed in; the Functions screen inside it is MC only (§2A.8).
  { key: 'settings', label: 'Settings', path: '/settings', built: true },
]
