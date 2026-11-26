/**
 * Real HTTP implementation of the `Api` interface (Spec §2A.5 — ticket DEV-0043).
 *
 * Wired to the real backend so far:
 *   listMembers, addMember, getMembershipDetail, extendTerm, moveToTeam (§2A.5)
 *   getMyCustomFields, updateMyCustomFields, getMyMembershipHistory (Profile, §2A.9 — DEV-0045)
 *
 * Every other method comes from `options.fallback` (today, the mock), so the rest
 * of the app keeps running while those backend tickets are still in progress.
 *
 * AUTH: this file doesn't know how people sign in. The caller passes
 * `getAuthHeaders()`, which runs before every request. Supabase mode returns
 * `{ Authorization: 'Bearer <access token>' }` (see `api/index.ts`); a cookie
 * session (EXPA sign-in, later) can return `{}`. The backend decides who the
 * caller is from those headers alone — never from anything else we send.
 *
 * URL SHAPE (backend route → frontend method):
 *   POST /api/v1/members/summary           → listMembers
 *   POST /api/v1/members                   → addMember
 *   GET  /api/v1/members/:id               → getMembershipDetail
 *   POST /api/v1/members/:id/extend-term   → extendTerm
 *   POST /api/v1/members/:id/move-to-team  → moveToTeam
 *   GET  /api/v1/me/custom-fields          → getMyCustomFields
 *   PATCH /api/v1/me/custom-fields         → updateMyCustomFields
 *   GET  /api/v1/me/memberships            → getMyMembershipHistory
 *   GET/POST /api/v1/people, PATCH /people/:id, POST /people/:id/(de|re)activate
 *                                          → listPeopleAdmin, createPerson, updatePerson, …
 *   GET/POST /api/v1/people/:id/memberships → listPersonMemberships, assignMembership
 *   PATCH /api/v1/memberships/:id, POST …/end → correctMembership, endMembership
 */

import type {
  ActionResult,
  DataChart,
  DataQuery,
  Lc,
  ReferenceData,
  Team,
  Term,
  AddMemberInput,
  AddMemberResult,
  Api,
  CustomField,
  CustomFieldValue,
  MembershipView,
  IsoDate,
  MemberQuery,
  MembershipDetail,
  Page,
  MemberSummaryRow,
  AdminPersonRow,
  AdminPersonInput,
  AdminPersonQuery,
  AdminMembershipRow,
  AssignMembershipInput,
  CorrectMembershipInput,
} from '../types'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * A database id from the frontend's string id: '12' → 12. Anything else → null.
 * A non-numeric id (e.g. the mock's 'lc-usyd') means the form was built from stale
 * reference data, so the caller refuses it rather than sending it to the backend.
 */
function toDbId(id: string | undefined | null): number | null {
  return id != null && /^\d+$/.test(id) ? Number(id) : null
}

/** What the user sees when a form holds an id the backend can't accept. */
const STALE_FORM: { status: 'rejected'; message: string } = {
  status: 'rejected',
  message: 'The form is out of date. Close it and try again.',
}

// ---------------------------------------------------------------------------
// Options
// ---------------------------------------------------------------------------

export interface HttpApiOptions {
  /** Headers that prove who is calling. Supabase mode: { Authorization: 'Bearer …' }.
   *  Cookie-session sign-in (EXPA, later): {}. Called before every request, so a
   *  refreshed token is always picked up. */
  getAuthHeaders: () => Promise<Record<string, string>>
  /** The API origin. '' = same origin (Firebase Hosting forwards /api/**). */
  baseUrl?: string
  /** The `Api` that still answers the non-membership methods (today, the mock). */
  fallback: Api
}

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

/** A non-2xx answer from the backend. `status` lets callers word the error. */
export class HttpError extends Error {
  readonly status: number
  /** The server's own explanation (FastAPI's `{"detail": "..."}`), when it gave one. */
  readonly detail: string | null

  constructor(method: string, path: string, status: number, text: string) {
    super(`${method} ${path} → ${status}: ${text}`)
    this.name = 'HttpError'
    this.status = status
    this.detail = detailFrom(text)
  }
}

function detailFrom(text: string): string | null {
  try {
    const detail: unknown = JSON.parse(text)?.detail
    return typeof detail === 'string' ? detail : null
  } catch {
    return null
  }
}

interface Transport {
  post<T>(path: string, body: unknown): Promise<T>
  patch<T>(path: string, body: unknown): Promise<T>
  get<T>(path: string): Promise<T>
}

function createTransport(options: HttpApiOptions): Transport {
  const baseUrl = options.baseUrl ?? import.meta.env.VITE_API_URL ?? ''

  async function request<T>(method: 'GET' | 'POST' | 'PATCH', path: string, body?: unknown): Promise<T> {
    const headers = { 'Content-Type': 'application/json', ...(await options.getAuthHeaders()) }
    const res = await fetch(`${baseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText)
      throw new HttpError(method, path, res.status, text)
    }
    return res.json() as Promise<T>
  }

  return {
    post: (path, body) => request('POST', path, body),
    patch: (path, body) => request('PATCH', path, body),
    get: (path) => request('GET', path),
  }
}

/** What the user sees when a change could not be saved, by HTTP status. */
function failureMessage(error: unknown, notFound?: string): string {
  const status = error instanceof HttpError ? error.status : null
  if (status === 401) return 'Your session has expired. Sign in again.'
  // A 403 may carry its own reason (e.g. "You can't do this to your own record."), so
  // show that when there is one; otherwise the generic text.
  if (status === 403) {
    return error instanceof HttpError && error.detail ? error.detail : "You don't have permission to do that."
  }
  if (status === 404) return notFound ?? 'That membership no longer exists. Refresh the page.'
  // 400 and 409 carry a sentence written for the admin (e.g. "Someone already has
  // that email address."), so show it as it is.
  if ((status === 400 || status === 409) && error instanceof HttpError && error.detail) {
    return error.detail
  }
  return 'Something went wrong. Try again.'
}

/**
 * Runs a write request. Writes never throw: the dialogs only look at `status`, so a
 * failure (HTTP error or no network) comes back as a rejection the user can read.
 * Reads (listMembers, getMembershipDetail, getReferenceData) still throw, and the
 * pages show their own error state.
 */
async function action<T>(
  send: () => Promise<T>,
  notFound?: string,
): Promise<T | { status: 'rejected'; message: string }> {
  try {
    return await send()
  } catch (error) {
    return { status: 'rejected', message: failureMessage(error, notFound) }
  }
}

/** A membership id, made safe to put in a URL path. */
function idPath(membershipId: string): string {
  return `/api/v1/members/${encodeURIComponent(membershipId)}`
}

/** The 404 text for the people methods (the default text is about memberships). */
const PERSON_NOT_FOUND = 'That person no longer exists. Refresh the page.'

/** Turns a write's answer into an `ActionResult`. A person row (the people endpoints
 * answer with the saved person) or `{status: 'ok'}` is a success. */
function toActionResult(result: { status?: string; message?: string }): ActionResult {
  if (result.status === 'rejected') {
    return { status: 'rejected', message: result.message ?? 'Unknown error' }
  }
  // A failed `action()` is already `rejected`, handled above. Anything else saved.
  return { status: 'ok' }
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

/**
 * Creates an `Api` implementation that:
 * - Calls the real FastAPI backend for the membership-summary and Profile methods.
 * - Uses `options.fallback` for everything else (getMe, signIn, signOut, admin, …).
 */
export function createHttpApi(options: HttpApiOptions): Api {
  const http = createTransport(options)

  return {
    ...options.fallback,

    /**
     * LCs, terms and teams come from the backend, so their ids are real database
     * ids. Positions and functions still come from the fallback: the backend has no
     * endpoint for them yet. KNOWN GAP: the mock's keys and the backend seeds only
     * partly agree (functions: only `ogv` and `bd` match today; the MC positions are
     * missing from the seeds). See docs/data-model.md "Known differences"; the
     * schema-alignment ticket fixes the seeds.
     */
    async getReferenceData(): Promise<ReferenceData> {
      const [fromBackend, local] = await Promise.all([
        http.get<{ lcs: Lc[]; terms: Term[]; teams: Team[] }>('/api/v1/reference/membership-options'),
        options.fallback.getReferenceData(),
      ])
      return { ...local, lcs: fromBackend.lcs, terms: fromBackend.terms, teams: fromBackend.teams }
    },

    // -------------------------------------------------------------------
    // Membership summary — REAL backend (Spec §2A.5)
    // -------------------------------------------------------------------

    async listMembers(query: MemberQuery): Promise<Page<MemberSummaryRow>> {
      return http.post<Page<MemberSummaryRow>>('/api/v1/members/summary', query)
    },

    async addMember(input: AddMemberInput): Promise<AddMemberResult> {
      const lcId = toDbId(input.lcId)
      const teamId = toDbId(input.teamId)
      const termId = toDbId(input.termId)
      // Which of the actor's own memberships this add is made under (optional).
      const actingMembershipId = toDbId(input.membershipId)
      // An id that was given but isn't numeric came from stale reference data.
      const stale =
        lcId === null ||
        (input.teamId && teamId === null) ||
        (input.termId && termId === null) ||
        (input.membershipId && actingMembershipId === null)
      if (stale) return STALE_FORM
      const body = {
        email: input.email,
        lcId,
        positionKey: input.positionKey,
        functionKey: input.functionKey,
        teamId,
        startDate: input.startDate,
        endDate: input.endDate,
        termId,
        firstName: input.firstName ?? null,
        lastName: input.lastName ?? null,
        confirmedExisting: input.confirmedExisting ?? false,
        membershipId: actingMembershipId,
      }
      const result = await action(() => http.post<{ status: string; message?: string }>('/api/v1/members', body))
      // Narrow to the union type the frontend `Api` expects
      if (result.status === 'needs_name') return { status: 'needs_name' }
      if (result.status === 'confirm_existing') return { status: 'confirm_existing' }
      if (result.status === 'created') return { status: 'created' }
      return { status: 'rejected', message: result.message ?? 'Unknown error' }
    },

    async getMembershipDetail(membershipId: string): Promise<MembershipDetail> {
      return http.get<MembershipDetail>(idPath(membershipId))
    },

    async extendTerm(membershipId: string, newEndDate: IsoDate): Promise<ActionResult> {
      const result = await action(() =>
        http.post<{ status: string; message?: string }>(`${idPath(membershipId)}/extend-term`, { newEndDate }),
      )
      if (result.status === 'ok') return { status: 'ok' }
      return { status: 'rejected', message: result.message ?? 'Unknown error' }
    },

    async moveToTeam(membershipId: string, teamId: string): Promise<ActionResult> {
      const dbTeamId = toDbId(teamId)
      if (dbTeamId === null) return STALE_FORM
      const result = await action(() =>
        http.post<{ status: string; message?: string }>(`${idPath(membershipId)}/move-to-team`, { teamId: dbTeamId }),
      )
      if (result.status === 'ok') return { status: 'ok' }
      return { status: 'rejected', message: result.message ?? 'Unknown error' }
    },

    // -------------------------------------------------------------------
    // Admin console: People and Memberships — REAL backend (DEV-47)
    // -------------------------------------------------------------------

    async listPeopleAdmin(query: AdminPersonQuery): Promise<Page<AdminPersonRow>> {
      const params = new URLSearchParams({
        search: query.search,
        page: String(query.page),
        pageSize: String(query.pageSize),
      })
      return http.get<Page<AdminPersonRow>>(`/api/v1/people?${params.toString()}`)
    },

    async createPerson(input: AdminPersonInput): Promise<ActionResult> {
      const result = await action(() => http.post<AdminPersonRow>('/api/v1/people', input), PERSON_NOT_FOUND)
      return toActionResult(result)
    },

    async updatePerson(personId: string, changes: Partial<AdminPersonInput>): Promise<ActionResult> {
      const id = toDbId(personId)
      if (id === null) return STALE_FORM
      const result = await action(() => http.patch<AdminPersonRow>(`/api/v1/people/${id}`, changes), PERSON_NOT_FOUND)
      return toActionResult(result)
    },

    async deactivatePerson(personId: string): Promise<ActionResult> {
      const id = toDbId(personId)
      if (id === null) return STALE_FORM
      const result = await action(() => http.post<AdminPersonRow>(`/api/v1/people/${id}/deactivate`, {}), PERSON_NOT_FOUND)
      return toActionResult(result)
    },

    async unlinkExpa(personId: string): Promise<ActionResult> {
      const id = toDbId(personId)
      if (id === null) return STALE_FORM
      const result = await action(() => http.post<AdminPersonRow>(`/api/v1/people/${id}/unlink-expa`, {}), PERSON_NOT_FOUND)
      return toActionResult(result)
    },

    async reactivatePerson(personId: string): Promise<ActionResult> {
      const id = toDbId(personId)
      if (id === null) return STALE_FORM
      const result = await action(() => http.post<AdminPersonRow>(`/api/v1/people/${id}/reactivate`, {}), PERSON_NOT_FOUND)
      return toActionResult(result)
    },

    async listPersonMemberships(personId: string): Promise<AdminMembershipRow[]> {
      return http.get<AdminMembershipRow[]>(`/api/v1/people/${encodeURIComponent(personId)}/memberships`)
    },

    async assignMembership(personId: string, input: AssignMembershipInput): Promise<ActionResult> {
      const id = toDbId(personId)
      const lcId = toDbId(input.lcId)
      if (id === null || lcId === null) return STALE_FORM
      const body = { ...input, lcId }
      const result = await action(
        () => http.post<{ status: string; message?: string }>(`/api/v1/people/${id}/memberships`, body),
        PERSON_NOT_FOUND,
      )
      return toActionResult(result)
    },

    async correctMembership(membershipId: string, changes: CorrectMembershipInput): Promise<ActionResult> {
      const id = toDbId(membershipId)
      if (id === null) return STALE_FORM
      const result = await action(() =>
        http.patch<{ status: string; message?: string }>(`/api/v1/memberships/${id}`, changes),
      )
      return toActionResult(result)
    },

    async endMembership(membershipId: string, endDate: IsoDate): Promise<ActionResult> {
      const id = toDbId(membershipId)
      if (id === null) return STALE_FORM
      const result = await action(() =>
        http.post<{ status: string; message?: string }>(`/api/v1/memberships/${id}/end`, { endDate }),
      )
      return toActionResult(result)
    },

    // -------------------------------------------------------------------
    // Profile — REAL backend (Spec §2A.9)
    // -------------------------------------------------------------------

    async getMyCustomFields(): Promise<CustomField[]> {
      return http.get<CustomField[]>('/api/v1/me/custom-fields')
    },

    async getMyMembershipHistory(): Promise<MembershipView[]> {
      return http.get<MembershipView[]>('/api/v1/me/memberships')
    },

    /** Throws `HttpError` when the save is refused; a 422's `detail` says which field. */
    async updateMyCustomFields(values: Record<string, CustomFieldValue>): Promise<CustomField[]> {
      return http.patch<CustomField[]>('/api/v1/me/custom-fields', values)
    },

    // -------------------------------------------------------------------
    // Data page — REAL backend (Spec §2A.7, §6)
    // -------------------------------------------------------------------

    async getDataChart(query: DataQuery): Promise<DataChart> {
      const params = new URLSearchParams({
        scope: query.scope,
        start: query.startDate,
        end: query.endDate,
      })
      if (query.kpiKey) params.set('kpi', query.kpiKey)
      const lcId = toDbId(query.lcId ?? null)
      if (lcId !== null) params.set('lc_id', String(lcId))
      return http.get<DataChart>(`/api/v1/data/chart?${params.toString()}`)
    },
  }
}
