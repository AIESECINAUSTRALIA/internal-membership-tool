import { Checkbox, FormControlLabel, MenuItem, TextField, Typography } from '@mui/material'
import { useState } from 'react'

import { useApi } from '../api/ApiContext'
import type { AdminFunctionRow, AdminPositionRow, Level } from '../api/types'
import { AdminDialogFrame, type AdminDialogProps } from './AdminDialogFrame'

/**
 * The dialogs of the Positions & functions screen (spec §1.5, §2A.2). They all use the
 * shared `AdminDialogFrame`, like the LC and Metrics dialogs. The server re-checks
 * every rule; the dialogs only stop obviously incomplete forms from being sent.
 */

/** The highest rank the signed-in admin may give a position: one below their own (§3.4). */
interface RankLimit {
  maxRank: number
}

/** A whole number from 1 up to `maxRank`, or null if the field isn't one yet. */
function parseRank(value: string, maxRank: number): number | null {
  const rank = Number(value)
  if (value.trim() === '' || !Number.isInteger(rank) || rank < 1 || rank > maxRank) return null
  return rank
}

/** The Level, Rank and president-exception fields shared by Add and Edit details. */
function PositionDetailsFields({
  level,
  setLevel,
  rank,
  setRank,
  canAddSameRank,
  setCanAddSameRank,
  maxRank,
}: {
  level: Level | ''
  setLevel: (level: Level | '') => void
  rank: string
  setRank: (rank: string) => void
  canAddSameRank: boolean
  setCanAddSameRank: (value: boolean) => void
  maxRank: number
}) {
  return (
    <>
      <TextField select required label="Level" value={level} onChange={(e) => setLevel(e.target.value as Level | '')}>
        <MenuItem value="lc">LC</MenuItem>
        <MenuItem value="mc">MC</MenuItem>
      </TextField>
      <TextField
        required
        label="Rank"
        type="number"
        value={rank}
        onChange={(e) => setRank(e.target.value)}
        helperText={`A higher number is a more senior position. You can set 1 to ${maxRank}, below your own position.`}
        slotProps={{ htmlInput: { min: 1, max: maxRank } }}
      />
      <FormControlLabel
        control={<Checkbox checked={canAddSameRank} onChange={(e) => setCanAddSameRank(e.target.checked)} />}
        label="People in this position can add another person to the same position (like the LC President)"
      />
    </>
  )
}

// ---------------------------------------------------------------------------
// Position dialogs
// ---------------------------------------------------------------------------

export function AddPositionDialog({ maxRank, ...props }: AdminDialogProps & RankLimit) {
  const api = useApi()
  const [label, setLabel] = useState('')
  const [level, setLevel] = useState<Level | ''>('')
  const [rank, setRank] = useState('')
  const [canAddSameRank, setCanAddSameRank] = useState(false)
  const parsedRank = parseRank(rank, maxRank)

  const submit = async () => {
    if (level === '' || parsedRank === null) return 'Choose a level and a rank.'
    const result = await api.createPosition({ label, level, rank: parsedRank, canAddSameRank })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <AdminDialogFrame
      {...props}
      title="Add position"
      submitLabel="Add position"
      canSubmit={label.trim() !== '' && level !== '' && parsedRank !== null}
      submit={submit}
    >
      <TextField required autoFocus label="Name" value={label} onChange={(e) => setLabel(e.target.value)} />
      <PositionDetailsFields
        level={level}
        setLevel={setLevel}
        rank={rank}
        setRank={setRank}
        canAddSameRank={canAddSameRank}
        setCanAddSameRank={setCanAddSameRank}
        maxRank={maxRank}
      />
    </AdminDialogFrame>
  )
}

export function RenamePositionDialog({ position, ...props }: AdminDialogProps & { position: AdminPositionRow }) {
  const api = useApi()
  const [label, setLabel] = useState(position.label)

  const submit = async () => {
    const result = await api.updatePosition(position.id, { label })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <AdminDialogFrame
      {...props}
      title={`Rename "${position.label}"`}
      submitLabel="Rename"
      canSubmit={label.trim() !== '' && label.trim() !== position.label}
      submit={submit}
    >
      <TextField required autoFocus label="Name" value={label} onChange={(e) => setLabel(e.target.value)} />
      <Typography variant="body2" color="text.secondary">
        The new name shows everywhere. Everyone&rsquo;s membership history keeps this position.
      </Typography>
    </AdminDialogFrame>
  )
}

export function EditPositionDetailsDialog({
  position,
  maxRank,
  ...props
}: AdminDialogProps & RankLimit & { position: AdminPositionRow }) {
  const api = useApi()
  const [level, setLevel] = useState<Level | ''>(position.level ?? '')
  const [rank, setRank] = useState(position.rank !== null ? String(position.rank) : '')
  const [canAddSameRank, setCanAddSameRank] = useState(position.canAddSameRank)
  const parsedRank = parseRank(rank, maxRank)

  const submit = async () => {
    if (level === '' || parsedRank === null) return 'Choose a level and a rank.'
    const result = await api.updatePosition(position.id, { level, rank: parsedRank, canAddSameRank })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <AdminDialogFrame
      {...props}
      title={`Edit details: ${position.label}`}
      submitLabel="Save"
      canSubmit={level !== '' && parsedRank !== null}
      submit={submit}
    >
      <PositionDetailsFields
        level={level}
        setLevel={setLevel}
        rank={rank}
        setRank={setRank}
        canAddSameRank={canAddSameRank}
        setCanAddSameRank={setCanAddSameRank}
        maxRank={maxRank}
      />
    </AdminDialogFrame>
  )
}

export function SetPositionActiveDialog({
  position,
  makeActive,
  ...props
}: AdminDialogProps & { position: AdminPositionRow; makeActive: boolean }) {
  const api = useApi()

  const submit = async () => {
    const result = await api.updatePosition(position.id, { active: makeActive })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <AdminDialogFrame
      {...props}
      title={makeActive ? `Reactivate "${position.label}"` : `Deactivate "${position.label}"`}
      submitLabel={makeActive ? 'Reactivate' : 'Deactivate'}
      canSubmit
      submit={submit}
    >
      <Typography>
        {makeActive
          ? 'This position will be offered again when adding members.'
          : 'This position will no longer be offered when adding members. Everyone who already holds it keeps it. You can reactivate it later.'}
      </Typography>
    </AdminDialogFrame>
  )
}

// ---------------------------------------------------------------------------
// Function dialogs
// ---------------------------------------------------------------------------

export function AddFunctionDialog(props: AdminDialogProps) {
  const api = useApi()
  const [label, setLabel] = useState('')

  const submit = async () => {
    const result = await api.createFunction({ label })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <AdminDialogFrame
      {...props}
      title="Add function"
      submitLabel="Add function"
      canSubmit={label.trim() !== ''}
      submit={submit}
    >
      <TextField required autoFocus label="Name" value={label} onChange={(e) => setLabel(e.target.value)} />
      <Typography variant="body2" color="text.secondary">
        You can rename the function later.
      </Typography>
    </AdminDialogFrame>
  )
}

export function RenameFunctionDialog({ func, ...props }: AdminDialogProps & { func: AdminFunctionRow }) {
  const api = useApi()
  const [label, setLabel] = useState(func.label)

  const submit = async () => {
    const result = await api.updateFunction(func.id, { label })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <AdminDialogFrame
      {...props}
      title={`Rename "${func.label}"`}
      submitLabel="Rename"
      canSubmit={label.trim() !== '' && label.trim() !== func.label}
      submit={submit}
    >
      <TextField required autoFocus label="Name" value={label} onChange={(e) => setLabel(e.target.value)} />
      <Typography variant="body2" color="text.secondary">
        The new name shows everywhere. Everyone&rsquo;s membership history keeps this function.
      </Typography>
    </AdminDialogFrame>
  )
}

export function SetFunctionActiveDialog({
  func,
  makeActive,
  ...props
}: AdminDialogProps & { func: AdminFunctionRow; makeActive: boolean }) {
  const api = useApi()

  const submit = async () => {
    const result = await api.updateFunction(func.id, { active: makeActive })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <AdminDialogFrame
      {...props}
      title={makeActive ? `Reactivate "${func.label}"` : `Deactivate "${func.label}"`}
      submitLabel={makeActive ? 'Reactivate' : 'Deactivate'}
      canSubmit
      submit={submit}
    >
      <Typography>
        {makeActive
          ? 'This function will be offered again when adding members.'
          : 'This function will no longer be offered when adding members. Everyone who already has it keeps it. You can reactivate it later.'}
      </Typography>
    </AdminDialogFrame>
  )
}
