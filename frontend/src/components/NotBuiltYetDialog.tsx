import { Button, Dialog, DialogActions, DialogContent, DialogTitle, Typography } from '@mui/material'

/**
 * What an unbuilt action opens instead of doing anything (e.g. Settings' "Add
 * function", Data's "Build a report"). Says what the button will do, so nobody
 * wonders whether it is broken. Replace the call site with the real action when the
 * feature is built; this component can stay for the next one.
 */
export function NotBuiltYetDialog({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean
  title: string
  /** One or two sentences: what this action will do, once it exists. */
  children: string
  onClose: () => void
}) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <Typography color="text.secondary">Not built yet. {children}</Typography>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button variant="contained" onClick={onClose} color="primary" autoFocus>
          Close
        </Button>
      </DialogActions>
    </Dialog>
  )
}
