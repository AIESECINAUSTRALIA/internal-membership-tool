import { Paper, Typography } from '@mui/material'

import { useAuth } from '../auth/authContext'
import { can } from '../auth/permissions'
import { PlannedPage } from '../components/PlannedPage'

/**
 * Settings (spec §2A.8). Mostly a placeholder. The one real item planned for this term is
 * the Functions screen, shown only to positions that hold `manage` on `function` (every
 * MC position, through the permission matrix).
 */
export function SettingsPage() {
  const { me } = useAuth()
  const canManageFunctions = me ? can(me.permissions, 'function', 'manage') : false

  return (
    <PlannedPage
      title="Settings"
      intro="General settings for your account. There are none to change yet."
      willDo={['Change general settings, once there are any.']}
    >
      {canManageFunctions && (
        <Paper variant="outlined" component="section" aria-labelledby="functions-title" sx={{ p: 3 }}>
          <Typography id="functions-title" variant="h2" component="h2">
            Functions
          </Typography>
          <Typography sx={{ mt: 1, maxWidth: '65ch' }}>
            As an MC position, you will add, rename and deactivate functions here. Deactivating
            a function stops it being given to new members. It doesn&rsquo;t end existing
            memberships or change history. Not built yet.
          </Typography>
        </Paper>
      )}
    </PlannedPage>
  )
}
