import { Box, Button, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material'
import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import BarChartOutlined from '@mui/icons-material/BarChartOutlined'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'

import { useReferenceData } from '../api/ReferenceDataContext'
import type { Lc, Scope } from '../api/types'
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
 * reports (§7). The KPI catalog is still a spec TODO (§4.3), so the summary and graph
 * are shown in their intended shape but empty ("No data exists", spec §2A).
 */
export function DataPage() {
  const { me } = useAuth()
  const { reference } = useReferenceData()
  const [scope, setScope] = useState<Scope>('team')
  const [lcId, setLcId] = useState(ALL_LCS)
  const [startDate, setStartDate] = useState<Dayjs | null>(dayjs().subtract(30, 'day'))
  const [endDate, setEndDate] = useState<Dayjs | null>(dayjs())
  const [reportOpen, setReportOpen] = useState(false)

  if (!me) return null

  const scopeOptions = availableDataScopes(me.permissions)
  // The route guard requires at least 'team' scope to reach this page, so scopeOptions
  // is never empty here in practice; `?? 'team'` only satisfies the array-index type.
  const activeScope = scopeOptions.includes(scope) ? scope : (scopeOptions[0] ?? 'team')
  // MC-wide viewers may narrow an LC-level summary to one LC (spec §12 #15 is still open
  // on who else may do this).
  const canPickLc = widestScope(me.permissions, 'analytics_report', 'view') === 'all'
  const showLcPicker = canPickLc && activeScope === 'lc' && reference

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
          Summary
        </Typography>
        <EmptyDataTable label="Summary" columns={[GROUP_LABEL[activeScope], 'Value']} />
        <Typography color="text.secondary" sx={{ mt: 1, maxWidth: '65ch' }}>
          Rolled up by {GROUP_LABEL[activeScope].toLowerCase()}, computed from records at request time — never a stored
          total (spec §6). Waiting on the KPI catalog (spec §4.3).
        </Typography>
      </Paper>

      <Paper variant="outlined" sx={{ p: 3 }} component="section" aria-labelledby="data-graph-title">
        <Typography id="data-graph-title" variant="h2" component="h2">
          Graph
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 0.5 }}>
          {SCOPE_LABELS[activeScope]}, over the chosen date range.
        </Typography>
        <EmptyChartState />
      </Paper>
    </Stack>
  )
}
