import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import GroupsOutlined from '@mui/icons-material/GroupsOutlined'
import EventRepeatOutlined from '@mui/icons-material/EventRepeatOutlined'
import PersonAddAlt1Outlined from '@mui/icons-material/PersonAddAlt1Outlined'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useState } from 'react'

import { useApi } from '../../api/ApiContext'
import type { MemberSummaryRow, MembershipDetail } from '../../api/types'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { formatDate, fullName, roleLabel } from '../../lib/labels'

const KEEP_CURRENT_TEAM = ''

interface Props {
  row: MemberSummaryRow
  /** Memberships of this person the actor may move between teams (from `rowActions`). */
  teamEligibleRoleIds: string[]
  /** Memberships of this person the actor may extend (from `rowActions`). */
  termEligibleRoleIds: string[]
  /** Whether the actor may add this person to another function at all (reuses Add member). */
  canAddFunction: boolean
  onClose: () => void
  /** Called after at least one change is saved, with the message to show. */
  onDone: (message: string) => void
  /** Opens the existing Add member dialog so the actor can give this person another
   * function. Not pre-filled — the person's email never reaches the frontend (spec
   * §2A.5), so there's nothing to carry across. */
  onAddFunction: () => void
}

/**
 * Manage membership (spec §2A.5): Move to team and Extend term for one person, in one
 * place, instead of two separate single-purpose dialogs. A person can hold several
 * memberships, and the hierarchy rule compares the SPECIFIC membership acted on
 * (§3.4), so a picker appears when more than one is eligible for either action.
 *
 * Picking a different membership below swaps which one this whole panel edits, so the
 * editable fields are a child component keyed by `roleId` — switching memberships
 * remounts it with fresh state instead of needing an effect to reset five fields by hand.
 */
export function ManageMembershipPanel({ row, teamEligibleRoleIds, termEligibleRoleIds, canAddFunction, onClose, onDone, onAddFunction }: Props) {
  const roleIds = [...new Set([...teamEligibleRoleIds, ...termEligibleRoleIds])]
  const [roleId, setRoleId] = useState(roleIds[0])

  return (
    <MembershipFields
      key={roleId}
      row={row}
      roleId={roleId}
      roleIds={roleIds}
      onRoleChange={setRoleId}
      canEditTeam={teamEligibleRoleIds.includes(roleId)}
      canEditTerm={termEligibleRoleIds.includes(roleId)}
      canAddFunction={canAddFunction}
      onClose={onClose}
      onDone={onDone}
      onAddFunction={onAddFunction}
    />
  )
}

function MembershipFields({
  row,
  roleId,
  roleIds,
  onRoleChange,
  canEditTeam,
  canEditTerm,
  canAddFunction,
  onClose,
  onDone,
  onAddFunction,
}: {
  row: MemberSummaryRow
  roleId: string
  roleIds: string[]
  onRoleChange: (roleId: string) => void
  canEditTeam: boolean
  canEditTerm: boolean
  canAddFunction: boolean
  onClose: () => void
  onDone: (message: string) => void
  onAddFunction: () => void
}) {
  const api = useApi()
  const [detail, setDetail] = useState<MembershipDetail | null>(null)
  const [teamId, setTeamId] = useState(KEEP_CURRENT_TEAM)
  const [newEnd, setNewEnd] = useState<Dayjs | null>(null)
  const [submitted, setSubmitted] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)

  const fetchDetail = () =>
    api.getMembershipDetail(roleId).then((loaded) => {
      setDetail(loaded)
      // The date field starts at the current end date, so editing it reads as "change
      // this" rather than "you must pick a fresh date" (a later date is still required).
      setNewEnd(loaded.endDate ? dayjs(loaded.endDate) : null)
    })

  useEffect(() => {
    void fetchDetail()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only: a new `roleId` remounts this whole component (see the `key` in the parent)
  }, [])

  const personName = fullName(row.firstName, row.lastName)
  const role = row.roles.find((r) => r.membershipId === roleId)
  const roleText = role ? roleLabel(role.position, role.function) : ''
  const currentEnd = detail?.endDate ? dayjs(detail.endDate) : null
  const chosenTeam = detail?.teamOptions.find((t) => t.id === teamId)

  const teamChanged = teamId !== KEEP_CURRENT_TEAM
  const endError = canEditTerm && newEnd && currentEnd && !newEnd.isAfter(currentEnd, 'day') ? 'Choose a date after the current end date.' : ''
  const termChanged = canEditTerm && !!newEnd?.isValid() && !endError && !newEnd.isSame(currentEnd, 'day')
  const nothingChanged = !teamChanged && !termChanged

  const review = () => {
    setSubmitted(true)
    if (!endError && !nothingChanged) setConfirming(true)
  }

  const apply = async () => {
    setBusy(true)
    setServerError(null)
    try {
      if (teamChanged) {
        const result = await api.moveToTeam(roleId, teamId)
        if (result.status !== 'ok') {
          setServerError(result.message)
          await fetchDetail()
          return
        }
      }
      if (termChanged) {
        const result = await api.extendTerm(roleId, newEnd!.format('YYYY-MM-DD'))
        if (result.status !== 'ok') {
          setServerError(result.message)
          await fetchDetail()
          return
        }
      }
      onDone(teamChanged && termChanged ? 'Team and term updated' : teamChanged ? 'Moved to team' : 'Term extended')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Dialog open={!confirming} onClose={busy ? undefined : onClose} maxWidth="sm" fullWidth>
        <DialogTitle>Manage membership</DialogTitle>
        <DialogContent>
          <Stack spacing={2.5} sx={{ pt: 1 }}>
            <Typography variant="h3" component="p">
              {personName}
            </Typography>

            {roleIds.length > 1 && (
              <TextField select label="Membership" value={roleId} onChange={(e) => onRoleChange(e.target.value)} fullWidth>
                {roleIds.map((id) => {
                  const r = row.roles.find((x) => x.membershipId === id)
                  return (
                    <MenuItem key={id} value={id}>
                      {r ? roleLabel(r.position, r.function) : id}
                    </MenuItem>
                  )
                })}
              </TextField>
            )}

            {!detail ? (
              <Typography color="text.secondary">Loading…</Typography>
            ) : (
              <>
                {canEditTeam && (
                  <Box>
                    <Stack direction="row" sx={{ alignItems: 'center', gap: 1, mb: 1 }}>
                      <GroupsOutlined color="action" fontSize="small" />
                      <Typography variant="subtitle2">Team</Typography>
                    </Stack>
                    {detail.teamOptions.length === 0 ? (
                      <Alert severity="info">
                        {detail.currentTeam?.name ?? 'No team'} — there are no other teams in this LC and function to
                        move {personName} to.
                      </Alert>
                    ) : (
                      <TextField select label="Team" value={teamId} onChange={(e) => setTeamId(e.target.value)} helperText={`Currently: ${detail.currentTeam?.name ?? 'no team'}`} fullWidth>
                        <MenuItem value={KEEP_CURRENT_TEAM}>Keep current team ({detail.currentTeam?.name ?? 'no team'})</MenuItem>
                        {detail.teamOptions.map((t) => (
                          <MenuItem key={t.id} value={t.id}>
                            {t.name}
                          </MenuItem>
                        ))}
                      </TextField>
                    )}
                  </Box>
                )}

                {canEditTeam && canEditTerm && <Divider />}

                {canEditTerm && (
                  <Box>
                    <Stack direction="row" sx={{ alignItems: 'center', gap: 1, mb: 1 }}>
                      <EventRepeatOutlined color="action" fontSize="small" />
                      <Typography variant="subtitle2">Term</Typography>
                    </Stack>
                    <DatePicker
                      label="End date"
                      format="DD/MM/YYYY"
                      value={newEnd}
                      onChange={setNewEnd}
                      minDate={currentEnd?.add(1, 'day')}
                      slotProps={{
                        textField: {
                          fullWidth: true,
                          helperText: submitted && endError ? endError : `Currently ends on ${formatDate(detail.endDate)}. Choose a later date to extend.`,
                          error: submitted && !!endError,
                        },
                      }}
                    />
                  </Box>
                )}
              </>
            )}

            {canAddFunction && (
              <>
                <Divider />
                <Button startIcon={<PersonAddAlt1Outlined />} onClick={onAddFunction} sx={{ alignSelf: 'flex-start' }}>
                  Add {personName} to another function
                </Button>
              </>
            )}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="contained" onClick={review} disabled={!detail}>
            Save changes
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={confirming}
        title="Save changes?"
        confirmLabel="Save changes"
        busy={busy}
        error={serverError}
        onConfirm={() => void apply()}
        onCancel={() => {
          setConfirming(false)
          setServerError(null)
        }}
      >
        <Stack spacing={1}>
          {teamChanged && (
            <Typography>
              {personName}&rsquo;s {roleText} moves from {detail?.currentTeam?.name ?? 'no team'} to {chosenTeam?.name}.
            </Typography>
          )}
          {termChanged && (
            <Typography>
              {personName}&rsquo;s {roleText} term will now end on {formatDate(newEnd!.format('YYYY-MM-DD'))} instead of{' '}
              {formatDate(detail?.endDate ?? null)}.
            </Typography>
          )}
        </Stack>
      </ConfirmDialog>
    </>
  )
}
