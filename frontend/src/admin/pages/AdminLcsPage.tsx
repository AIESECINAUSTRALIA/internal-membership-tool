import {
  Box,
  Button,
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

import { useReferenceData } from '../../api/ReferenceDataContext'
import type { Lc } from '../../api/types'
import { NotBuiltYetDialog } from '../../components/NotBuiltYetDialog'

type LcAction = 'rename' | 'set_state' | 'mark_inactive' | 'merge'

const ACTION_COPY: Record<LcAction, { title: (lc: Lc) => string; body: string }> = {
  rename: {
    title: (lc) => `Rename ${lc.name}`,
    body: 'This will change the LC name everywhere it is shown, without touching its history.',
  },
  set_state: {
    title: (lc) => `Set state for ${lc.name}`,
    body: 'This will set the LC’s state, which drives its timezone for date-scoped data.',
  },
  mark_inactive: {
    title: (lc) => `Mark ${lc.name} inactive`,
    body: 'This will stop the LC being offered when someone is added, without touching existing members or history.',
  },
  merge: {
    title: (lc) => `Merge ${lc.name}`,
    body: 'This will move another LC’s members and history into this one, then mark the other LC inactive.',
  },
}

/** The per-row "..." menu: every action from spec §1.5/§2A.2's LCs row. */
function LcActionsMenu({ lc, onChoose }: { lc: Lc; onChoose: (action: LcAction) => void }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const choose = (action: LcAction) => {
    setAnchor(null)
    onChoose(action)
  }
  return (
    <>
      <IconButton aria-label={`Actions for ${lc.name}`} aria-haspopup="menu" onClick={(e) => setAnchor(e.currentTarget)}>
        <MoreVert />
      </IconButton>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        <MenuItem onClick={() => choose('rename')}>Rename</MenuItem>
        <MenuItem onClick={() => choose('set_state')}>Set state</MenuItem>
        <MenuItem onClick={() => choose('mark_inactive')}>Mark inactive</MenuItem>
        <MenuItem onClick={() => choose('merge')}>Merge into another LC</MenuItem>
      </Menu>
    </>
  )
}

/**
 * The LCs screen (spec §1.5, §2A.2): add, rename, set state, mark inactive, merge.
 * Reads the real reference data, same as the rest of the app; the actions are stubs
 * until the backend exists, following the same pattern as Settings' Functions screen.
 */
export function AdminLcsPage() {
  const { reference } = useReferenceData()
  const lcs: Lc[] = reference?.lcs ?? []
  const [dialog, setDialog] = useState<{ title: string; body: string } | null>(null)

  return (
    <Stack spacing={3}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 2, flexWrap: 'wrap' }}>
        <Box>
          <Typography id="lcs-title" variant="h1" component="h1">
            LCs
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5, maxWidth: '65ch' }}>
            Local Committees and the MC. Renaming or marking one inactive never breaks the history that points at it.
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<AddOutlined />}
          onClick={() => setDialog({ title: 'Add LC', body: 'This will add a new LC, available to add members to.' })}
        >
          Add LC
        </Button>
      </Stack>
      <Paper variant="outlined" component="section" aria-labelledby="lcs-title" sx={{ p: 3 }}>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" aria-labelledby="lcs-title">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Type</TableCell>
                <TableCell aria-label="Actions" />
              </TableRow>
            </TableHead>
            <TableBody>
              {lcs.map((lc) => (
                <TableRow key={lc.id}>
                  <TableCell>{lc.name}</TableCell>
                  <TableCell>{lc.type === 'mc' ? 'MC' : 'Local Committee'}</TableCell>
                  <TableCell align="right">
                    <LcActionsMenu lc={lc} onChoose={(action) => setDialog({ title: ACTION_COPY[action].title(lc), body: ACTION_COPY[action].body })} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      </Paper>
      {dialog && (
        <NotBuiltYetDialog open title={dialog.title} onClose={() => setDialog(null)}>
          {dialog.body}
        </NotBuiltYetDialog>
      )}
    </Stack>
  )
}
