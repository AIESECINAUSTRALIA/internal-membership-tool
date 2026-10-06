import {
  Avatar,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Button,
  InputAdornment,
  List,
  ListItemAvatar,
  ListItemButton,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import { useEffect, useState } from 'react'

import { useApi } from '../../api/ApiContext'
import type { MemberSummaryRow, Permission } from '../../api/types'
import { rowActions, type Actor } from '../../auth/permissions'
import { fullName, roleLabel } from '../../lib/labels'
import { useDebounced } from '../../lib/useDebounced'
import { ManageMembershipPanel } from './ManageMembershipPanel'

interface Props {
  actor: Actor
  permissions: Permission[]
  canAddFunction: boolean
  onClose: () => void
  /** Called after a change is saved, with the message to show. */
  onDone: (message: string) => void
  /** Opens Add member for the person picked inside the hub. */
  onAddFunction: () => void
}

/**
 * The "Manage membership" entry point (spec §2A.5): pick anyone the actor may manage,
 * then move them to a team and/or extend their term. Separate from the per-row "..."
 * menu on the table (which still does one quick action at a time) — this is for
 * reaching someone who isn't already in view, or doing more than one thing at once.
 */
export function ManageMembershipHub({ actor, permissions, canAddFunction, onClose, onDone, onAddFunction }: Props) {
  const api = useApi()
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)
  const [candidates, setCandidates] = useState<MemberSummaryRow[]>([])
  const [selected, setSelected] = useState<MemberSummaryRow | null>(null)

  useEffect(() => {
    let cancelled = false
    // "Manageable" is filtered client-side after the fetch (the API has no
    // may-the-actor-manage-this-row filter), so the fetch itself has to cover
    // everyone in scope, not just a small page — otherwise a real match past the
    // first page silently never appears, however far you scroll.
    api.listMembers({ search: debouncedSearch, sort: null, page: 0, pageSize: 500, lcId: null }).then((page) => {
      if (cancelled) return
      const manageable = page.rows.filter((row) => {
        const a = rowActions(actor, permissions, row)
        return a.extendRoleIds.length > 0 || a.moveRoleIds.length > 0
      })
      setCandidates(manageable)
    })
    return () => {
      cancelled = true
    }
  }, [api, actor, permissions, debouncedSearch])

  if (selected) {
    const a = rowActions(actor, permissions, selected)
    return (
      <ManageMembershipPanel
        row={selected}
        teamEligibleRoleIds={a.moveRoleIds}
        termEligibleRoleIds={a.extendRoleIds}
        canAddFunction={canAddFunction}
        onClose={onClose}
        onDone={onDone}
        onAddFunction={onAddFunction}
      />
    )
  }

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Manage membership</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField
            label="Search people you can manage"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
            slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment> } }}
            fullWidth
          />
          {debouncedSearch && candidates.length === 0 && <Typography color="text.secondary">No data exists</Typography>}
          {candidates.length > 0 && (
            <List aria-label="Search results" sx={{ maxHeight: 320, overflowY: 'auto' }}>
              {candidates.map((row) => (
                <ListItemButton key={row.personId} onClick={() => setSelected(row)}>
                  <ListItemAvatar>
                    <Avatar>{(row.firstName[0] ?? '?').toUpperCase()}</Avatar>
                  </ListItemAvatar>
                  <ListItemText
                    primary={fullName(row.firstName, row.lastName)}
                    secondary={row.roles.map((r) => roleLabel(r.position, r.function)).join(', ')}
                  />
                </ListItemButton>
              ))}
            </List>
          )}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
      </DialogActions>
    </Dialog>
  )
}
