
/**
 * Notifies the authentication provider when the backend rejects a session.
 *
 * HTTP requests can discover an expired or revoked session before the
 * authentication provider does. This keeps session handling in one place
 * rather than making every page handle HTTP 401 separately.
 */
export function createSessionEvents() {
  const listeners = new Set<() => void>()

  return {
    subscribe(listener: () => void): () => void {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },

    notify(): void {
      listeners.forEach((listener) => listener())
    },
  }
}
