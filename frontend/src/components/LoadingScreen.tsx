import { Box, CircularProgress } from '@mui/material'

export function LoadingScreen() {
  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
      <CircularProgress aria-label="Loading" color="secondary" />
    </Box>
  )
}
