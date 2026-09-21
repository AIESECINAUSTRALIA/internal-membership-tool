import { Paper, Stack, Typography } from '@mui/material'
import { useEffect, useState } from 'react'

import { useApi } from '../api/ApiContext'
import type { HomeChart } from '../api/types'
import { useAuth } from '../auth/authContext'

/**
 * A homepage block: self-contained so a later version can let people arrange or swap
 * blocks (customisation is V2, spec §2A.4). Build no customisation now.
 */
function ChartBlock({ chart }: { chart: HomeChart | null }) {
  return (
    <Paper variant="outlined" sx={{ p: 3 }} component="section" aria-labelledby="home-chart-title">
      <Typography id="home-chart-title" variant="h2" component="h2">
        {chart ? chart.title : 'Monthly activity'}
      </Typography>
      <Typography color="text.secondary" sx={{ mt: 0.5 }}>
        {chart?.scope === 'team' && 'Your team, month by month.'}
        {chart?.scope === 'function' && 'Your function in your LC, month by month.'}
        {chart?.scope === 'all' && 'All LCs, month by month.'}
      </Typography>
      {/* No KPI catalog yet (spec §4.3 TODO), so there are no points to plot. */}
      {chart && chart.points.length === 0 && (
        <Typography variant="h3" component="p" sx={{ mt: 4, mb: 2 }}>
          No data exists
        </Typography>
      )}
    </Paper>
  )
}

/**
 * Homepage (spec §2A.4): one default layout for everyone. The chart shown depends on
 * the person's position: team for Member and Team Leader, function for LCVP and LCP,
 * all of Australia for MC (the MC choice is an assumption, see spec §12 #12).
 */
export function HomePage() {
  const api = useApi()
  const { me } = useAuth()
  const [chart, setChart] = useState<HomeChart | null>(null)

  useEffect(() => {
    let cancelled = false
    api.getHomeChart().then((result) => {
      if (!cancelled) setChart(result)
    })
    return () => {
      cancelled = true
    }
  }, [api])

  return (
    <Stack spacing={3}>
      <Typography variant="h1" component="h1">
        Home
      </Typography>
      <Typography>Welcome back, {me?.person.firstName}.</Typography>
      <ChartBlock chart={chart} />
    </Stack>
  )
}
