/**
 * The parts of `Api` that talk to the real backend.
 *
 * Only Profile (spec §2A.9) is real so far: `getMe` and `updateMyCustomFields`.
 * `api/index.ts` combines these with the mock for every other method. As more
 * endpoints land, add their methods here; once every method is here, the mock goes.
 *
 * Who is signed in: until real sign-in (ticket 7) exists, the backend trusts an
 * `X-Actor-Email` header (only when `DEV_ACTOR_HEADER_ENABLED=true`). Ticket 7
 * replaces `authHeaders` below with the Supabase access token. Nothing else changes.
 */
import type { Api, CustomFieldValue, Me } from '../types'

export type HttpApi = Pick<Api, 'getMe' | 'updateMyCustomFields'>

export interface HttpApiOptions {
  /** e.g. "http://localhost:8000" (`VITE_API_URL`). */
  baseUrl: string
  /** Dev only: the AIESEC email to act as (`VITE_DEV_ACTOR_EMAIL`). */
  actorEmail: string
}

/** Thrown for any non-2xx response. `message` is the server's explanation. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function errorFrom(response: Response): Promise<ApiError> {
  // FastAPI errors look like {"detail": "..."} (or a list, for request-shape errors).
  const body = await response.json().catch(() => null)
  const detail: unknown = body?.detail
  const message = typeof detail === 'string' ? detail : `Request failed (${response.status})`
  return new ApiError(response.status, message)
}

export function createHttpApi({ baseUrl, actorEmail }: HttpApiOptions): HttpApi {
  const authHeaders = (): Record<string, string> => ({ 'X-Actor-Email': actorEmail })

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${baseUrl}/api/v1${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...authHeaders(), ...init.headers },
    })
    if (!response.ok) throw await errorFrom(response)
    return (await response.json()) as T
  }

  return {
    async getMe() {
      try {
        return await request<Me>('/me')
      } catch (error) {
        // 401 = nobody signed in, which `getMe` reports as null.
        if (error instanceof ApiError && error.status === 401) return null
        throw error
      }
    },

    async updateMyCustomFields(values: Record<string, CustomFieldValue>) {
      return request<Me>('/me/custom-fields', { method: 'PATCH', body: JSON.stringify(values) })
    },
  }
}
