import {
  Avatar,
  Box,
  Chip,
  InputAdornment,
  List,
  ListItemAvatar,
  ListItemButton,
  ListItemText,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import { useEffect, useMemo, useState } from 'react'

import { useApi } from '../api/ApiContext'
import type { FunctionRef, MemberSummaryRow } from '../api/types'
import { useAuth } from '../auth/authContext'
import { canTrackOthers, distinctFunctions, trackableRoleIds } from '../auth/permissions'
import { EmptyDataTable } from '../components/EmptyState'
import { OptionToggleGroup } from '../components/OptionToggleGroup'
import { fullName, roleLabel, shortLabel } from '../lib/labels'
import { useDebounced } from '../lib/useDebounced'

/** The shape the real KPI table will have (period, value, who recorded it), shown empty
 * until the KPI catalog exists (spec §4.3 TODO). */
const KPI_TABLE_COLUMNS = ['Period', 'Value', 'Recorded by']

function TrackingTable({ label, note }: { label: string; note: string }) {
  return (
    <>
      <EmptyDataTable label={label} columns={KPI_TABLE_COLUMNS} />
      <Typography color="text.secondary" sx={{ mt: 1, maxWidth: '65ch' }}>
        {note}
      </Typography>
    </>
  )
}

/**
 * Track someone (§2A.6, §3.4): search within scope, pick a person, then pick which of
 * their trackable position/function pairs to view. Reuses `listMembers` for the search
 * (already scoped to the viewer's LC/team), then narrows to rows the actor may track —
 * an approximation until a `kpi_record`-scoped search exists on the real backend.
 */
function TrackSomeone() {
  const api = useApi()
  const { me, actor } = useAuth()
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)
  const [candidates, setCandidates] = useState<MemberSummaryRow[]>([])
  const [selected, setSelected] = useState<MemberSummaryRow | null>(null)
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null)

  useEffect(() => {
    if (!actor) return
    let cancelled = false
    api.listMembers({ search: debouncedSearch, sort: null, page: 0, pageSize: 8, lcId: null }).then((page) => {
      if (cancelled) return
      const trackable = page.rows.filter((row) => trackableRoleIds(actor, me!.permissions, row).length > 0)
      setCandidates(trackable)
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `actor`/`me` change together on sign-in only
  }, [api, debouncedSearch])

  if (!me || !actor) return null

  const trackableRoles = (row: MemberSummaryRow) => {
    const ids = new Set(trackableRoleIds(actor, me.permissions, row))
    return row.roles.filter((role) => ids.has(role.membershipId))
  }

  if (selected) {
    const roles = trackableRoles(selected)
    const activeRole = roles.find((r) => r.membershipId === selectedRoleId) ?? roles[0]
    return (
      <Stack spacing={2}>
        <Stack direction="row" sx={{ alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
          <Typography variant="h3" component="p">
            {fullName(selected.firstName, selected.lastName)}
          </Typography>
          <Chip
            label="Change person"
            variant="outlined"
            onClick={() => {
              setSelected(null)
              setSelectedRoleId(null)
            }}
          />
        </Stack>
        {roles.length > 1 && (
          <OptionToggleGroup
            value={activeRole?.function?.key ?? null}
            options={roles
              .map((r) => r.function)
              .filter((f): f is FunctionRef => f !== null)
              .map((fn) => ({ value: fn.key, label: shortLabel(fn.label), ariaLabel: fn.label }))}
            onChange={(key) => setSelectedRoleId(roles.find((r) => r.function?.key === key)?.membershipId ?? null)}
            ariaLabel={`${fullName(selected.firstName, selected.lastName)}'s functions`}
          />
        )}
        <TrackingTable
          label={`${fullName(selected.firstName, selected.lastName)}'s numbers`}
          note={
            activeRole
              ? `${roleLabel(activeRole.position, activeRole.function)}. Entries you record here will be attributed to you as the recorder.`
              : 'Choose a function above.'
          }
        />
      </Stack>
    )
  }

  return (
    <Stack spacing={1.5}>
      <TextField
        label="Search people you can track"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment> } }}
        sx={{ maxWidth: 420 }}
      />
      {debouncedSearch && candidates.length === 0 && (
        <Typography color="text.secondary">No data exists</Typography>
      )}
      {candidates.length > 0 && (
        <List aria-label="Search results" sx={{ maxWidth: 480, bgcolor: 'background.paper' }}>
          {candidates.map((row) => {
            const roles = trackableRoles(row)
            return (
              <ListItemButton
                key={row.personId}
                onClick={() => {
                  setSelected(row)
                  setSelectedRoleId(roles[0]?.membershipId ?? null)
                }}
              >
                <ListItemAvatar>
                  <Avatar>{(row.firstName[0] ?? '?').toUpperCase()}</Avatar>
                </ListItemAvatar>
                <ListItemText
                  primary={fullName(row.firstName, row.lastName)}
                  secondary={roles.map((r) => roleLabel(r.position, r.function)).join(', ')}
                />
              </ListItemButton>
            )
          })}
        </List>
      )}
    </Stack>
  )
}

/**
 * Tracking (spec §2A.6): enter and view KPI numbers. What is tracked depends on
 * function (the `attribute` catalog, filtered by function — spec §4.3), which is still
 * a spec TODO, so the tables below are shown in their intended shape but empty.
 */
export function TrackingPage() {
  const { me, actor } = useAuth()
  const myFunctions = useMemo(() => (actor ? distinctFunctions(actor) : []), [actor])
  const [selectedFunctionKey, setSelectedFunctionKey] = useState<string | null>(myFunctions[0]?.key ?? null)

  if (!me || !actor) return null
  const activeFunction = myFunctions.find((f) => f.key === selectedFunctionKey) ?? myFunctions[0] ?? null
  const showTrackSomeone = canTrackOthers(me.permissions)

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h1" component="h1">
          Tracking
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 0.5, maxWidth: '65ch' }}>
          Enter and view KPI numbers. What you track depends on your function.
        </Typography>
      </Box>

      <Paper variant="outlined" component="section" aria-labelledby="my-tracking-title" sx={{ p: 3 }}>
        <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2, mb: 2 }}>
          <Typography id="my-tracking-title" variant="h2" component="h2">
            My tracking
          </Typography>
          <OptionToggleGroup
            value={selectedFunctionKey}
            options={myFunctions.map((fn) => ({ value: fn.key, label: shortLabel(fn.label), ariaLabel: fn.label }))}
            onChange={setSelectedFunctionKey}
            ariaLabel="Your functions"
          />
        </Stack>
        <TrackingTable
          label="My numbers"
          note={
            activeFunction
              ? `Your numbers for ${shortLabel(activeFunction.label)}. Entries you record here will be attributed to you.`
              : 'You have no active function to track yet.'
          }
        />
      </Paper>

      {showTrackSomeone && (
        <Paper variant="outlined" component="section" aria-labelledby="track-someone-title" sx={{ p: 3 }}>
          <Typography id="track-someone-title" variant="h2" component="h2" sx={{ mb: 2 }}>
            Track someone
          </Typography>
          <Typography color="text.secondary" sx={{ mb: 2, maxWidth: '65ch' }}>
            Pick a person below you to enter or view their numbers.
          </Typography>
          <TrackSomeone />
        </Paper>
      )}
    </Stack>
  )
}
