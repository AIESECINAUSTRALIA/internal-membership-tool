import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  MenuItem,
  Paper,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { DatePicker } from '@mui/x-date-pickers/DatePicker'
import dayjs from 'dayjs'
import { useState, type ReactNode } from 'react'

import { useApi } from '../api/ApiContext'
import type { CustomField, CustomFieldValue, Me } from '../api/types'
import { useAuth } from '../auth/authContext'
import { formatDate, humanise, SCOPE_LABELS, shortLabel } from '../lib/labels'

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <Paper variant="outlined" component="section" aria-labelledby={id} sx={{ p: 3 }}>
      <Typography id={id} variant="h2" component="h2" sx={{ mb: 2 }}>
        {title}
      </Typography>
      {children}
    </Paper>
  )
}

/** Names and email are locked. An admin corrects them on the Admin console (§2A.9). */
function Identity({ me }: { me: Me }) {
  const rows: [string, string][] = [
    ['First name', me.person.firstName],
    ['Last name', me.person.lastName],
    ['Email', me.person.email],
  ]
  return (
    <Section id="profile-identity" title="Your details">
      <Box component="dl" sx={{ m: 0, display: 'grid', gridTemplateColumns: 'max-content 1fr', columnGap: 4, rowGap: 1 }}>
        {rows.map(([label, value]) => (
          <Box key={label} sx={{ display: 'contents' }}>
            <Typography component="dt" sx={{ fontWeight: 700 }}>
              {label}
            </Typography>
            <Typography component="dd" sx={{ m: 0 }}>
              {value || 'None'}
            </Typography>
          </Box>
        ))}
      </Box>
      <Typography color="text.secondary" sx={{ mt: 2, maxWidth: '65ch' }}>
        Your name, email, position, function, LC and dates can&rsquo;t be changed here. To correct
        one, ask someone in your EB or MC.
      </Typography>
    </Section>
  )
}

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: CustomField
  value: CustomFieldValue
  onChange: (value: CustomFieldValue) => void
}) {
  switch (field.dataType) {
    case 'boolean':
      return (
        <FormControlLabel
          control={<Checkbox checked={value === true} onChange={(e) => onChange(e.target.checked)} />}
          label={field.label}
        />
      )
    case 'enum':
      return (
        <TextField select label={field.label} value={value ?? ''} onChange={(e) => onChange(e.target.value || null)} fullWidth>
          <MenuItem value="">Not set</MenuItem>
          {field.enumOptions?.map((option) => (
            <MenuItem key={option} value={option}>
              {option}
            </MenuItem>
          ))}
        </TextField>
      )
    case 'date':
      return (
        <DatePicker
          label={field.label}
          format="DD/MM/YYYY"
          value={typeof value === 'string' ? dayjs(value) : null}
          onChange={(d) => onChange(d?.isValid() ? d.format('YYYY-MM-DD') : null)}
          slotProps={{ textField: { fullWidth: true } }}
        />
      )
    case 'number':
      return (
        <TextField
          type="number"
          label={field.label}
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
          fullWidth
        />
      )
    default:
      return <TextField label={field.label} value={value ?? ''} onChange={(e) => onChange(e.target.value || null)} fullWidth />
  }
}

/** The only editable part of Profile: person-level custom fields (§2A.9, §4.2). */
function CustomFields({ me }: { me: Me }) {
  const api = useApi()
  const { setMe } = useAuth()
  const [values, setValues] = useState<Record<string, CustomFieldValue>>(() =>
    Object.fromEntries(me.person.customFields.map((f) => [f.key, f.value])),
  )
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  if (me.person.customFields.length === 0) return null

  const handleSave = async () => {
    setSaving(true)
    try {
      setMe(await api.updateMyCustomFields(values))
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Section id="profile-fields" title="About you">
      <Stack spacing={2.5} sx={{ maxWidth: 420 }}>
        {me.person.customFields.map((field) => (
          <FieldInput
            key={field.key}
            field={field}
            value={values[field.key] ?? null}
            onChange={(value) => setValues((prev) => ({ ...prev, [field.key]: value }))}
          />
        ))}
        <Box>
          <Button variant="contained" onClick={handleSave} disabled={saving}>
            Save changes
          </Button>
        </Box>
      </Stack>
      <Snackbar open={saved} autoHideDuration={4000} onClose={() => setSaved(false)}>
        <Alert severity="success" onClose={() => setSaved(false)}>
          Changes saved
        </Alert>
      </Snackbar>
    </Section>
  )
}

/** Read-only, newest first, one row per membership (§2A.9). */
function PositionHistory({ me }: { me: Me }) {
  const rows = [...me.memberships].sort((a, b) => (a.startDate < b.startDate ? 1 : a.startDate > b.startDate ? -1 : 0))
  return (
    <Section id="profile-history" title="Position history">
      {rows.length === 0 ? (
        <Typography>No data exists</Typography>
      ) : (
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" aria-labelledby="profile-history">
            <TableHead>
              <TableRow>
                <TableCell>Position</TableCell>
                <TableCell>Function</TableCell>
                <TableCell>LC</TableCell>
                <TableCell>Start date</TableCell>
                <TableCell>End date</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((m) => (
                <TableRow key={m.id}>
                  <TableCell>{m.position.label}</TableCell>
                  <TableCell>{m.function ? shortLabel(m.function.label) : 'None'}</TableCell>
                  <TableCell>{m.lc.name}</TableCell>
                  <TableCell>{formatDate(m.startDate)}</TableCell>
                  <TableCell>{formatDate(m.endDate)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      )}
    </Section>
  )
}

/** Every grant, exactly as the server resolved it (§2A.9). Read-only. */
function Permissions({ me }: { me: Me }) {
  const rows = [...me.permissions].sort(
    (a, b) => a.resource.localeCompare(b.resource) || a.action.localeCompare(b.action),
  )
  return (
    <Section id="profile-permissions" title="Your permissions">
      {rows.length === 0 ? (
        <Typography>No data exists</Typography>
      ) : (
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" aria-labelledby="profile-permissions">
            <TableHead>
              <TableRow>
                <TableCell>Resource</TableCell>
                <TableCell>Action</TableCell>
                <TableCell>Scope</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((p) => (
                <TableRow key={`${p.resource}:${p.action}`}>
                  <TableCell>{humanise(p.resource)}</TableCell>
                  <TableCell>{humanise(p.action)}</TableCell>
                  <TableCell>{SCOPE_LABELS[p.scope]}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      )}
    </Section>
  )
}

/**
 * Profile (spec §2A.9): who you are, what you may do, your position history, and edit
 * of your own person-level custom fields. Names, email, membership and dates are locked.
 */
export function ProfilePage() {
  const { me } = useAuth()
  if (!me) return null
  return (
    <Stack spacing={3}>
      <Typography variant="h1" component="h1">
        Profile
      </Typography>
      <Identity me={me} />
      <CustomFields me={me} />
      <PositionHistory me={me} />
      <Permissions me={me} />
    </Stack>
  )
}
