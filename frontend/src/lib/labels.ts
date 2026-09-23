/**
 * Small display helpers. Labels come from the lookup data (position and function
 * labels), so a renamed function shows up everywhere without a code change.
 */
import dayjs from 'dayjs'

import type { FunctionRef, IsoDate, MembershipView, Position, Scope, Team } from '../api/types'

/** "Team Leader (TL)" -> "TL". "Member" -> "Member". Uses the bracketed short name if any. */
export function shortLabel(label: string): string {
  const match = /\(([^)]+)\)\s*$/.exec(label)
  return match ? match[1] : label
}

/** "TL – oGV": the position-function pair shown in tables (spec §2A.5). */
export function roleLabel(position: Position, fn: FunctionRef | null): string {
  return fn ? `${shortLabel(position.label)} – ${shortLabel(fn.label)}` : shortLabel(position.label)
}

/** "TL – oGV · oGV Team A": disambiguates two memberships of the same position (the
 * Add-Member "Add as" picker) by adding the team, or the LC when there's no team. */
export function membershipLabel(m: MembershipView): string {
  return `${roleLabel(m.position, m.function)} · ${m.team?.name ?? m.lc.name}`
}

/** "oGV Team A — led by Jamie Lee" / "oGV Team A — no leader assigned": the Add-Member
 * team picker's option text. */
export function teamOptionLabel(t: Team): string {
  return `${t.name} — ${t.leader ? `led by ${t.leader.name}` : 'no leader assigned'}`
}

/** "temp_oGV" or "Member 1": first and last name joined, with no stray space if one is blank. */
export function fullName(firstName: string, lastName: string): string {
  return [firstName, lastName].filter(Boolean).join(' ')
}

/** Australian style, e.g. "5 Nov 2026". */
export function formatDate(iso: IsoDate | null): string {
  return iso ? dayjs(iso).format('D MMM YYYY') : 'No end date'
}

/** Plain-English scope names for the permissions table. */
export const SCOPE_LABELS: Record<Scope, string> = {
  own: 'Only you',
  team: 'Your team',
  function: 'Your function',
  lc: 'Your LC',
  all: 'All LCs',
}

/** "member_record" -> "Member record", "kpi_record" -> "KPI record". */
export function humanise(key: string): string {
  const spaced = key.replace(/[_.]/g, ' ').replace(/\b(kpi|lc|mc)\b/gi, (word) => word.toUpperCase())
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}
