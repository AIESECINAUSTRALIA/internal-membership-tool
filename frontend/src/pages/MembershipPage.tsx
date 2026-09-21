import { Alert, Box, Button, Chip, InputAdornment, MenuItem, Snackbar, Stack, TextField, Typography } from '@mui/material'
import { DataGrid, type GridColDef, type GridPaginationModel, type GridSortModel } from '@mui/x-data-grid'
import PersonAddAlt1Outlined from '@mui/icons-material/PersonAddAlt1Outlined'
import SearchIcon from '@mui/icons-material/Search'
import { useEffect, useMemo, useState } from 'react'

import { useApi } from '../api/ApiContext'
import type { MemberQuery, MemberSortField, MemberSummaryRow, Page, ReferenceData } from '../api/types'
import { useAuth } from '../auth/authContext'
import { addableLcs, rowActions, widestScope } from '../auth/permissions'
import { AddMemberDialog } from '../features/membership/AddMemberDialog'
import { ManageMembershipDialog, type ManageKind } from '../features/membership/ManageMembershipDialog'
import { MemberActionsMenu } from '../features/membership/MemberActionsMenu'
import { roleLabel } from '../lib/labels'
import { useDebounced } from '../lib/useDebounced'

const ALL_LCS = 'all'

/**
 * Membership summary (spec §2A.5): who is in the LC and what they do. Shows ONLY first
 * name, last name, position-function pairs and LC. Email is never here, and the API
 * never sends it. Search, sort and pagination all run through the API ("in the query").
 */
export function MembershipPage() {
  const api = useApi()
  const { me, actor } = useAuth()

  const [reference, setReference] = useState<ReferenceData | null>(null)
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)
  const [lcId, setLcId] = useState(ALL_LCS)
  const [paginationModel, setPaginationModel] = useState<GridPaginationModel>({ page: 0, pageSize: 10 })
  const [sortModel, setSortModel] = useState<GridSortModel>([{ field: 'lastName', sort: 'asc' }])
  const [reloadCount, setReloadCount] = useState(0)

  const query: MemberQuery = useMemo(
    () => ({
      search: debouncedSearch,
      sort: sortModel[0]?.sort ? { field: sortModel[0].field as MemberSortField, direction: sortModel[0].sort } : null,
      page: paginationModel.page,
      pageSize: paginationModel.pageSize,
      lcId: lcId === ALL_LCS ? null : lcId,
    }),
    [debouncedSearch, sortModel, paginationModel, lcId],
  )
  // "Loading" is derived: the last answer belongs to a different question than the current one.
  const queryKey = JSON.stringify([query, reloadCount])
  const [result, setResult] = useState<{ key: string; page: Page<MemberSummaryRow> } | null>(null)
  const loading = result?.key !== queryKey

  const [adding, setAdding] = useState(false)
  const [managing, setManaging] = useState<{ kind: ManageKind; row: MemberSummaryRow } | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api.getReferenceData().then((data) => {
      if (!cancelled) setReference(data)
    })
    return () => {
      cancelled = true
    }
  }, [api])

  useEffect(() => {
    let cancelled = false
    api.listMembers(query).then((page) => {
      if (!cancelled) setResult({ key: queryKey, page })
    })
    return () => {
      cancelled = true
    }
  }, [api, query, queryKey])

  if (!me || !actor) return null

  const canAdd = reference ? addableLcs(actor, me.permissions, reference.lcs).length > 0 : false
  const canPickLc = widestScope(me.permissions, 'membership', 'view') === 'all' // MC users (§2A.5)
  const actionsFor = (row: MemberSummaryRow) => rowActions(actor, me.permissions, row)
  const showActions = (result?.page.rows ?? []).some((row) => {
    const a = actionsFor(row)
    return a.extendRoleIds.length > 0 || a.moveRoleIds.length > 0
  })

  const columns: GridColDef<MemberSummaryRow>[] = [
    { field: 'firstName', headerName: 'First name', flex: 1, minWidth: 140 },
    { field: 'lastName', headerName: 'Last name', flex: 1, minWidth: 140 },
    {
      field: 'position',
      headerName: 'Position and function',
      flex: 2,
      minWidth: 280,
      renderCell: ({ row }) => (
        <Stack direction="row" sx={{ py: 1, gap: 0.75, flexWrap: 'wrap' }}>
          {row.roles.map((role) => (
            <Chip key={role.membershipId} variant="outlined" label={roleLabel(role.position, role.function)} />
          ))}
        </Stack>
      ),
    },
    { field: 'lc', headerName: 'LC', width: 110, valueGetter: (_value, row) => row.lc.name },
    ...(showActions
      ? [
          {
            field: 'actions',
            headerName: 'Actions',
            width: 100,
            sortable: false,
            renderCell: ({ row }) => (
              <MemberActionsMenu row={row} actions={actionsFor(row)} onChoose={(kind) => setManaging({ kind, row })} />
            ),
          } satisfies GridColDef<MemberSummaryRow>,
        ]
      : []),
  ]

  return (
    <Stack spacing={3}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 2, flexWrap: 'wrap' }}>
        <div>
          <Typography variant="h1" component="h1">
            Membership
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5 }}>
            Current members and the positions they hold.
          </Typography>
        </div>
        {canAdd && (
          <Button variant="contained" startIcon={<PersonAddAlt1Outlined />} onClick={() => setAdding(true)}>
            Add member
          </Button>
        )}
      </Stack>

      <Stack direction={{ xs: 'column', sm: 'row' }} sx={{ gap: 2 }}>
        <TextField
          label="Search members"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPaginationModel((m) => ({ ...m, page: 0 }))
          }}
          slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment> } }}
          sx={{ flex: 1, maxWidth: 420 }}
        />
        {canPickLc && reference && (
          <TextField
            select
            label="LC"
            value={lcId}
            onChange={(e) => {
              setLcId(e.target.value)
              setPaginationModel((m) => ({ ...m, page: 0 }))
            }}
            sx={{ minWidth: 200 }}
          >
            <MenuItem value={ALL_LCS}>All LCs</MenuItem>
            {reference.lcs.map((lc) => (
              <MenuItem key={lc.id} value={lc.id}>
                {lc.name}
              </MenuItem>
            ))}
          </TextField>
        )}
      </Stack>

      <Box>
        <DataGrid
          aria-label="Members"
          rows={result?.page.rows ?? []}
          rowCount={result?.page.total ?? 0}
          columns={columns}
          getRowId={(row) => row.personId}
          loading={loading}
          paginationMode="server"
          sortingMode="server"
          paginationModel={paginationModel}
          onPaginationModelChange={setPaginationModel}
          sortModel={sortModel}
          onSortModelChange={setSortModel}
          pageSizeOptions={[10, 25, 50]}
          getRowHeight={() => 'auto'}
          autoHeight
          disableColumnFilter
          disableColumnMenu
          disableColumnSelector
          localeText={{ noRowsLabel: 'No data exists' }}
        />
      </Box>

      {adding && reference && (
        <AddMemberDialog
          open
          reference={reference}
          actor={actor}
          permissions={me.permissions}
          onClose={() => setAdding(false)}
          onAdded={() => {
            setAdding(false)
            setToast('Member added')
            setReloadCount((n) => n + 1)
          }}
        />
      )}
      {managing && (
        <ManageMembershipDialog
          kind={managing.kind}
          row={managing.row}
          eligibleRoleIds={
            managing.kind === 'extend' ? actionsFor(managing.row).extendRoleIds : actionsFor(managing.row).moveRoleIds
          }
          onClose={() => setManaging(null)}
          onDone={(message) => {
            setManaging(null)
            setToast(message)
            setReloadCount((n) => n + 1)
          }}
        />
      )}
      <Snackbar open={toast !== null} autoHideDuration={4000} onClose={() => setToast(null)}>
        <Alert severity="success" onClose={() => setToast(null)}>
          {toast}
        </Alert>
      </Snackbar>
    </Stack>
  )
}
