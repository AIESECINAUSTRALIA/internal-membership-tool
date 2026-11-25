import {
  Autocomplete,
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
  TextField,
  Typography,
} from '@mui/material'
import AddOutlined from '@mui/icons-material/AddOutlined'
import MoreVert from '@mui/icons-material/MoreVert'
import dayjs from 'dayjs'
import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'

import { useApi } from '../../api/ApiContext'
import type { AdminMembershipRow, AdminPersonRow } from '../../api/types'
import { fullName } from '../../lib/labels'
import { useDebounced } from '../../lib/useDebounced'
import { AssignMembershipDialog, CorrectMembershipDialog, EndMembershipDialog } from '../MembershipDialogs'

type MembershipAction = 'correct' | 'end'

const today = () => dayjs().format('YYYY-MM-DD')
const formatDate = (date: string | null) => (date ? dayjs(date).format('DD/MM/YYYY') : '—')

function statusOf(m: AdminMembershipRow): 'Current' | 'Upcoming' | 'Ended' {
  if (m.current) return 'Current'
  return m.startDate > today() ? 'Upcoming' : 'Ended'
}

/** Search people by name or email, the same list as the People screen. */
function PersonPicker({ value, onChange }: { value: AdminPersonRow | null; onChange: (person: AdminPersonRow | null) => void }) {
  const api = useApi()
  const [input, setInput] = useState('')
  const search = useDebounced(input)
  const [options, setOptions] = useState<AdminPersonRow[]>([])

  useEffect(() => {
    let cancelled = false
    api.listPeopleAdmin({ search, page: 0, pageSize: 10 }).then((page) => {
      if (!cancelled) setOptions(page.rows)
    })
    return () => {
      cancelled = true
    }
  }, [api, search])

  return (
    <Autocomplete
      value={value}
      onChange={(_event, person) => onChange(person)}
      inputValue={input}
      onInputChange={(_event, text) => setInput(text)}
      options={value && !options.some((o) => o.id === value.id) ? [value, ...options] : options}
      // The server already filtered by the search text.
      filterOptions={(all) => all}
      getOptionLabel={(p) => `${fullName(p.firstName, p.lastName)} (${p.email})`}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      noOptionsText="No data exists"
      renderInput={(params) => <TextField {...params} label="Person" placeholder="Search by name or email" />}
      sx={{ maxWidth: 520 }}
    />
  )
}

function MembershipActionsMenu({ membership, onChoose }: { membership: AdminMembershipRow; onChoose: (action: MembershipAction) => void }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const choose = (action: MembershipAction) => {
    setAnchor(null)
    onChoose(action)
  }
  const ended = membership.endDate !== null && membership.endDate < today()
  const label = [membership.position?.label, membership.lc.name].filter(Boolean).join(', ')
  return (
    <>
      <IconButton aria-label={`Actions for ${label}`} aria-haspopup="menu" onClick={(e) => setAnchor(e.currentTarget)}>
        <MoreVert />
      </IconButton>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        <MenuItem onClick={() => choose('correct')}>Correct</MenuItem>
        {!ended && <MenuItem onClick={() => choose('end')}>End</MenuItem>}
      </Menu>
    </>
  )
}

/**
 * The Memberships screen (spec §1.5, §2A.2): pick a person, then assign them a
 * membership (in any LC, which makes it a transfer if it's a new LC), correct a
 * mistake, or end one early. The admin-side version of the Membership summary's Add
 * member (§2A.5): an admin holding `manage` on `membership` isn't limited to one LC or
 * team, but the hierarchy rule (§3.4) and level-match rule (§3.6) still apply, and the
 * server checks both on every change.
 *
 * Coming from the People screen's "Manage memberships", the chosen person arrives in
 * the router state, not the URL, so no name or email ends up in the browser history.
 */
export function AdminMembershipsPage() {
  const api = useApi()
  const location = useLocation()
  const initial = (location.state as { person?: AdminPersonRow } | null)?.person ?? null
  const [person, setPerson] = useState<AdminPersonRow | null>(initial)
  const [dialog, setDialog] = useState<{ action: MembershipAction | 'assign'; membership: AdminMembershipRow | null } | null>(null)
  // Bumped after a change, so the table reloads for the same person.
  const [version, setVersion] = useState(0)
  const requestKey = person ? `${person.id}#${version}` : null
  const [result, setResult] = useState<{ key: string; rows: AdminMembershipRow[] } | null>(null)
  // Only show rows loaded for the person (and version) on screen now.
  const memberships = result !== null && result.key === requestKey ? result.rows : null

  useEffect(() => {
    if (!person || requestKey === null) return
    let cancelled = false
    api.listPersonMemberships(person.id).then((rows) => {
      if (!cancelled) setResult({ key: requestKey, rows })
    })
    return () => {
      cancelled = true
    }
  }, [api, person, requestKey])

  const load = () => setVersion((v) => v + 1)
  const closeDialog = () => setDialog(null)
  const deactivated = person?.status === 'inactive'
  const currentLcIds = [...new Set((memberships ?? []).filter((m) => m.current || m.startDate > today()).map((m) => m.lc.id))]

  return (
    <Stack spacing={3}>
      <Box>
        <Typography id="memberships-title" variant="h1" component="h1">
          Memberships
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 0.5, maxWidth: '65ch' }}>
          Assign someone to an LC, position and function, or correct or end one of their memberships. Nothing is deleted:
          ended memberships stay as history.
        </Typography>
      </Box>

      <PersonPicker value={person} onChange={setPerson} />

      {!person && <Typography color="text.secondary">Choose a person to see their memberships.</Typography>}

      {person && (
        <Paper variant="outlined" component="section" aria-labelledby="person-memberships-title" sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 2, flexWrap: 'wrap' }}>
              <Box>
                <Typography id="person-memberships-title" variant="h2" component="h2">
                  {fullName(person.firstName, person.lastName)}
                </Typography>
                <Typography color="text.secondary">{person.email}</Typography>
                {deactivated && (
                  <Typography color="text.secondary" sx={{ mt: 1 }}>
                    Deactivated. Reactivate them on the People screen before assigning a membership.
                  </Typography>
                )}
              </Box>
              <Button
                variant="contained"
                startIcon={<AddOutlined />}
                disabled={deactivated}
                onClick={() => setDialog({ action: 'assign', membership: null })}
              >
                Assign membership
              </Button>
            </Stack>

            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small" aria-labelledby="person-memberships-title">
                <TableHead>
                  <TableRow>
                    <TableCell>LC</TableCell>
                    <TableCell>Position</TableCell>
                    <TableCell>Function</TableCell>
                    <TableCell>Team</TableCell>
                    <TableCell>Term</TableCell>
                    <TableCell>Start</TableCell>
                    <TableCell>End</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell aria-label="Actions" />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {memberships?.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={9}>
                        <Typography sx={{ py: 1 }}>No data exists</Typography>
                      </TableCell>
                    </TableRow>
                  )}
                  {memberships?.map((m) => (
                    <TableRow key={m.id}>
                      <TableCell>{m.lc.name}</TableCell>
                      <TableCell>{m.position?.label ?? '—'}</TableCell>
                      <TableCell>{m.function?.label ?? '—'}</TableCell>
                      <TableCell>{m.teamName ?? '—'}</TableCell>
                      <TableCell>{m.termName ?? '—'}</TableCell>
                      <TableCell>{formatDate(m.startDate)}</TableCell>
                      <TableCell>{formatDate(m.endDate)}</TableCell>
                      <TableCell>
                        <Chip size="small" variant="outlined" color={m.current ? 'success' : 'default'} label={statusOf(m)} />
                      </TableCell>
                      <TableCell align="right">
                        <MembershipActionsMenu membership={m} onChoose={(action) => setDialog({ action, membership: m })} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          </Stack>
        </Paper>
      )}

      {person && dialog?.action === 'assign' && (
        <AssignMembershipDialog personId={person.id} currentLcIds={currentLcIds} onClose={closeDialog} onDone={load} />
      )}
      {dialog?.membership && dialog.action === 'correct' && (
        <CorrectMembershipDialog membership={dialog.membership} onClose={closeDialog} onDone={load} />
      )}
      {dialog?.membership && dialog.action === 'end' && (
        <EndMembershipDialog membership={dialog.membership} onClose={closeDialog} onDone={load} />
      )}
    </Stack>
  )
}
