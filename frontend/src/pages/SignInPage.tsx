import { Button, Typography } from '@mui/material'
import { useState } from 'react'

import { useAuth } from '../auth/authContext'
import { AuthLayout } from '../layout/AuthLayout'

/**
 * Sign in (spec §2A.3). PLACEHOLDER: one plain button so the app can be built and
 * demoed before Google sign-in exists. When OAuth lands (§9) this becomes a single
 * "Sign in with Google" button and the footer note is deleted. There is no other way in.
 */
export function SignInPage() {
  const { signIn } = useAuth()
  const [busy, setBusy] = useState(false)

  const handleSignIn = async () => {
    setBusy(true)
    try {
      await signIn() // the guard on this route then sends the person onward
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout
      footer={
        <Typography variant="caption">
          Development sign-in. It becomes a single &ldquo;Sign in with Google&rdquo; button once Google
          sign-in is connected.
        </Typography>
      }
    >
      <Typography variant="displaySm" component="h1">
        Sign in
      </Typography>
      <Typography sx={{ mt: 1.5, mb: 4 }}>Use your AIESEC Google account.</Typography>
      <Button variant="contained" size="large" fullWidth onClick={handleSignIn} disabled={busy}>
        Sign in
      </Button>
      <Typography color="text.secondary" sx={{ mt: 3, textWrap: 'balance' }}>
        New here? Someone in your EB or MC needs to add you first.
      </Typography>
    </AuthLayout>
  )
}
