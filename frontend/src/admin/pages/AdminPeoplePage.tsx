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

import { useApi } from '../../api/ApiContext'
import type { AdminPersonQuery, AdminPersonRow, Page } from '../../api/types'
import { NotBuiltYetDialog } from '../../components/NotBuiltYetDialog'
import { fullName } from '../../lib/labels'
import { useDebounced } from '../../lib/useDebounced'

type PersonAction = 'edit' | 'deactivate'

/** The per-row "..." menu: Edit and Deactivate, both stubs until built. */
function PersonActionsMenu({ person, onChoose }: { person: AdminPersonRow; onChoose: (action: PersonAction) => void }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const choose = (action: PersonAction) => {
    setAnchor(null)
    onChoose(action)
  }
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
        <MenuItem onClick={() => choose('deactivate')} disabled={!person.active}>
          Deactivate
        </MenuItem>
      </Menu>
    </>
  )
}

/**
 * The People screen (spec §1.5, §2A.2): add, edit, deactivate people, identified by
 * their AIESEC email. Unlike the Membership summary (§2A.5), this list DOES show email
 * and includes people with no current membership — that's the point of an admin view.
 * Search and pagination run through the API, same pattern as the Membership page; add
 * and edit are stubs until the backend exists.
 */
export function AdminPeoplePage() {
  const api = useApi()
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(10)
  const [dialog, setDialog] = useState<{ title: string; body: string } | null>(null)

  const query: AdminPersonQuery = useMemo(() => ({ search: debouncedSearch, page, pageSize }), [debouncedSearch, page, pageSize])
  const queryKey = JSON.stringify(query)
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

  return (
    <Stack spacing={3}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 2, flexWrap: 'wrap' }}>
        <Box>
          <Typography variant="h1" component="h1">
            People
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5, maxWidth: '65ch' }}>
            Everyone in the system, identified by their AIESEC email.
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<PersonAddAlt1Outlined />}
          onClick={() => setDialog({ title: 'Add person', body: 'This will add a new person, identified by their AIESEC email.' })}
        >
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
              <TableCell aria-label="Actions" />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={5}>
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
                  <Chip
                    size="small"
                    label={person.active ? 'Active' : 'Inactive'}
                    color={person.active ? 'success' : 'default'}
                    variant="outlined"
                  />
                </TableCell>
                <TableCell align="right">
                  <PersonActionsMenu
                    person={person}
                    onChoose={(action) =>
                      setDialog(
                        action === 'edit'
                          ? { title: `Edit ${fullName(person.firstName, person.lastName)}`, body: 'This will change their name and custom fields.' }
                          : {
                              title: `Deactivate ${fullName(person.firstName, person.lastName)}`,
                              body: 'This will end their current membership and stop them signing in, without deleting their history.',
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

      {dialog && (
        <NotBuiltYetDialog open title={dialog.title} onClose={() => setDialog(null)}>
          {dialog.body}
        </NotBuiltYetDialog>
      )}
    </Stack>
  )
}
