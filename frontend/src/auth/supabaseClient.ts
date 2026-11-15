/**
 * The one Supabase client for the browser. Only used when VITE_AUTH_MODE=supabase
 * (see api/index.ts and docs/auth.md).
 *
 * The anon key is safe in the browser by design: it identifies the project but grants
 * nothing on its own. Never put a service-role key in a VITE_ variable.
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js'

export function createSupabaseClient(): SupabaseClient {
  const url = import.meta.env.VITE_SUPABASE_URL
  const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY
  if (!url || !anonKey) {
    throw new Error(
      'VITE_AUTH_MODE=supabase needs VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY. See docs/auth.md.',
    )
  }
  return createClient(url, anonKey, {
    auth: {
      // PKCE: Google's answer comes back as a one-time code that only this browser can
      // exchange, instead of a token in the URL.
      flowType: 'pkce',
      detectSessionInUrl: true,
      persistSession: true,
      autoRefreshToken: true,
    },
  })
}
