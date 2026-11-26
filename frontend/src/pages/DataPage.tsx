import {
  Box,
  Button,
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
import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import BarChartOutlined from '@mui/icons-material/BarChartOutlined'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useState } from 'react'

import { useApi } from '../api/ApiContext'
import { useReferenceData } from '../api/ReferenceDataContext'
import type { DataChart, Lc, Scope } from '../api/types'
import { useAuth } from '../auth/authContext'
import { availableDataScopes, widestScope } from '../auth/permissions'
import { EmptyChartState, EmptyDataTable } from '../components/EmptyState'
import { NotBuiltYetDialog } from '../components/NotBuiltYetDialog'
import { OptionToggleGroup } from '../components/OptionToggleGroup'
import { SCOPE_LABELS } from '../lib/labels'

/** What the "next level up" is called in the summary table for a given scope. */
const GROUP_LABEL: Record<Scope, string> = { own: 'You', team: 'Member', function: 'Team', lc: 'Function', all: 'LC' }
const ALL_LCS = 'all'

/**
 * Data (spec §2A.7, §6): summaries and graphs, with a custom date range and a
 * data-analytics report generator SEPARATE from the official NAMs / SONA / MTR
 * reports (§7).
 */
export function DataPage() {
  const api = useApi()
  const { me } = useAuth()
  const { reference } = useReferenceData()
  const [scope, setScope] = useState<Scope>('team')
  const [lcId, setLcId] = useState(ALL_LCS)
  const [startDate, setStartDate] = useState<Dayjs | null>(dayjs().subtract(30, 'day'))
  const [endDate, setEndDate] = useState<Dayjs | null>(dayjs())
  const [reportOpen, setReportOpen] = useState(false)
  const [chart, setChart] = useState<DataChart | null>(null)

  // Derived from me.permissions — safe to compute before the early-return because
  // `availableDataScopes` / `widestScope` accept an empty array when me is null.
  const permissions = me?.permissions ?? []
  const scopeOptions = availableDataScopes(permissions)
  // The route guard requires at least 'team' scope to reach this page, so scopeOptions
  // is never empty here in practice; `?? 'team'` only satisfies the array-index type.
  const activeScope: Exclude<Scope, 'own'> = (
    scopeOptions.includes(scope) ? scope : (scopeOptions[0] ?? 'team')
  ) as Exclude<Scope, 'own'>
  // MC-wide viewers may narrow an LC-level summary to one LC (spec §12 #15 is still open
  // on who else may do this).
  const canPickLc = widestScope(permissions, 'analytics_report', 'view') === 'all'
  const showLcPicker = canPickLc && activeScope === 'lc' && reference

  useEffect(() => {
    // Guard: no call without a signed-in user and a valid date range.
    if (!me || !startDate || !endDate) return
    let cancelled = false
    api
      .getDataChart({
        scope: activeScope,
        startDate: startDate.format('YYYY-MM-DD'),
        endDate: endDate.format('YYYY-MM-DD'),
        lcId: lcId !== ALL_LCS ? lcId : null,
      })
      .then(
        (result) => {
          if (!cancelled) setChart(result)
        },
        () => {
          if (!cancelled) setChart(null)
        },
      )
    return () => {
      cancelled = true
    }
  }, [api, me, activeScope, startDate, endDate, lcId])

  if (!me) return null

  const summaryLabel = GROUP_LABEL[activeScope]

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h1" component="h1">
          Data
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 0.5, maxWidth: '65ch' }}>
          Summaries and graphs for your LC, function or team, over any date range.
        </Typography>
      </Box>

      <Box>
        <Button variant="outlined" startIcon={<BarChartOutlined />} onClick={() => setReportOpen(true)}>
          Build a report
        </Button>
      </Box>
      <NotBuiltYetDialog open={reportOpen} title="Build a report" onClose={() => setReportOpen(false)}>
        This will let you build your own graphs from data within your scope. It is separate from the official NAMs,
        SONA and MTR reports.
      </NotBuiltYetDialog>

      <Paper variant="outlined" sx={{ p: 3 }} component="section" aria-labelledby="data-filters-title">
        <Typography id="data-filters-title" variant="h2" component="h2" sx={{ mb: 2 }}>
          Filters
        </Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} sx={{ gap: 2, flexWrap: 'wrap', alignItems: { sm: 'center' } }}>
          <OptionToggleGroup
            value={activeScope}
            options={scopeOptions.map((s) => ({ value: s, label: SCOPE_LABELS[s] }))}
            onChange={setScope}
            ariaLabel="Summary level"
          />
          {showLcPicker && (
            <TextField select label="LC" value={lcId} onChange={(e) => setLcId(e.target.value)} sx={{ minWidth: 180 }}>
              <MenuItem value={ALL_LCS}>All LCs</MenuItem>
              {reference!.lcs.filter((lc: Lc) => lc.type === 'lc').map((lc) => (
                <MenuItem key={lc.id} value={lc.id}>
                  {lc.name}
                </MenuItem>
              ))}
            </TextField>
          )}
          <DatePicker label="Start date" format="DD/MM/YYYY" value={startDate} onChange={setStartDate} maxDate={endDate ?? undefined} />
          <DatePicker label="End date" format="DD/MM/YYYY" value={endDate} onChange={setEndDate} minDate={startDate ?? undefined} />
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 3 }} component="section" aria-labelledby="data-summary-title">
        <Typography id="data-summary-title" variant="h2" component="h2" sx={{ mb: 2 }}>
          Summary{chart?.kpi ? `: ${chart.kpi.label}${chart.kpi.unit ? ` (${chart.kpi.unit})` : ''}` : ''}
        </Typography>
        {chart && chart.summaryRows.length > 0 ? (
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small" aria-label="Summary">
              <TableHead>
                <TableRow>
                  <TableCell>{summaryLabel}</TableCell>
                  <TableCell align="right">Value</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {chart.summaryRows.map((row) => (
                  <TableRow key={row.label}>
                    <TableCell>{row.label}</TableCell>
                    <TableCell align="right">{row.value}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        ) : (
          <EmptyDataTable label="Summary" columns={[summaryLabel, 'Value']} />
        )}
        <Typography color="text.secondary" sx={{ mt: 1, maxWidth: '65ch' }}>
          Rolled up by {summaryLabel.toLowerCase()}, computed from records at request time — never a stored total
          (spec §6).
        </Typography>
      </Paper>

      <Paper variant="outlined" sx={{ p: 3 }} component="section" aria-labelledby="data-graph-title">
        <Typography id="data-graph-title" variant="h2" component="h2">
          Graph
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 0.5 }}>
          {SCOPE_LABELS[activeScope]}, over the chosen date range.
        </Typography>
        {(!chart || chart.points.length === 0) && <EmptyChartState />}
      </Paper>
    </Stack>
  )
}
