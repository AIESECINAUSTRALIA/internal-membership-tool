import { Alert, Button, Typography } from '@mui/material'
import { useState } from 'react'

import { useApi } from '../api/ApiContext'
import { useAuth } from '../auth/authContext'
import { AuthLayout } from '../layout/AuthLayout'

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

  const message = startError ?? error

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
