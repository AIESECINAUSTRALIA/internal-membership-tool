/**
 * Which sign-in the app uses (docs/auth.md).
 *
 * - `expa`: real EXPA sign-in, using the backend's server-side session.
 * - `mock`: the development sign-in button and personas. Never real access.
 *
 * Spec §2A.3: mock sign-in must be off in every deployed environment.
 * Production builds always use EXPA. The dev server and tests default
 * to mock unless VITE_AUTH_MODE=expa is explicitly set.
 */
export type AuthMode = 'mock' | 'expa'

export function pickAuthMode(env: {
  VITE_AUTH_MODE?: string
  PROD: boolean
}): AuthMode {
  if (env.PROD) return 'expa'
  return env.VITE_AUTH_MODE === 'expa' ? 'expa' : 'mock'
}
