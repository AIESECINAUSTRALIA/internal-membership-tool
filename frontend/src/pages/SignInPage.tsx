import { Alert, Button, Typography } from '@mui/material'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { useApi } from '../api/ApiContext'
import { useAuth } from '../auth/authContext'
import { AuthLayout } from '../layout/AuthLayout'

/**
 * Why a sign-in failed, keyed by the `?error=` value the backend's
 * `/auth/callback` adds when it redirects here. Keep in sync with `SignInError` in
 * `backend/app/api/v1/auth.py`.
 */
const SIGN_IN_ERRORS: Record<string, string> = {
  denied: 'Sign-in was cancelled. Please try again.',
  expired: 'Your sign-in attempt expired. Please try again.',
  expa: 'We could not reach EXPA. Please try again in a moment.',
  domain: 'Please sign in with your AIESEC account.',
  // Fixed wording from spec §2A.3 (same as the not-allocated page).
  not_allocated: 'You have not been allocated yet, please contact someone in your EB or MC',
}

/**
 * Sign in (spec §2A.3). With real sign-in (VITE_AUTH_MODE=supabase, docs/auth.md) this
 * is a single "Sign in with Google" button. In mock mode it is the development
 * placeholder: one plain button that signs in as a mock persona. There is no other way in.
 */
export function SignInPage() {
  const { signIn, error } = useAuth()
  const { signInMethod } = useApi()
  const google = signInMethod === 'google'
  const [busy, setBusy] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  const [searchParams] = useSearchParams()
  const callbackCode = searchParams.get('error')
  // An unknown code still gets a message rather than silence.
  const callbackError = callbackCode
    ? (SIGN_IN_ERRORS[callbackCode] ?? 'Sign-in failed. Please try again.')
    : null

  const handleSignIn = async () => {
    setBusy(true)
    setStartError(null)
    try {
      // Mock: the guard on this route then sends the person onward.
      // Google: the browser leaves for Google and comes back here, signed in.
      await signIn()
    } catch {
      setStartError('Sign-in could not start. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  const message = startError ?? error ?? callbackError

  return (
    <AuthLayout
      footer={
        google ? undefined : (
          <Typography variant="caption">
            Development sign-in. It becomes a single &ldquo;Sign in with Google&rdquo; button once
            Google sign-in is connected.
          </Typography>
        )
      }
    >
      <Typography variant="displaySm" component="h1">
        Sign in
      </Typography>
      <Typography sx={{ mt: 1.5, mb: 4 }}>Use your AIESEC Google account.</Typography>
      {message && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {message}
        </Alert>
      )}
      <Button variant="contained" size="large" fullWidth onClick={handleSignIn} disabled={busy}>
        {google ? 'Sign in with Google' : 'Sign in'}
      </Button>
      <Typography color="text.secondary" sx={{ mt: 3, textWrap: 'balance' }}>
        New here? Someone in your EB or MC needs to add you first.
      </Typography>
    </AuthLayout>
  )
}
