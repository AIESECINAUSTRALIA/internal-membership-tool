/// <reference types="vite/client" />

/** Every VITE_ variable the app reads. Documented in .env.example. */
interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_AUTH_MODE?: 'mock' | 'supabase'
  readonly VITE_SUPABASE_URL?: string
  readonly VITE_SUPABASE_ANON_KEY?: string
  readonly VITE_GOOGLE_HOSTED_DOMAIN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
