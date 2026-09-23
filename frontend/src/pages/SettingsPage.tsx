import {
  Box,
  Button,
  Chip,
  IconButton,
  Menu,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import AddOutlined from '@mui/icons-material/AddOutlined'
import MoreVert from '@mui/icons-material/MoreVert'
import { useState } from 'react'

import { useReferenceData } from '../api/ReferenceDataContext'
import type { FunctionDef } from '../api/types'
import { useAuth } from '../auth/authContext'
import { can } from '../auth/permissions'
import { NotBuiltYetDialog } from '../components/NotBuiltYetDialog'

/** The per-row "..." menu: Rename and Deactivate, both stubs until built. */
function FunctionActionsMenu({ fn, onChoose }: { fn: FunctionDef; onChoose: (action: 'rename' | 'deactivate') => void }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const choose = (action: 'rename' | 'deactivate') => {
    setAnchor(null)
    onChoose(action)
  }
  return (
    <>
      <IconButton aria-label={`Actions for ${fn.label}`} aria-haspopup="menu" onClick={(e) => setAnchor(e.currentTarget)}>
        <MoreVert />
      </IconButton>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        <MenuItem onClick={() => choose('rename')}>Rename</MenuItem>
        <MenuItem onClick={() => choose('deactivate')} disabled={!fn.active}>
          Deactivate
        </MenuItem>
      </Menu>
    </>
  )
}

/**
 * The Functions screen (spec §2A.8): every MC position may add, rename and
 * deactivate functions. Reads the real reference data; the three actions are stubs
 * until the backend exists. Deactivating stops a function being given to new
 * members, without ending existing memberships or changing history (spec §1.5).
 */
function FunctionsSection() {
  const { reference } = useReferenceData()
  const functions: FunctionDef[] = reference?.functions ?? []
  const [dialog, setDialog] = useState<{ title: string; body: string } | null>(null)

  return (
    <Paper variant="outlined" component="section" aria-labelledby="functions-title" sx={{ p: 3 }}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2, mb: 2 }}>
        <Typography id="functions-title" variant="h2" component="h2">
          Functions
        </Typography>
        <Button
          variant="outlined"
          startIcon={<AddOutlined />}
          onClick={() => setDialog({ title: 'Add function', body: 'This will add a new function, available to every LC.' })}
        >
          Add function
        </Button>
      </Stack>
      <Typography color="text.secondary" sx={{ mb: 2, maxWidth: '65ch' }}>
        Deactivating a function stops it being given to new members. It doesn&rsquo;t end existing memberships or change
        history.
      </Typography>
      <Box sx={{ overflowX: 'auto' }}>
        <Table size="small" aria-labelledby="functions-title">
          <TableHead>
            <TableRow>
              <TableCell>Function</TableCell>
              <TableCell>Status</TableCell>
              <TableCell aria-label="Actions" />
            </TableRow>
          </TableHead>
          <TableBody>
            {functions.map((fn) => (
              <TableRow key={fn.key}>
                <TableCell>{fn.label}</TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    label={fn.active ? 'Active' : 'Inactive'}
                    color={fn.active ? 'success' : 'default'}
                    variant="outlined"
                  />
                </TableCell>
                <TableCell align="right">
                  <FunctionActionsMenu
                    fn={fn}
                    onChoose={(action) =>
                      setDialog(
                        action === 'rename'
                          ? { title: `Rename ${fn.label}`, body: 'This will change the label everywhere it is shown.' }
                          : {
                              title: `Deactivate ${fn.label}`,
                              body: 'This will stop it being offered when someone is added, without touching existing members.',
                            },
                      )
                    }
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>
      {dialog && (
        <NotBuiltYetDialog open title={dialog.title} onClose={() => setDialog(null)}>
          {dialog.body}
        </NotBuiltYetDialog>
      )}
    </Paper>
  )
}

/**
 * Settings (spec §2A.8). Mostly a placeholder: there are no general settings to
 * change yet. The one real item planned for this term is the Functions screen, shown
 * only to positions that hold `manage` on `function` (every MC position, §2A.8).
 */
export function SettingsPage() {
  const { me } = useAuth()
  const canManageFunctions = me ? can(me.permissions, 'function', 'manage') : false

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h1" component="h1">
          Settings
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 0.5, maxWidth: '65ch' }}>
          General settings for your account. There are none to change yet.
        </Typography>
      </Box>
      {canManageFunctions && <FunctionsSection />}
    </Stack>
  )
}
