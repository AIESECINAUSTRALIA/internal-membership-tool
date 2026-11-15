import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useState, type FormEvent, type ReactNode } from 'react'

import { useApi } from '../api/ApiContext'
import type { AdminFunctionRow, AdminPositionRow } from '../api/types'

interface DialogProps {
  onClose: () => void
  onDone: () => void
}

/**
 * Shared dialog frame used by every position/function dialog: title, form body,
 * Cancel/submit buttons, and an error banner. `submit` returns an error message or null.
 */
function DialogFrame({
  title,
  submitLabel,
  canSubmit,
  submit,
  onClose,
  onDone,
  children,
}: DialogProps & {
  title: string
  submitLabel: string
  canSubmit: boolean
  submit: () => Promise<string | null>
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
    onDone()
    onClose()
  }

  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
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

// ---------------------------------------------------------------------------
// Position dialogs
// ---------------------------------------------------------------------------

export function AddPositionDialog(props: DialogProps) {
  const api = useApi()
  const [label, setLabel] = useState('')
  const [level, setLevel] = useState<'lc' | 'mc' | ''>('')
  const [rank, setRank] = useState('')
  const [canAddSameRank, setCanAddSameRank] = useState(false)

  const submit = async () => {
    const result = await api.createPosition({
      label,
      level: level || null,
      rank: rank ? parseInt(rank, 10) : null,
      canAddSameRank,
    })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <DialogFrame {...props} title="Add position" submitLabel="Add position" canSubmit={label.trim() !== ''} submit={submit}>
      <TextField required autoFocus label="Name" value={label} onChange={(e) => setLabel(e.target.value)} />
      <TextField select label="Level" value={level} onChange={(e) => setLevel(e.target.value as 'lc' | 'mc' | '')}>
        <MenuItem value="">Not set</MenuItem>
        <MenuItem value="lc">LC</MenuItem>
        <MenuItem value="mc">MC</MenuItem>
      </TextField>
      <TextField
        label="Rank"
        type="number"
        value={rank}
        onChange={(e) => setRank(e.target.value)}
        helperText="Higher number = more senior (§2). Leave blank if not yet decided."
        inputProps={{ min: 1 }}
      />
      <FormControlLabel
        control={<Checkbox checked={canAddSameRank} onChange={(e) => setCanAddSameRank(e.target.checked)} />}
        label="Can add another holder of the same position (president exception, §3.4)"
      />
    </DialogFrame>
  )
}

export function RenamePositionDialog({ position, ...props }: DialogProps & { position: AdminPositionRow }) {
  const api = useApi()
  const [label, setLabel] = useState(position.label)

  const submit = async () => {
    const result = await api.updatePosition(position.id, { label })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <DialogFrame
      {...props}
      title={`Rename "${position.label}"`}
      submitLabel="Rename"
      canSubmit={label.trim() !== '' && label.trim() !== position.label}
      submit={submit}
    >
      <TextField required autoFocus label="Name" value={label} onChange={(e) => setLabel(e.target.value)} />
      <Typography variant="body2" color="text.secondary">
        The new name shows everywhere. The key code and all membership history are unaffected.
      </Typography>
    </DialogFrame>
  )
}

export function EditPositionDetailsDialog({ position, ...props }: DialogProps & { position: AdminPositionRow }) {
  const api = useApi()
  const [level, setLevel] = useState<string>(position.level ?? '')
  const [rank, setRank] = useState(position.rank !== null ? String(position.rank) : '')
  const [canAddSameRank, setCanAddSameRank] = useState(position.canAddSameRank)

  const submit = async () => {
    const result = await api.updatePosition(position.id, {
      level: (level as 'lc' | 'mc') || null,
      rank: rank ? parseInt(rank, 10) : null,
      canAddSameRank,
    })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <DialogFrame {...props} title={`Edit details — ${position.label}`} submitLabel="Save" canSubmit submit={submit}>
      <TextField select label="Level" value={level} onChange={(e) => setLevel(e.target.value)}>
        <MenuItem value="">Not set</MenuItem>
        <MenuItem value="lc">LC</MenuItem>
        <MenuItem value="mc">MC</MenuItem>
      </TextField>
      <TextField
        label="Rank"
        type="number"
        value={rank}
        onChange={(e) => setRank(e.target.value)}
        helperText="Higher number = more senior (§2)."
        inputProps={{ min: 1 }}
      />
      <FormControlLabel
        control={<Checkbox checked={canAddSameRank} onChange={(e) => setCanAddSameRank(e.target.checked)} />}
        label="Can add another holder of the same position (president exception, §3.4)"
      />
    </DialogFrame>
  )
}

export function SetPositionActiveDialog({
  position,
  makeActive,
  ...props
}: DialogProps & { position: AdminPositionRow; makeActive: boolean }) {
  const api = useApi()

  const submit = async () => {
    const result = await api.updatePosition(position.id, { active: makeActive })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <DialogFrame
      {...props}
      title={makeActive ? `Reactivate "${position.label}"` : `Deactivate "${position.label}"`}
      submitLabel={makeActive ? 'Mark active' : 'Deactivate'}
      canSubmit
      submit={submit}
    >
      <Typography>
        {makeActive
          ? 'This position will be offered again when adding members.'
          : 'This position will no longer be offered when adding members. All existing memberships with this position are unaffected.'}
      </Typography>
    </DialogFrame>
  )
}

// ---------------------------------------------------------------------------
// Function dialogs
// ---------------------------------------------------------------------------

export function AddFunctionDialog(props: DialogProps) {
  const api = useApi()
  const [label, setLabel] = useState('')

  const submit = async () => {
    const result = await api.createFunction({ label })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <DialogFrame {...props} title="Add function" submitLabel="Add function" canSubmit={label.trim() !== ''} submit={submit}>
      <TextField required autoFocus label="Name" value={label} onChange={(e) => setLabel(e.target.value)} />
      <Typography variant="body2" color="text.secondary">
        A unique key is generated from the name. The function can be renamed later.
      </Typography>
    </DialogFrame>
  )
}

export function RenameFunctionDialog({ func, ...props }: DialogProps & { func: AdminFunctionRow }) {
  const api = useApi()
  const [label, setLabel] = useState(func.label)

  const submit = async () => {
    const result = await api.updateFunction(func.id, { label })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <DialogFrame
      {...props}
      title={`Rename "${func.label}"`}
      submitLabel="Rename"
      canSubmit={label.trim() !== '' && label.trim() !== func.label}
      submit={submit}
    >
      <TextField required autoFocus label="Name" value={label} onChange={(e) => setLabel(e.target.value)} />
      <Typography variant="body2" color="text.secondary">
        The new name shows everywhere. The key code and all membership history are unaffected.
      </Typography>
    </DialogFrame>
  )
}

export function SetFunctionActiveDialog({
  func,
  makeActive,
  ...props
}: DialogProps & { func: AdminFunctionRow; makeActive: boolean }) {
  const api = useApi()

  const submit = async () => {
    const result = await api.updateFunction(func.id, { active: makeActive })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <DialogFrame
      {...props}
      title={makeActive ? `Reactivate "${func.label}"` : `Deactivate "${func.label}"`}
      submitLabel={makeActive ? 'Mark active' : 'Deactivate'}
      canSubmit
      submit={submit}
    >
      <Typography>
        {makeActive
          ? 'This function will be offered again when adding members.'
          : 'This function will no longer be offered when adding members. All existing memberships with this function are unaffected.'}
      </Typography>
    </DialogFrame>
  )
}
