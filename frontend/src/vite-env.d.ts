/// <reference types="vite/client" />

/** Every VITE_ variable the app reads. Documented in .env.example. */
interface ImportMetaEnv {
  readonly VITE_AUTH_MODE?: 'mock' | 'expa'
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
