import { Box, Button, Paper, Stack, Typography } from '@mui/material'
import { Link as RouterLink } from 'react-router-dom'
import type { ReactNode } from 'react'

/**
 * Stand-in for a page that is planned but not built yet (spec §2A). It says what the page
 * will do, in plain words, so nobody meets a blank screen. Replace the page's body, not
 * this component, when the real feature lands.
 */
export function PlannedPage({
  title,
  intro,
  willDo,
  children,
}: {
  title: string
  /** One sentence: what this page is for. */
  intro: string
  /** What it will let people do. Short, active sentences. */
  willDo: string[]
  /** Extra blocks, e.g. a section only some positions may see. */
  children?: ReactNode
}) {
  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h1" component="h1">
          {title}
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 0.5, maxWidth: '65ch' }}>
          {intro}
        </Typography>
      </Box>
      <Paper variant="outlined" component="section" aria-labelledby="planned-title" sx={{ p: 3 }}>
        <Typography id="planned-title" variant="h2" component="h2">
          Not built yet
        </Typography>
        <Typography sx={{ mt: 1, maxWidth: '65ch' }}>This page will let you:</Typography>
        <Box component="ul" sx={{ mt: 1, mb: 3, pl: 3, maxWidth: '65ch', '& li + li': { mt: 0.5 } }}>
          {willDo.map((item) => (
            <li key={item}>
              <Typography component="span">{item}</Typography>
            </li>
          ))}
        </Box>
        <Button component={RouterLink} to="/" variant="outlined" color="primary">
          Go to Home
        </Button>
      </Paper>
      {children}
    </Stack>
  )
}
