/**
 * Real HTTP implementation of the `Api` interface (Spec §2A.5 — ticket DEV-0043).
 *
 * Only the five membership-summary methods are wired to the real backend:
 *   listMembers, addMember, getMembershipDetail, extendTerm, moveToTeam
 *
 * All other methods (getMe, signIn, signOut, updateMyCustomFields,
 * getReferenceData, getHomeChart) are delegated to the mockApi so the rest of
 * the app keeps running while those tickets are still in progress.
 *
 * AUTH: The backend currently uses the `X-Actor-Email` test-double header (set
 * by `deps.py::get_current_actor`). Ticket 7 will replace this with a real JWT
 * — when it does, swap the header logic in `headers()` below, nothing else changes.
 *
 * URL SHAPE (backend route → frontend method):
 *   POST /api/v1/members/summary           → listMembers
 *   POST /api/v1/members                   → addMember
 *   GET  /api/v1/members/:id               → getMembershipDetail
 *   POST /api/v1/members/:id/extend-term   → extendTerm
 *   POST /api/v1/members/:id/move-to-team  → moveToTeam
 *
 * SHAPE DIFFERENCES (backend ↔ frontend):
 *   • `Page` — backend returns `{items, total, page, pageSize}`;
 *               frontend Api expects `{rows, total}`.
 *   • `lcId` / `teamId` — frontend `Api` uses string IDs; backend schemas accept
 *               both integer IDs and string slugs (e.g. "lc-usyd").
 *   • `MemberSummaryRow.lc.type` — backend uses `"lc"|"mc"` (Enum LCType)
 *               which maps to frontend's `Level` type — already compatible.
 */

import type {
  ActionResult,
  AddMemberInput,
  AddMemberResult,
  Api,
  IsoDate,
  MemberQuery,
  MembershipDetail,
  Page,
  MemberSummaryRow,
} from '../types'
import type { MockApiOptions } from '../mock/mockApi'
import { createMockApi } from '../mock/mockApi'

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Normalises an ID so that numeric strings become numbers, while slug strings
 * (e.g. "lc-usyd" from mock seed reference data) are preserved as strings.
 */
function parseId(val: string | number | undefined | null): number | string | null {
  if (val == null) return null
  if (typeof val === 'number') return isNaN(val) ? null : val
  const trimmed = String(val).trim()
  if (/^\d+$/.test(trimmed)) return parseInt(trimmed, 10)
  return trimmed
}

// ---------------------------------------------------------------------------
// Wire the real `httpApi` on top of the mock for non-membership methods
// ---------------------------------------------------------------------------

export interface HttpApiOptions {
  /**
   * The AIESEC email of the signed-in user, sent as `X-Actor-Email` on every
   * request. This is the test-double auth mechanism until Ticket 7 lands.
   * When the actor email is not yet known (e.g. before sign-in resolves)
   * the header is omitted and the backend will return 401 — the UI's existing
   * auth guard handles that gracefully.
   */
  getActorEmail: () => string | null
  /** Options forwarded to the mock that still handles the non-membership calls. */
  mockOptions?: MockApiOptions
}

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

function headers(actorEmail: string | null): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  if (actorEmail) h['X-Actor-Email'] = actorEmail
  return h
}

async function post<T>(path: string, body: unknown, actorEmail: string | null): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: headers(actorEmail),
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`POST ${path} → ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

async function get<T>(path: string, actorEmail: string | null): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'GET',
    headers: headers(actorEmail),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`GET ${path} → ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// Backend response shapes (differ slightly from frontend Api types)
// ---------------------------------------------------------------------------

/** The backend Page schema — `items` instead of `rows`. */
interface BackendPage<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

/**
 * Creates an `Api` implementation that:
 * - Calls the real FastAPI backend for all five membership-summary methods.
 * - Delegates everything else to the mock (getMe, signIn, signOut, …).
 */
export function createHttpApi(options: HttpApiOptions): Api {
  const mock = createMockApi(options.mockOptions ?? {})
  const email = () => options.getActorEmail()

  return {
    // -------------------------------------------------------------------
    // Session — still mock (Ticket 7 / §2A.3)
    // -------------------------------------------------------------------
    getMe: () => mock.getMe(),
    signIn: () => mock.signIn(),
    signOut: () => mock.signOut(),
    updateMyCustomFields: (values) => mock.updateMyCustomFields(values),

    // -------------------------------------------------------------------
    // Reference data — still mock (no /reference-data endpoint yet)
    // -------------------------------------------------------------------
    getReferenceData: () => mock.getReferenceData(),

    // -------------------------------------------------------------------
    // Homepage chart — still mock (Ticket 11 / §2A.4)
    // -------------------------------------------------------------------
    getHomeChart: () => mock.getHomeChart(),

    // -------------------------------------------------------------------
    // Membership summary — REAL backend (Spec §2A.5)
    // -------------------------------------------------------------------

    async listMembers(query: MemberQuery): Promise<Page<MemberSummaryRow>> {
      const body = {
        search: query.search,
        sortField: query.sort?.field ?? 'lastName',
        sortDirection: query.sort?.direction ?? 'asc',
        page: query.page,
        pageSize: query.pageSize,
        lcId: query.lcId ?? null,
      }
      const backendPage = await post<BackendPage<MemberSummaryRow>>(
        '/api/v1/members/summary',
        body,
        email(),
      )
      // Normalise backend {items} → frontend {rows}
      return { rows: backendPage.items, total: backendPage.total }
    },

    async addMember(input: AddMemberInput): Promise<AddMemberResult> {
      const body = {
        email: input.email,
        lcId: parseId(input.lcId),
        positionKey: input.positionKey,
        functionKey: input.functionKey,
        teamId: parseId(input.teamId),
        startDate: input.startDate,
        endDate: input.endDate,
        termId: parseId(input.termId),
        firstName: input.firstName ?? null,
        lastName: input.lastName ?? null,
        confirmedExisting: input.confirmedExisting ?? false,
        membershipId: parseId(input.membershipId),
      }
      const result = await post<{ status: string; message?: string }>(
        '/api/v1/members',
        body,
        email(),
      )
      // Narrow to the union type the frontend `Api` expects
      if (result.status === 'needs_name') return { status: 'needs_name' }
      if (result.status === 'confirm_existing') return { status: 'confirm_existing' }
      if (result.status === 'created') return { status: 'created' }
      return { status: 'rejected', message: result.message ?? 'Unknown error' }
    },

    async getMembershipDetail(membershipId: string): Promise<MembershipDetail> {
      return get<MembershipDetail>(`/api/v1/members/${membershipId}`, email())
    },

    async extendTerm(membershipId: string, newEndDate: IsoDate): Promise<ActionResult> {
      const result = await post<{ status: string; message?: string }>(
        `/api/v1/members/${membershipId}/extend-term`,
        { newEndDate },
        email(),
      )
      if (result.status === 'ok') return { status: 'ok' }
      return { status: 'rejected', message: result.message ?? 'Unknown error' }
    },

    async moveToTeam(membershipId: string, teamId: string): Promise<ActionResult> {
      const result = await post<{ status: string; message?: string }>(
        `/api/v1/members/${membershipId}/move-to-team`,
        { teamId: parseId(teamId) },
        email(),
      )
      if (result.status === 'ok') return { status: 'ok' }
      return { status: 'rejected', message: result.message ?? 'Unknown error' }
    },
  }
}
