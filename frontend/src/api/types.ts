/**
 * Domain types and the API contract.
 *
 * WHY THIS FILE EXISTS
 * The backend schema is behind the spec (docs/data-model.md, "Known differences"),
 * so the frontend does NOT import backend models. Everything the UI knows about the
 * server is described here, and everything the UI asks of the server goes through the
 * single `Api` interface at the bottom of this file.
 *
 * Today `Api` is implemented by `api/mock/mockApi.ts`. When the real backend is ready,
 * write an `Api` implementation that calls it and change the one line in `api/index.ts`.
 * No page or component talks to `fetch` directly.
 *
 * Shapes follow the spec: positions/functions (§2), permissions (§3.1), membership
 * summary (§2A.5), profile (§2A.9).
 */

// ---------------------------------------------------------------------------
// Lookups (data, not code: an admin can add a function or reorder ranks, §1.5)
// ---------------------------------------------------------------------------

/** Whether a position/LC belongs to a Local Committee or to the national MC (§3.6). */
export type Level = 'lc' | 'mc'

/** Which team/function/all-of-Australia chart a position sees on the homepage. */
export type ChartScope = 'team' | 'function' | 'all'

export interface Position {
  key: string
  label: string
  level: Level
  /** A HIGHER number is a HIGHER position (§2, §3.4). */
  rank: number
  /** President exception (§3.4): may add another holder of the same position. */
  canAddSameRank: boolean
  /**
   * Frontend assumption, not yet in the spec or schema: presidential positions (LCP,
   * MCP) use the `presidentOnly` function, and no other position may (spec §2 says the
   * President function is "for LCP and MCP"). Confirm before the real backend swap.
   */
  presidential: boolean
  /** Frontend assumption: which default chart the homepage shows (spec §12 #12). */
  homeChartScope: ChartScope
  /** True when a person in this position belongs to a specific team (§3.4). */
  holdsTeam: boolean
}

export interface FunctionDef {
  key: string
  label: string
  active: boolean
  /** True only for the President function (see `Position.presidential`). */
  presidentOnly: boolean
}

export interface FunctionRef {
  key: string
  label: string
}

export interface Lc {
  id: string
  /** Short display name, e.g. "USYD". The MC is a row with type 'mc' (spec §0.5). */
  name: string
  type: Level
}

export interface Term {
  id: string
  /** e.g. "26.2" (§5.3) */
  name: string
  startDate: string
  endDate: string
}

export interface Team {
  id: string
  name: string
  lcId: string
  functionKey: string
  /** Who currently leads it, resolved for display where the mock/backend resolves it
   * (Add-Member's team picker) — undefined where not resolved (e.g. Move-to-team's
   * `teamOptions`, which doesn't need it). Null means no leader is currently assigned. */
  leader?: { membershipId: string; name: string } | null
}

/** Everything the Add member form needs to build its choices. */
export interface ReferenceData {
  lcs: Lc[]
  positions: Position[]
  functions: FunctionDef[]
  terms: Term[]
  teams: Team[]
}

// ---------------------------------------------------------------------------
// Permissions (§3.1). Resolved on the server (§3.2) and delivered read-only.
// ---------------------------------------------------------------------------

/** Ordered narrowest to widest in `auth/permissions.ts` (SCOPE_ORDER). */
export type Scope = 'own' | 'team' | 'function' | 'lc' | 'all'

export type Action = 'view' | 'create' | 'edit' | 'delete' | 'export' | 'manage'

export interface Permission {
  /** e.g. 'membership', 'team_member', 'kpi_record'. A string because it is data. */
  resource: string
  action: Action
  scope: Scope
}

// ---------------------------------------------------------------------------
// "me": the signed-in person (§2A.9)
// ---------------------------------------------------------------------------

/** ISO calendar date, "YYYY-MM-DD". Compares correctly as a plain string. */
export type IsoDate = string

export type CustomFieldValue = string | number | boolean | null

/** A person-level custom field (§4.2, `attribute.applies_to = 'person'`) plus its value. */
export interface CustomField {
  key: string
  label: string
  dataType: 'text' | 'number' | 'date' | 'boolean' | 'enum'
  enumOptions?: string[]
  value: CustomFieldValue
}

/** One row of the person's own position history (§2A.9). */
export interface MembershipView {
  id: string
  position: Position
  function: FunctionRef | null
  lc: Lc
  /** Current team, if any. Needed for `team` scope checks. */
  team: { id: string; name: string } | null
  startDate: IsoDate
  endDate: IsoDate | null
}

export interface Me {
  person: {
    id: string
    firstName: string
    lastName: string
    /** Shown on Profile only. Never shown on the Membership summary (§2A.5). */
    email: string
    customFields: CustomField[]
  }
  /** Current, past and future memberships. Filter with `isActive` before using for access. */
  memberships: MembershipView[]
  /** Every grant, already resolved by the server (§3.2). */
  permissions: Permission[]
}

// ---------------------------------------------------------------------------
// Membership summary (§2A.5)
// ---------------------------------------------------------------------------

/**
 * One position-function pair of a person. Carries only what the UI needs to decide
 * which actions to offer. NO email and no dates: the summary shows names, roles and
 * LC only (§2A.5).
 */
export interface MemberRole {
  membershipId: string
  position: Position
  function: FunctionRef | null
  teamId: string | null
}

export interface MemberSummaryRow {
  personId: string
  firstName: string
  lastName: string
  lc: Lc
  /** A person with several functions appears once, with every pair (§2A.5). */
  roles: MemberRole[]
}

export type MemberSortField = 'firstName' | 'lastName' | 'lc' | 'position'

export interface MemberQuery {
  search: string
  sort: { field: MemberSortField; direction: 'asc' | 'desc' } | null
  /** Zero-based. */
  page: number
  pageSize: number
  /** MC users can filter by LC (§2A.5). Null means all LCs in the viewer's scope. */
  lcId: string | null
}

export interface Page<T> {
  rows: T[]
  total: number
}

export interface AddMemberInput {
  /** The AIESEC email identifies the person (§2A.5). */
  email: string
  /** Only needed when no one has this email yet. */
  firstName?: string
  lastName?: string
  /** Which of the actor's own active memberships this request is acting under. Omit to
   * use their default (`actingMembership`'s own choice) — only meaningful when the
   * actor holds more than one membership of the same position. */
  membershipId?: string
  lcId: string
  positionKey: string
  functionKey: string
  /** Required when the chosen position holds a team (`Position.holdsTeam`) and the
   * actor isn't already fixed to one team-scope team. */
  teamId?: string
  startDate: IsoDate
  endDate: IsoDate
  termId?: string
  /** Set after the user confirms the "existing email" dialog. */
  confirmedExisting?: boolean
}

export type AddMemberResult =
  /** No one has this email: ask for first and last name, then send again. */
  | { status: 'needs_name' }
  /** Someone has this email: ask the user to confirm, then send again with `confirmedExisting`. */
  | { status: 'confirm_existing' }
  | { status: 'created' }
  | { status: 'rejected'; message: string }

export type ActionResult = { status: 'ok' } | { status: 'rejected'; message: string }

/** What the Manage membership panel shows about one membership (team + term). */
export interface MembershipDetail {
  membershipId: string
  personName: string
  position: Position
  function: FunctionRef | null
  lc: Lc
  startDate: IsoDate
  endDate: IsoDate | null
  currentTeam: { id: string; name: string } | null
  /** Teams this person could move to, already limited to the viewer's scope. */
  teamOptions: Team[]
}

// ---------------------------------------------------------------------------
// Homepage (§2A.4)
// ---------------------------------------------------------------------------

export interface HomeChart {
  scope: ChartScope
  title: string
  period: 'monthly'
  /** Empty until the KPI catalog exists (spec §4.3 TODO). The UI then says "No data exists". */
  points: { month: string; value: number }[]
}

// ---------------------------------------------------------------------------
// The one interface every page uses
// ---------------------------------------------------------------------------

export interface Api {
  // Session
  /** The signed-in person, or null when signed out or the session expired. */
  getMe(): Promise<Me | null>
  /** Placeholder now; becomes "Sign in with Google" (§2A.3, §9). */
  signIn(): Promise<void>
  signOut(): Promise<void>

  // Profile
  /** Person-level custom fields only. Names, email, membership and dates are locked (§2A.9). */
  updateMyCustomFields(values: Record<string, CustomFieldValue>): Promise<Me>

  // Membership summary
  getReferenceData(): Promise<ReferenceData>
  listMembers(query: MemberQuery): Promise<Page<MemberSummaryRow>>
  addMember(input: AddMemberInput): Promise<AddMemberResult>
  getMembershipDetail(membershipId: string): Promise<MembershipDetail>
  extendTerm(membershipId: string, newEndDate: IsoDate): Promise<ActionResult>
  moveToTeam(membershipId: string, teamId: string): Promise<ActionResult>

  // Homepage
  getHomeChart(): Promise<HomeChart>
}
