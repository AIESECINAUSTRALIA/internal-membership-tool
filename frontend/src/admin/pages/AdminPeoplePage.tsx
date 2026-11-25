import {
  Box,
  Button,
  Chip,
  IconButton,
  InputAdornment,
  Menu,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import PersonAddAlt1Outlined from '@mui/icons-material/PersonAddAlt1Outlined'
import MoreVert from '@mui/icons-material/MoreVert'
import SearchIcon from '@mui/icons-material/Search'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useApi } from '../../api/ApiContext'
import type { AdminPersonQuery, AdminPersonRow, Page } from '../../api/types'
import { useAuth } from '../../auth/authContext'
import { can } from '../../auth/permissions'
import { fullName } from '../../lib/labels'
import { useDebounced } from '../../lib/useDebounced'
import { AddPersonDialog, EditPersonDialog, SetPersonActiveDialog, UnlinkExpaDialog } from '../PeopleDialogs'

type PersonAction = 'edit' | 'memberships' | 'deactivate' | 'reactivate' | 'unlink'

/** The per-row "..." menu. A deactivated person can only be edited or reactivated. */
function PersonActionsMenu({
  person,
  canManageMemberships,
  onChoose,
}: {
  person: AdminPersonRow
  canManageMemberships: boolean
  onChoose: (action: PersonAction) => void
}) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const choose = (action: PersonAction) => {
    setAnchor(null)
    onChoose(action)
  }
  const deactivated = person.status === 'inactive'
  return (
    <>
      <IconButton
        aria-label={`Actions for ${fullName(person.firstName, person.lastName)}`}
        aria-haspopup="menu"
        onClick={(e) => setAnchor(e.currentTarget)}
      >
        <MoreVert />
      </IconButton>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        <MenuItem onClick={() => choose('edit')}>Edit</MenuItem>
        {canManageMemberships && <MenuItem onClick={() => choose('memberships')}>Manage memberships</MenuItem>}
        {person.expaLinked && <MenuItem onClick={() => choose('unlink')}>Unlink EXPA</MenuItem>}
        {deactivated ? (
          <MenuItem onClick={() => choose('reactivate')}>Reactivate</MenuItem>
        ) : (
          <MenuItem onClick={() => choose('deactivate')}>Deactivate</MenuItem>
        )}
      </Menu>
    </>
  )
}

/** Deactivated beats everything; otherwise whether they hold a role today. */
function StatusChip({ person }: { person: AdminPersonRow }) {
  if (person.status === 'inactive') return <Chip size="small" variant="outlined" label="Deactivated" />
  return person.active ? (
    <Chip size="small" variant="outlined" color="success" label="Active" />
  ) : (
    <Chip size="small" variant="outlined" label="No current role" />
  )
}

/**
 * The People screen (spec §1.5, §2A.2): add, edit, deactivate people, identified by
 * their AIESEC email. Unlike the Membership summary (§2A.5), this list DOES show email
 * and includes people with no current membership — that's the point of an admin view.
 * Search and pagination run through the API, same pattern as the Membership page.
 *
 * There is no delete. Deactivating stops someone signing in and ends their current
 * memberships, but keeps every row their history points at (§1.5). Each action is
 * checked again on the server, including the hierarchy rule (§3.4).
 */
export function AdminPeoplePage() {
  const api = useApi()
  const navigate = useNavigate()
  const { me } = useAuth()
  const canManageMemberships = me !== null && can(me.permissions, 'membership', 'manage')
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(10)
  // Bumped after a change, so the table reloads with the same query.
  const [version, setVersion] = useState(0)
  const [dialog, setDialog] = useState<{ action: PersonAction | 'add'; person: AdminPersonRow | null } | null>(null)

  const query: AdminPersonQuery = useMemo(() => ({ search: debouncedSearch, page, pageSize }), [debouncedSearch, page, pageSize])
  const queryKey = `${JSON.stringify(query)}#${version}`
  const [result, setResult] = useState<{ key: string; page: Page<AdminPersonRow> } | null>(null)
  const loading = result?.key !== queryKey

  useEffect(() => {
    let cancelled = false
    api.listPeopleAdmin(query).then((p) => {
      if (!cancelled) setResult({ key: queryKey, page: p })
    })
    return () => {
      cancelled = true
    }
  }, [api, query, queryKey])

  const rows = result?.page.rows ?? []
  const closeDialog = () => setDialog(null)
  const reload = () => setVersion((v) => v + 1)

  const choose = (person: AdminPersonRow, action: PersonAction) => {
    // Router state, not the URL: no name or email in the browser history.
    if (action === 'memberships') navigate('/admin/memberships', { state: { person } })
    else setDialog({ action, person })
  }

  return (
    <Stack spacing={3}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 2, flexWrap: 'wrap' }}>
        <Box>
          <Typography variant="h1" component="h1">
            People
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5, maxWidth: '65ch' }}>
            Everyone in the system, identified by their AIESEC email. Deactivating someone keeps their history.
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<PersonAddAlt1Outlined />} onClick={() => setDialog({ action: 'add', person: null })}>
          Add person
        </Button>
      </Stack>

      <TextField
        label="Search people"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value)
          setPage(0)
        }}
        slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment> } }}
        sx={{ maxWidth: 420 }}
      />

      <Box sx={{ overflowX: 'auto' }}>
        <Table size="small" aria-label="People" sx={{ opacity: loading ? 0.6 : 1 }}>
          <TableHead>
            <TableRow>
              <TableCell>First name</TableCell>
              <TableCell>Last name</TableCell>
              <TableCell>Email</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>EXPA</TableCell>
              <TableCell aria-label="Actions" />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography sx={{ py: 1 }}>No data exists</Typography>
                </TableCell>
              </TableRow>
            )}
            {rows.map((person) => (
              <TableRow key={person.id}>
                <TableCell>{person.firstName}</TableCell>
                <TableCell>{person.lastName}</TableCell>
                <TableCell>{person.email}</TableCell>
                <TableCell>
                  <StatusChip person={person} />
                </TableCell>
                {/* Words, not just colour, so the state is clear to everyone (WCAG AA). */}
                <TableCell>{person.expaLinked ? 'Linked' : 'Not linked'}</TableCell>
                <TableCell align="right">
                  <PersonActionsMenu
                    person={person}
                    canManageMemberships={canManageMemberships}
                    onChoose={(action) => choose(person, action)}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>
      <TablePagination
        component="div"
        count={result?.page.total ?? 0}
        page={page}
        onPageChange={(_event, newPage) => setPage(newPage)}
        rowsPerPage={pageSize}
        onRowsPerPageChange={(e) => {
          setPageSize(parseInt(e.target.value, 10))
          setPage(0)
        }}
        rowsPerPageOptions={[10, 25, 50]}
      />

      {dialog?.action === 'add' && <AddPersonDialog onClose={closeDialog} onDone={reload} />}
      {dialog?.person && dialog.action === 'edit' && (
        <EditPersonDialog person={dialog.person} onClose={closeDialog} onDone={reload} />
      )}
      {dialog?.person && dialog.action === 'unlink' && (
        <UnlinkExpaDialog person={dialog.person} onClose={closeDialog} onDone={reload} />
      )}
      {dialog?.person && (dialog.action === 'deactivate' || dialog.action === 'reactivate') && (
        <SetPersonActiveDialog
          person={dialog.person}
          makeActive={dialog.action === 'reactivate'}
          onClose={closeDialog}
          onDone={reload}
        />
      )}
    </Stack>
  )
}
