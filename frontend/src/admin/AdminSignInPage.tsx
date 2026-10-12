import { Button, Typography } from '@mui/material'
import { useState } from 'react'

import { useAuth } from '../auth/authContext'
import { AuthLayout } from '../layout/AuthLayout'

/**
 * The Admin console's own sign-in page (spec §2A.2): a separate address
 * (`/admin/sign-in`) from the main app's `/sign-in`, so a normal user never lands here
 * by following a link. PLACEHOLDER, same as the main sign-in (§2A.3): one plain button
 * until Google sign-in is wired up, at which point this becomes a single "Sign in with
 * Google" button, same as the main app's.
 */
export function AdminSignInPage() {
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
          Development sign-in. It becomes a single &ldquo;Sign in with Google&rdquo; button once Google sign-in
          is connected.
        </Typography>
      }
    >
      <Typography variant="displaySm" component="h1">
        Admin console
      </Typography>
      <Typography sx={{ mt: 1.5, mb: 4 }}>Use your AIESEC Google account. Access is restricted.</Typography>
      <Button variant="contained" size="large" fullWidth onClick={handleSignIn} disabled={busy}>
        Sign in
      </Button>
    </AuthLayout>
  )
}
