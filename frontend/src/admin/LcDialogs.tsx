import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'

import { useApi } from '../api/ApiContext'
import type { Lc, MergeLcSummary, StateTimezone } from '../api/types'

/** What every LC dialog needs from the page. */
interface DialogProps {
  onClose: () => void
  /** Called after the change succeeded, so the page can reload its table. */
  onDone: () => void
}

/**
 * The shared frame of every LC dialog: title, form body, Cancel/submit buttons, and an
 * error banner for when the server rejects the change. `submit` returns an error message
 * to show, or null when it worked (the frame then calls `onDone` and `onClose`).
 */
function LcDialogFrame({
  title,
  submitLabel,
  canSubmit,
  submit,
  keepOpenOnSuccess = false,
  onClose,
  onDone,
  children,
}: DialogProps & {
  title: string
  submitLabel: string
  canSubmit: boolean
  submit: () => Promise<string | null>
  /** The merge dialog stays open to show its result; the others close. */
  keepOpenOnSuccess?: boolean
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

/** The state picker, fed by the state → timezone lookup so it never drifts from the server. */
function StateSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (state: string) => void
  options: StateTimezone[]
}) {
  return (
    <TextField select required label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((option) => (
        <MenuItem key={option.state} value={option.state}>
          {option.state} ({option.timezone})
        </MenuItem>
      ))}
    </TextField>
  )
}

/** Loads the state lookup once per dialog. */
function useStateTimezones(): StateTimezone[] {
  const api = useApi()
  const [options, setOptions] = useState<StateTimezone[]>([])
  useEffect(() => {
    let cancelled = false
    api.listStateTimezones().then((rows) => {
      if (!cancelled) setOptions(rows)
    })
    return () => {
      cancelled = true
    }
  }, [api])
  return options
}

export function AddLcDialog(props: DialogProps) {
  const api = useApi()
  const states = useStateTimezones()
  const [name, setName] = useState('')
  const [state, setState] = useState('')

  const submit = async () => {
    const result = await api.createLc({ name, state })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <LcDialogFrame {...props} title="Add LC" submitLabel="Add LC" canSubmit={name.trim() !== '' && state !== ''} submit={submit}>
      <TextField required autoFocus label="Name" value={name} onChange={(e) => setName(e.target.value)} />
      <StateSelect label="State" value={state} onChange={setState} options={states} />
    </LcDialogFrame>
  )
}

export function RenameLcDialog({ lc, ...props }: DialogProps & { lc: Lc }) {
  const api = useApi()
  const [name, setName] = useState(lc.name)

  const submit = async () => {
    const result = await api.updateLc(lc.id, { name })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <LcDialogFrame
      {...props}
      title={`Rename ${lc.name}`}
      submitLabel="Rename"
      canSubmit={name.trim() !== '' && name.trim() !== lc.name}
      submit={submit}
    >
      <TextField required autoFocus label="Name" value={name} onChange={(e) => setName(e.target.value)} />
      <Typography variant="body2" color="text.secondary">
        The new name shows everywhere. History is not changed.
      </Typography>
    </LcDialogFrame>
  )
}

export function SetLcStateDialog({ lc, ...props }: DialogProps & { lc: Lc }) {
  const api = useApi()
  const states = useStateTimezones()
  const [state, setState] = useState(lc.state ?? '')

  const submit = async () => {
    const result = await api.updateLc(lc.id, { state })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <LcDialogFrame
      {...props}
      title={`Set state for ${lc.name}`}
      submitLabel="Save state"
      canSubmit={state !== '' && state !== lc.state}
      submit={submit}
    >
      <StateSelect label="State" value={state} onChange={setState} options={states} />
      <Typography variant="body2" color="text.secondary">
        The state sets the timezone of everyone currently in this LC.
      </Typography>
    </LcDialogFrame>
  )
}

/** Mark inactive (the soft delete) or bring an inactive LC back. */
export function SetLcActiveDialog({ lc, makeActive, ...props }: DialogProps & { lc: Lc; makeActive: boolean }) {
  const api = useApi()

  const submit = async () => {
    const result = await api.updateLc(lc.id, { active: makeActive })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <LcDialogFrame
      {...props}
      title={makeActive ? `Mark ${lc.name} active` : `Mark ${lc.name} inactive`}
      submitLabel={makeActive ? 'Mark active' : 'Mark inactive'}
      canSubmit
      submit={submit}
    >
      <Typography>
        {makeActive
          ? 'This LC will be offered again when someone is added.'
          : 'This LC will no longer be offered when someone is added. Its members, teams and history are kept, and you can mark it active again later.'}
      </Typography>
    </LcDialogFrame>
  )
}

/** What the admin sees after a merge: the counts, and the one thing that may surprise them. */
function MergeSummaryAlert({ summary }: { summary: MergeLcSummary }) {
  return (
    <Alert severity="success">
      {summary.membershipsMoved} members moved
      {summary.futureMembershipsRepointed > 0 && `, ${summary.futureMembershipsRepointed} future memberships re-pointed`}
      {summary.leadersNotCarried > 0 && `. ${summary.leadersNotCarried} team leaders were not carried over because the team already had one`}.
    </Alert>
  )
}

export function MergeLcDialog({ lc, targets, onClose, onDone }: DialogProps & { lc: Lc; targets: Lc[] }) {
  const api = useApi()
  const [targetId, setTargetId] = useState('')
  const [summary, setSummary] = useState<MergeLcSummary | null>(null)
  const target = targets.find((t) => t.id === targetId)

  const finish = () => {
    onDone()
    onClose()
  }

  if (summary) {
    return (
      <Dialog open onClose={finish} maxWidth="xs" fullWidth>
        <DialogTitle>Merge complete</DialogTitle>
        <DialogContent>
          <MergeSummaryAlert summary={summary} />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button variant="contained" autoFocus onClick={finish}>
            Close
          </Button>
        </DialogActions>
      </Dialog>
    )
  }

  const submit = async () => {
    const result = await api.mergeLc(lc.id, targetId)
    if (result.status === 'rejected') return result.message
    setSummary(result.summary)
    return null
  }

  return (
    <LcDialogFrame
      title={`Merge ${lc.name}`}
      submitLabel="Merge"
      canSubmit={targetId !== ''}
      submit={submit}
      keepOpenOnSuccess
      onClose={onClose}
      onDone={onDone}
    >
      <TextField select required autoFocus label="Merge into" value={targetId} onChange={(e) => setTargetId(e.target.value)}>
        {targets.map((option) => (
          <MenuItem key={option.id} value={option.id}>
            {option.name}
          </MenuItem>
        ))}
      </TextField>
      <Typography variant="body2" color="text.secondary">
        {target
          ? `Members of ${lc.name} will move to ${target.name} from today. Their past records and KPIs stay under ${lc.name}. ${lc.name} will be marked inactive.`
          : 'Choose the LC that will take over this LC’s current members and teams.'}
      </Typography>
    </LcDialogFrame>
  )
}
