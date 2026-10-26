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
import { useCallback, useEffect, useState } from 'react'

import { useApi } from '../../api/ApiContext'
import { useReferenceData } from '../../api/ReferenceDataContext'
import type { Lc } from '../../api/types'
import { can } from '../../auth/permissions'
import { useAuth } from '../../auth/authContext'
import {
  AddLcDialog,
  MergeLcDialog,
  RenameLcDialog,
  SetLcActiveDialog,
  SetLcStateDialog,
} from '../LcDialogs'

type LcAction = 'add' | 'rename' | 'set_state' | 'set_inactive' | 'set_active' | 'merge'

/** The dialog that is open: an action, plus the LC it applies to (none for "add"). */
interface OpenDialog {
  action: LcAction
  lc: Lc | null
}

/** The per-row "..." menu. Inactive LCs can only be reactivated or renamed. */
function LcActionsMenu({ lc, onChoose }: { lc: Lc; onChoose: (action: LcAction) => void }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const choose = (action: LcAction) => {
    setAnchor(null)
    onChoose(action)
  }
  const isMc = lc.type === 'mc'

  return (
    <>
      <IconButton aria-label={`Actions for ${lc.name}`} aria-haspopup="menu" onClick={(e) => setAnchor(e.currentTarget)}>
        <MoreVert />
      </IconButton>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        <MenuItem onClick={() => choose('rename')}>Rename</MenuItem>
        {!isMc && <MenuItem onClick={() => choose('set_state')}>Set state</MenuItem>}
        {lc.active && !isMc && <MenuItem onClick={() => choose('merge')}>Merge into another LC</MenuItem>}
        {lc.active && !isMc && <MenuItem onClick={() => choose('set_inactive')}>Mark inactive</MenuItem>}
        {!lc.active && <MenuItem onClick={() => choose('set_active')}>Mark active</MenuItem>}
      </Menu>
    </>
  )
}

/**
 * The LCs screen (spec §1.5, §2A.2): add, rename, set state, mark inactive, merge.
 * There is no delete: marking an LC inactive is the soft delete, and it can be undone.
 * Actions are only offered to people holding `manage` on `lc`; the server checks again.
 */
export function AdminLcsPage() {
  const api = useApi()
  const { me } = useAuth()
  const { invalidate: refreshReferenceData } = useReferenceData()
  const [lcs, setLcs] = useState<Lc[]>([])
  const [dialog, setDialog] = useState<OpenDialog | null>(null)
  const canManage = me !== null && can(me.permissions, 'lc', 'manage')

  const load = useCallback(() => {
    api.listLcsAdmin().then(setLcs)
  }, [api])

  useEffect(() => {
    load()
  }, [load])

  // Other screens read LCs from the shared reference data, so refresh that too.
  const handleDone = () => {
    load()
    refreshReferenceData()
  }

  const mergeTargets = (source: Lc) => lcs.filter((lc) => lc.active && lc.type === 'lc' && lc.id !== source.id)
  const closeDialog = () => setDialog(null)

  return (
    <Stack spacing={3}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 2, flexWrap: 'wrap' }}>
        <Box>
          <Typography id="lcs-title" variant="h1" component="h1">
            LCs
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5, maxWidth: '65ch' }}>
            Local Committees and the MC. Renaming, merging or marking one inactive never breaks the history that points at it.
          </Typography>
        </Box>
        {canManage && (
          <Button variant="contained" startIcon={<AddOutlined />} onClick={() => setDialog({ action: 'add', lc: null })}>
            Add LC
          </Button>
        )}
      </Stack>
      <Paper variant="outlined" component="section" aria-labelledby="lcs-title" sx={{ p: 3 }}>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" aria-labelledby="lcs-title">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>State</TableCell>
                <TableCell>Status</TableCell>
                {canManage && <TableCell aria-label="Actions" />}
              </TableRow>
            </TableHead>
            <TableBody>
              {lcs.map((lc) => (
                <TableRow key={lc.id}>
                  <TableCell>{lc.name}</TableCell>
                  <TableCell>{lc.type === 'mc' ? 'MC' : 'Local Committee'}</TableCell>
                  <TableCell>{lc.state ?? '—'}</TableCell>
                  <TableCell>
                    <Chip size="small" variant="outlined" label={lc.active ? 'Active' : 'Inactive'} />
                  </TableCell>
                  {canManage && (
                    <TableCell align="right">
                      <LcActionsMenu lc={lc} onChoose={(action) => setDialog({ action, lc })} />
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      </Paper>

      {dialog?.action === 'add' && <AddLcDialog onClose={closeDialog} onDone={handleDone} />}
      {dialog?.lc && dialog.action === 'rename' && (
        <RenameLcDialog lc={dialog.lc} onClose={closeDialog} onDone={handleDone} />
      )}
      {dialog?.lc && dialog.action === 'set_state' && (
        <SetLcStateDialog lc={dialog.lc} onClose={closeDialog} onDone={handleDone} />
      )}
      {dialog?.lc && dialog.action === 'set_inactive' && (
        <SetLcActiveDialog lc={dialog.lc} makeActive={false} onClose={closeDialog} onDone={handleDone} />
      )}
      {dialog?.lc && dialog.action === 'set_active' && (
        <SetLcActiveDialog lc={dialog.lc} makeActive onClose={closeDialog} onDone={handleDone} />
      )}
      {dialog?.lc && dialog.action === 'merge' && (
        <MergeLcDialog lc={dialog.lc} targets={mergeTargets(dialog.lc)} onClose={closeDialog} onDone={handleDone} />
      )}
    </Stack>
  )
}
