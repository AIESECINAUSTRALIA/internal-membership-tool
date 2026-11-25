import { Alert, MenuItem, TextField, Typography } from '@mui/material'
import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'

import { useApi } from '../api/ApiContext'
import { useReferenceData } from '../api/ReferenceDataContext'
import type { AdminMembershipRow, CorrectMembershipInput, FunctionDef, Level, Position } from '../api/types'
import { AdminDialogFrame, type AdminDialogProps } from './AdminDialogFrame'

const iso = (value: Dayjs | null) => (value && value.isValid() ? value.format('YYYY-MM-DD') : null)

/** Positions that fit an LC of this type (§3.6), lowest rank first. The server checks
 * the hierarchy rule (§3.4) and says so if a choice is above the admin's own rank. */
function positionsFor(positions: Position[], level: Level | undefined): Position[] {
  return positions.filter((p) => p.level === level).sort((a, b) => a.rank - b.rank)
}

/** The President function goes with presidential positions only (see `Position.presidential`). */
function functionsFor(functions: FunctionDef[], position: Position | undefined): FunctionDef[] {
  return functions.filter((f) => f.active && f.presidentOnly === Boolean(position?.presidential))
}

function DateField({ label, value, onChange }: { label: string; value: Dayjs | null; onChange: (value: Dayjs | null) => void }) {
  return (
    <DatePicker
      label={label}
      format="DD/MM/YYYY"
      value={value}
      onChange={onChange}
      slotProps={{ textField: { required: true, fullWidth: true } }}
    />
  )
}

/**
 * Assign a new membership to a person (§2A.2). An admin can pick any LC. Picking an LC
 * other than the one they're in now is a transfer: their memberships elsewhere end the
 * day before the new one starts (§5.1), so the dialog says so before they confirm.
 */
export function AssignMembershipDialog({
  personId,
  currentLcIds,
  ...props
}: AdminDialogProps & { personId: string; currentLcIds: string[] }) {
  const api = useApi()
  const { reference } = useReferenceData()
  const [lcId, setLcId] = useState('')
  const [positionKey, setPositionKey] = useState('')
  const [functionKey, setFunctionKey] = useState('')
  const [start, setStart] = useState<Dayjs | null>(dayjs())
  const [end, setEnd] = useState<Dayjs | null>(null)

  const lcs = reference?.lcs.filter((l) => l.active) ?? []
  const lc = lcs.find((l) => l.id === lcId)
  const positions = positionsFor(reference?.positions ?? [], lc?.type)
  const position = positions.find((p) => p.key === positionKey)
  const functions = functionsFor(reference?.functions ?? [], position)
  const isTransfer = lc !== undefined && currentLcIds.some((id) => id !== lc.id)

  const canSubmit = lc !== undefined && position !== undefined && functionKey !== '' && iso(start) !== null && iso(end) !== null

  const submit = async () => {
    const result = await api.assignMembership(personId, {
      lcId,
      positionKey,
      functionKey,
      startDate: iso(start)!,
      endDate: iso(end)!,
    })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <AdminDialogFrame {...props} title="Assign membership" submitLabel="Assign" canSubmit={canSubmit} submit={submit} maxWidth="sm">
      <TextField
        select
        required
        label="LC"
        value={lcId}
        onChange={(e) => {
          setLcId(e.target.value)
          setPositionKey('')
          setFunctionKey('')
        }}
      >
        {lcs.map((l) => (
          <MenuItem key={l.id} value={l.id}>
            {l.name}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        select
        required
        label="Position"
        value={positionKey}
        disabled={!lc}
        onChange={(e) => {
          setPositionKey(e.target.value)
          setFunctionKey('')
        }}
      >
        {positions.map((p) => (
          <MenuItem key={p.key} value={p.key}>
            {p.label}
          </MenuItem>
        ))}
      </TextField>
      <TextField select required label="Function" value={functionKey} disabled={!position} onChange={(e) => setFunctionKey(e.target.value)}>
        {functions.map((f) => (
          <MenuItem key={f.key} value={f.key}>
            {f.label}
          </MenuItem>
        ))}
      </TextField>
      <DateField label="Start date" value={start} onChange={setStart} />
      <DateField label="End date" value={end} onChange={setEnd} />
      {isTransfer && (
        <Alert severity="warning">
          This is a transfer. Their memberships in other LCs end the day before this one starts. Their past
          records stay with those LCs.
        </Alert>
      )}
    </AdminDialogFrame>
  )
}

/**
 * Correct a mistake in a membership's position, function or dates (§2A.2). This changes
 * the record in place, so it's for fixing data entry. A real change of role is End +
 * Assign, so history shows what happened (§5.1). The LC can't be corrected: that's a
 * transfer. Only the fields that changed are sent.
 */
export function CorrectMembershipDialog({ membership, ...props }: AdminDialogProps & { membership: AdminMembershipRow }) {
  const api = useApi()
  const { reference } = useReferenceData()
  const [positionKey, setPositionKey] = useState(membership.position?.key ?? '')
  const [functionKey, setFunctionKey] = useState(membership.function?.key ?? '')
  const [start, setStart] = useState<Dayjs | null>(dayjs(membership.startDate))
  const [end, setEnd] = useState<Dayjs | null>(membership.endDate ? dayjs(membership.endDate) : null)

  const positions = positionsFor(reference?.positions ?? [], membership.lc.type)
  const position = positions.find((p) => p.key === positionKey)
  const functions = functionsFor(reference?.functions ?? [], position)
  // Keep the current function on the list even if it would not normally be offered.
  const functionOptions =
    membership.function && !functions.some((f) => f.key === membership.function!.key)
      ? [...functions, { ...membership.function, active: true, presidentOnly: false }]
      : functions

  const changes: CorrectMembershipInput = {}
  if (positionKey !== (membership.position?.key ?? '')) changes.positionKey = positionKey
  if (functionKey !== (membership.function?.key ?? '')) changes.functionKey = functionKey === '' ? null : functionKey
  if (iso(start) !== membership.startDate && iso(start) !== null) changes.startDate = iso(start)!
  if (iso(end) !== membership.endDate && iso(end) !== null) changes.endDate = iso(end)!
  const canSubmit = Object.keys(changes).length > 0 && position !== undefined && iso(start) !== null && iso(end) !== null

  const submit = async () => {
    const result = await api.correctMembership(membership.id, changes)
    return result.status === 'ok' ? null : result.message
  }

  return (
    <AdminDialogFrame
      {...props}
      title={`Correct membership in ${membership.lc.name}`}
      submitLabel="Save correction"
      canSubmit={canSubmit}
      submit={submit}
      maxWidth="sm"
    >
      <Typography variant="body2" color="text.secondary">
        Use this to fix a mistake. If their role really changed, end this membership and assign a new one, so
        their history stays right.
      </Typography>
      <TextField
        select
        required
        label="Position"
        value={positionKey}
        onChange={(e) => {
          const next = positions.find((p) => p.key === e.target.value)
          setPositionKey(e.target.value)
          // Keep the function if it still goes with the new position; otherwise clear it.
          if (!functionsFor(reference?.functions ?? [], next).some((f) => f.key === functionKey)) setFunctionKey('')
        }}
      >
        {positions.map((p) => (
          <MenuItem key={p.key} value={p.key}>
            {p.label}
          </MenuItem>
        ))}
      </TextField>
      <TextField select label="Function" value={functionKey} onChange={(e) => setFunctionKey(e.target.value)}>
        <MenuItem value="">
          <em>No function</em>
        </MenuItem>
        {functionOptions.map((f) => (
          <MenuItem key={f.key} value={f.key}>
            {f.label}
          </MenuItem>
        ))}
      </TextField>
      <DateField label="Start date" value={start} onChange={setStart} />
      <DateField label="End date" value={end} onChange={setEnd} />
    </AdminDialogFrame>
  )
}

/** End a membership early. Asks for confirmation, since it changes someone's access (§2A). */
export function EndMembershipDialog({ membership, ...props }: AdminDialogProps & { membership: AdminMembershipRow }) {
  const api = useApi()
  const [end, setEnd] = useState<Dayjs | null>(dayjs())

  const submit = async () => {
    const result = await api.endMembership(membership.id, iso(end)!)
    return result.status === 'ok' ? null : result.message
  }

  const role = [membership.position?.label, membership.function?.label].filter(Boolean).join(', ')
  return (
    <AdminDialogFrame {...props} title="End membership" submitLabel="End membership" canSubmit={iso(end) !== null} submit={submit}>
      <Typography>
        {role} in {membership.lc.name}. They keep this membership&rsquo;s access until the end date. Its history and KPI
        records stay.
      </Typography>
      <DateField label="End date" value={end} onChange={setEnd} />
    </AdminDialogFrame>
  )
}
