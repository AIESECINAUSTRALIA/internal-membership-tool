/**
 * Which sign-in the app uses (docs/auth.md).
 *
 * - `supabase`: real "Sign in with Google", checked by the backend.
 * - `mock`: the development sign-in button and personas. Never real access.
 *
 * Spec §2A.3: the placeholder must be off in any deployed environment. So when
 * VITE_AUTH_MODE is not set, a production build (`npm run build`, i.e. anything
 * deployed) uses real sign-in, and only the dev server and tests default to the mock.
 * Setting VITE_AUTH_MODE explicitly always wins, so a demo build can still opt in.
 */
export type AuthMode = 'mock' | 'supabase'

export function pickAuthMode(env: { VITE_AUTH_MODE?: string; PROD: boolean }): AuthMode {
  if (env.VITE_AUTH_MODE === 'supabase' || env.VITE_AUTH_MODE === 'mock') return env.VITE_AUTH_MODE
  return env.PROD ? 'supabase' : 'mock'
}
