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
import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'

import { useApi } from '../../api/ApiContext'
import type { Permission, ReferenceData } from '../../api/types'
import {
  actingMembershipCandidates,
  addableFunctions,
  addableLcs,
  addablePositions,
  addableTeams,
  fixedTeam,
  narrowToMembership,
  type Actor,
} from '../../auth/permissions'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { membershipLabel, teamOptionLabel } from '../../lib/labels'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const ISO = 'YYYY-MM-DD'

interface Props {
  open: boolean
  reference: ReferenceData
  actor: Actor
  permissions: Permission[]
  onClose: () => void
  onAdded: () => void
}

/**
 * Add member (spec §2A.5). The AIESEC email identifies the person. Choices are limited
 * by the hierarchy rule (§3.4) and the LC's level (§3.6): the form only OFFERS what the
 * server would accept. Steps the server can ask for after submit:
 *   1. "needs_name": nobody has this email yet, so ask for first and last name.
 *   2. "confirm_existing": the email exists, so confirm before attaching the membership.
 *      Any current membership in another LC then ends automatically (§5.1). The message
 *      deliberately does not name that LC.
 */
export function AddMemberDialog({ open, reference, actor, permissions, onClose, onAdded }: Props) {
  const api = useApi()
  const [email, setEmail] = useState('')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [membershipChoice, setMembershipChoice] = useState('')
  const [lcChoice, setLcChoice] = useState('')
  const [positionChoice, setPositionChoice] = useState('')
  const [functionChoice, setFunctionChoice] = useState('')
  const [teamChoice, setTeamChoice] = useState('')
  const [termId, setTermId] = useState('')
  const [start, setStart] = useState<Dayjs | null>(null)
  const [end, setEnd] = useState<Dayjs | null>(null)
  const [needsName, setNeedsName] = useState(false)
  const [confirmExisting, setConfirmExisting] = useState(false)
  const [submitted, setSubmitted] = useState(false) // show field errors only after a first try
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  // Everything offered is derived from who is acting. Nothing here is hardcoded per role.
  // The actor may hold more than one membership of the same acting position (e.g. Team
  // Leader of two teams) — the "Add as" picker below lets them choose which one, and
  // everything downstream is derived from that single, narrowed membership.
  const candidates = actingMembershipCandidates(actor)
  const chosenMembership = candidates.find((m) => m.id === membershipChoice) ?? candidates[0]
  const effectiveActor = chosenMembership ? narrowToMembership(actor, chosenMembership.id) : actor
  const lcOptions = addableLcs(effectiveActor, permissions, reference.lcs)
  const lcFixed = lcOptions.length === 1
  const lc = lcOptions.find((l) => l.id === lcChoice) ?? (lcFixed ? lcOptions[0] : undefined)
  const positionOptions = lc ? addablePositions(effectiveActor, permissions, reference.positions, lc) : []
  const position =
    positionOptions.find((p) => p.key === positionChoice) ??
    (positionOptions.length === 1 ? positionOptions[0] : undefined)
  const functionOptions = position ? addableFunctions(effectiveActor, permissions, reference.functions, position) : []
  const fn =
    functionOptions.find((f) => f.key === functionChoice) ??
    (functionOptions.length === 1 ? functionOptions[0] : undefined)
  const team = fixedTeam(effectiveActor, permissions)
  // A Team-Leader-scope adder is already fixed to their own team (above); anyone
  // broader gets a genuine choice, once a team-holding position and function are set.
  const showTeamPicker = !team && position?.holdsTeam === true && !!fn
  const teamOptions = showTeamPicker ? addableTeams(effectiveActor, permissions, reference.teams, lc!, fn!.key) : []
  const teamChosen = teamOptions.find((t) => t.id === teamChoice) ?? (teamOptions.length === 1 ? teamOptions[0] : undefined)

  const emailError = !EMAIL_PATTERN.test(email.trim()) ? 'Enter their AIESEC email address.' : ''
  const startError = !start?.isValid() ? 'Enter a start date.' : ''
  const endError = !end?.isValid()
    ? 'Enter an end date.'
    : start?.isValid() && end.isBefore(start, 'day')
      ? 'The end date must be on or after the start date.'
      : ''
  const nameError = needsName && (!firstName.trim() || !lastName.trim()) ? 'Enter their first and last name.' : ''
  const valid =
    !emailError && !startError && !endError && !nameError && lc && position && fn && (!showTeamPicker || teamChosen)

  const submit = async (confirmed: boolean) => {
    setSubmitted(true)
    if (!valid) return
    setBusy(true)
    setServerError(null)
    try {
      const result = await api.addMember({
        email: email.trim(),
        firstName: needsName ? firstName.trim() : undefined,
        lastName: needsName ? lastName.trim() : undefined,
        membershipId: chosenMembership?.id,
        lcId: lc.id,
        positionKey: position.key,
        functionKey: fn.key,
        teamId: team?.team.id ?? teamChosen?.id,
        startDate: start!.format(ISO),
        endDate: end!.format(ISO),
        termId: termId || undefined,
        confirmedExisting: confirmed,
      })
      setConfirmExisting(false)
      if (result.status === 'needs_name') setNeedsName(true)
      else if (result.status === 'confirm_existing') setConfirmExisting(true)
      else if (result.status === 'rejected') setServerError(result.message)
      else onAdded()
    } finally {
      setBusy(false)
    }
  }

  const handleTerm = (id: string) => {
    setTermId(id)
    const term = reference.terms.find((t) => t.id === id)
    if (term) {
      // Choosing a term pre-fills the dates (§2A.5). They stay editable.
      setStart(dayjs(term.startDate))
      setEnd(dayjs(term.endDate))
    }
  }

  return (
    <>
      <Dialog open={open && !confirmExisting} onClose={busy ? undefined : onClose} maxWidth="sm" fullWidth>
        <DialogTitle>Add member</DialogTitle>
        <DialogContent>
          <Stack spacing={2.5} sx={{ pt: 1 }} component="form" noValidate onSubmit={(e) => { e.preventDefault(); void submit(false) }} id="add-member-form">
            <TextField
              label="AIESEC email"
              type="email"
              required
              autoFocus
              value={email}
              onChange={(e) => { setEmail(e.target.value); setNeedsName(false) }}
              error={submitted && !!emailError}
              helperText={submitted && emailError ? emailError : 'Their AIESEC email identifies them. It is not shown on the Membership page.'}
              fullWidth
            />
            {needsName && (
              <>
                <Alert severity="info">No one has this email yet. Enter their name to add them.</Alert>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                  <TextField label="First name" required value={firstName} onChange={(e) => setFirstName(e.target.value)} error={submitted && !firstName.trim()} fullWidth />
                  <TextField label="Last name" required value={lastName} onChange={(e) => setLastName(e.target.value)} error={submitted && !lastName.trim()} fullWidth />
                </Stack>
              </>
            )}
            {candidates.length > 1 && (
              <TextField
                select
                label="Add as"
                value={chosenMembership?.id ?? ''}
                onChange={(e) => {
                  setMembershipChoice(e.target.value)
                  setLcChoice('')
                  setPositionChoice('')
                  setFunctionChoice('')
                  setTeamChoice('')
                }}
                helperText="You hold this role in more than one place — choose which one you're adding under."
                fullWidth
              >
                {candidates.map((m) => (
                  <MenuItem key={m.id} value={m.id}>{membershipLabel(m)}</MenuItem>
                ))}
              </TextField>
            )}
            {lcFixed ? (
              <TextField label="LC" value={lc?.name ?? ''} slotProps={{ input: { readOnly: true } }} helperText="Fixed to your LC." fullWidth />
            ) : (
              <TextField select label="LC" required value={lc?.id ?? ''} onChange={(e) => { setLcChoice(e.target.value); setPositionChoice(''); setFunctionChoice(''); setTeamChoice('') }} error={submitted && !lc} helperText={submitted && !lc ? 'Choose an LC.' : ' '} fullWidth>
                {lcOptions.map((l) => (
                  <MenuItem key={l.id} value={l.id}>{l.name}</MenuItem>
                ))}
              </TextField>
            )}
            {team && <TextField label="Team" value={team.team.name} slotProps={{ input: { readOnly: true } }} helperText="Fixed to your team." fullWidth />}
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField select label="Position" required value={position?.key ?? ''} onChange={(e) => { setPositionChoice(e.target.value); setFunctionChoice(''); setTeamChoice('') }} error={submitted && !position} helperText={submitted && !position ? 'Choose a position.' : ' '} disabled={!lc} fullWidth>
                {positionOptions.map((p) => (
                  <MenuItem key={p.key} value={p.key}>{p.label}</MenuItem>
                ))}
              </TextField>
              <TextField select label="Function" required value={fn?.key ?? ''} onChange={(e) => { setFunctionChoice(e.target.value); setTeamChoice('') }} error={submitted && !fn} helperText={submitted && !fn ? 'Choose a function.' : ' '} disabled={!position} fullWidth>
                {functionOptions.map((f) => (
                  <MenuItem key={f.key} value={f.key}>{f.label}</MenuItem>
                ))}
              </TextField>
            </Stack>
            {showTeamPicker && (
              <TextField
                select
                label="Team"
                required
                value={teamChosen?.id ?? ''}
                onChange={(e) => setTeamChoice(e.target.value)}
                error={submitted && !teamChosen}
                helperText={submitted && !teamChosen ? 'Choose a team.' : ' '}
                fullWidth
              >
                {teamOptions.map((t) => (
                  <MenuItem key={t.id} value={t.id}>{teamOptionLabel(t)}</MenuItem>
                ))}
              </TextField>
            )}
            <TextField select label="Term (fills in the dates)" value={termId} onChange={(e) => handleTerm(e.target.value)} fullWidth>
              <MenuItem value="">No term, enter dates</MenuItem>
              {reference.terms.map((t) => (
                <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>
              ))}
            </TextField>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <DatePicker label="Start date" format="DD/MM/YYYY" value={start} onChange={setStart} slotProps={{ textField: { required: true, fullWidth: true, error: submitted && !!startError, helperText: submitted ? startError : undefined } }} />
              <DatePicker label="End date" format="DD/MM/YYYY" value={end} onChange={setEnd} slotProps={{ textField: { required: true, fullWidth: true, error: submitted && !!endError, helperText: submitted ? endError : undefined } }} />
            </Stack>
            {serverError && <Alert severity="error">{serverError}</Alert>}
            {needsName && submitted && nameError && <Typography color="text.primary" sx={{ fontWeight: 700 }}>{nameError}</Typography>}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" form="add-member-form" variant="contained" disabled={busy}>Add member</Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={open && confirmExisting}
        title="Add someone who already has an account?"
        confirmLabel="Add member"
        busy={busy}
        error={serverError}
        onConfirm={() => void submit(true)}
        onCancel={() => setConfirmExisting(false)}
      >
        <Typography>
          Someone already uses this email. This adds a new membership to that person. Any current
          membership they have in another LC will end automatically.
        </Typography>
      </ConfirmDialog>
    </>
  )
}
