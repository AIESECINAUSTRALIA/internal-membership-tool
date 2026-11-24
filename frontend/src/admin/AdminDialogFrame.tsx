import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack } from '@mui/material'
import { useState, type FormEvent, type ReactNode } from 'react'

/** What every Admin console dialog needs from the page that opens it. */
export interface AdminDialogProps {
  onClose: () => void
  /** Called after the change succeeded, so the page can reload its table. */
  onDone: () => void
}

/**
 * The shared frame of every Admin console dialog (LCs, Metrics & custom fields): title,
 * form body, Cancel/submit buttons, and an error banner for when the server rejects the
 * change. `submit` returns an error message to show, or null when it worked (the frame
 * then calls `onDone` and `onClose`).
 */
export function AdminDialogFrame({
  title,
  submitLabel,
  canSubmit,
  submit,
  keepOpenOnSuccess = false,
  maxWidth = 'xs',
  onClose,
  onDone,
  children,
}: AdminDialogProps & {
  title: string
  submitLabel: string
  canSubmit: boolean
  submit: () => Promise<string | null>
  /** The LC merge dialog stays open to show its result; the others close. */
  keepOpenOnSuccess?: boolean
  /** 'sm' for a dialog with a longer form. */
  maxWidth?: 'xs' | 'sm'
  children: ReactNode
}) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    const message = await submit()
    setBusy(false)
    if (message !== null) {
      setError(message)
      return
    }
    if (keepOpenOnSuccess) return
    onDone()
    onClose()
  }

  return (
    <Dialog open onClose={onClose} maxWidth={maxWidth} fullWidth>
      <form onSubmit={handleSubmit}>
        <DialogTitle>{title}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {error && <Alert severity="error">{error}</Alert>}
            {children}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={!canSubmit || busy}>
            {submitLabel}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  )
}
