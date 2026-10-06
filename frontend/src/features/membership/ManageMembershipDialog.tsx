import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Stack, TextField, Typography } from '@mui/material'
import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useState } from 'react'

import { useApi } from '../../api/ApiContext'
import type { MemberSummaryRow, MembershipDetail } from '../../api/types'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { formatDate, fullName, roleLabel } from '../../lib/labels'

export type ManageKind = 'extend' | 'move'

interface Props {
  kind: ManageKind
  row: MemberSummaryRow
  /** Memberships of this person the action may be applied to (from `rowActions`). */
  eligibleRoleIds: string[]
  onClose: () => void
  /** Called after the change is saved, with the message to show. */
  onDone: (message: string) => void
}

const TEXT = {
  extend: { title: 'Extend term', done: 'Term extended' },
  move: { title: 'Move to team', done: 'Moved to team' },
} as const

/**
 * Extend term and Move to team (spec §2A.5). Both work on ONE membership, because the
 * hierarchy rule compares the specific membership acted on (§3.4). The person may hold
 * several, so a picker appears when more than one is eligible. Both ask for a second
 * confirmation before anything changes.
 */
export function ManageMembershipDialog({ kind, row, eligibleRoleIds, onClose, onDone }: Props) {
  const api = useApi()
  const [roleId, setRoleId] = useState(eligibleRoleIds[0])
  const [loaded, setLoaded] = useState<MembershipDetail | null>(null)
  const [newEnd, setNewEnd] = useState<Dayjs | null>(null)
  const [teamId, setTeamId] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api.getMembershipDetail(roleId).then((detail) => {
      if (!cancelled) setLoaded(detail)
    })
    return () => {
      cancelled = true
    }
  }, [api, roleId])

  const detail = loaded?.membershipId === roleId ? loaded : null
  const personName = fullName(row.firstName, row.lastName)
  const role = row.roles.find((r) => r.membershipId === roleId)
  const roleText = role ? roleLabel(role.position, role.function) : ''
  const currentEnd = detail?.endDate ? dayjs(detail.endDate) : null
  const chosenTeam = detail?.teamOptions.find((t) => t.id === teamId)

  const endError = !newEnd?.isValid()
    ? 'Enter a new end date.'
    : currentEnd && !newEnd.isAfter(currentEnd, 'day')
      ? 'Choose a date after the current end date.'
      : ''
  const teamError = !chosenTeam ? 'Choose a team.' : ''
  const error = kind === 'extend' ? endError : teamError

  const review = () => {
    setSubmitted(true)
    if (!error && detail) setConfirming(true)
  }

  const apply = async () => {
    setBusy(true)
    setServerError(null)
    try {
      const result =
        kind === 'extend'
          ? await api.extendTerm(roleId, newEnd!.format('YYYY-MM-DD'))
          : await api.moveToTeam(roleId, teamId)
      if (result.status === 'ok') onDone(TEXT[kind].done)
      else setServerError(result.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Dialog open={!confirming} onClose={onClose} maxWidth="sm" fullWidth>
        <DialogTitle>{TEXT[kind].title}</DialogTitle>
        <DialogContent>
          <Stack spacing={2.5} sx={{ pt: 1 }}>
            <Typography>{personName}</Typography>
            {eligibleRoleIds.length > 1 && (
              <TextField select label="Membership" value={roleId} onChange={(e) => { setRoleId(e.target.value); setTeamId(''); setNewEnd(null); setSubmitted(false) }} fullWidth>
                {eligibleRoleIds.map((id) => {
                  const r = row.roles.find((x) => x.membershipId === id)
                  return <MenuItem key={id} value={id}>{r ? roleLabel(r.position, r.function) : id}</MenuItem>
                })}
              </TextField>
            )}
            {kind === 'extend' && (
              <>
                <Typography color="text.secondary">
                  {detail ? `${roleText} ends on ${formatDate(detail.endDate)}.` : 'Loading…'}
                </Typography>
                <DatePicker
                  label="New end date"
                  format="DD/MM/YYYY"
                  value={newEnd}
                  onChange={setNewEnd}
                  minDate={currentEnd?.add(1, 'day')}
                  slotProps={{ textField: { required: true, fullWidth: true, error: submitted && !!endError, helperText: submitted ? endError : undefined } }}
                />
              </>
            )}
            {kind === 'move' && (
              <>
                <Typography color="text.secondary">
                  {detail ? `Current team: ${detail.currentTeam?.name ?? 'No team'}.` : 'Loading…'}
                </Typography>
                {detail && detail.teamOptions.length === 0 ? (
                  <Alert severity="info">There are no other teams in this LC and function to move them to.</Alert>
                ) : (
                  <TextField select label="Move to" required value={teamId} onChange={(e) => setTeamId(e.target.value)} error={submitted && !!teamError} helperText={submitted ? teamError : undefined} disabled={!detail} fullWidth>
                    {(detail?.teamOptions ?? []).map((t) => (
                      <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>
                    ))}
                  </TextField>
                )}
              </>
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="contained" onClick={review} disabled={!detail || (kind === 'move' && detail.teamOptions.length === 0)}>
            {TEXT[kind].title}
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={confirming}
        title={`${TEXT[kind].title}?`}
        confirmLabel={TEXT[kind].title}
        busy={busy}
        error={serverError}
        onConfirm={() => void apply()}
        onCancel={() => { setConfirming(false); setServerError(null) }}
      >
        <Typography>
          {kind === 'extend' && detail && newEnd
            ? `${personName}'s ${roleText} term will now end on ${formatDate(newEnd.format('YYYY-MM-DD'))} instead of ${formatDate(detail.endDate)}.`
            : `${personName} will move from ${detail?.currentTeam?.name ?? 'no team'} to ${chosenTeam?.name ?? ''}.`}
        </Typography>
      </ConfirmDialog>
    </>
  )
}
