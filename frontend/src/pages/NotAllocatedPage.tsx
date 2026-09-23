import { Button, Typography } from '@mui/material'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/authContext'
import { AuthLayout } from '../layout/AuthLayout'

/**
 * Shown to someone who signed in but has no active membership: not added yet, or their
 * term has ended (spec §2A.3, §9). The message is fixed wording from the spec.
 */
export function NotAllocatedPage() {
  const { signOut } = useAuth()
  const navigate = useNavigate()

  const handleSignOut = async () => {
    await signOut()
    navigate('/sign-in', { replace: true })
  }

  return (
    <AuthLayout>
      <Typography variant="displaySm" component="h1" sx={{ mb: 4, textWrap: 'balance' }}>
        You have not been allocated yet, please contact someone in your EB or MC
      </Typography>
      <Button variant="outlined" color="primary" size="large" onClick={handleSignOut}>
        Sign out
      </Button>
    </AuthLayout>
  )
}
