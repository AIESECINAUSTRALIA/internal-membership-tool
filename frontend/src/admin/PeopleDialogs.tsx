import { TextField, Typography } from '@mui/material'
import { useState } from 'react'

import { useApi } from '../api/ApiContext'
import type { AdminPersonRow } from '../api/types'
import { fullName } from '../lib/labels'
import { AdminDialogFrame, type AdminDialogProps } from './AdminDialogFrame'

/** First name, last name and AIESEC email: the whole person record an admin edits. */
function PersonFields({
  firstName,
  lastName,
  email,
  onChange,
}: {
  firstName: string
  lastName: string
  email: string
  onChange: (field: 'firstName' | 'lastName' | 'email', value: string) => void
}) {
  return (
    <>
      <TextField required autoFocus label="First name" value={firstName} onChange={(e) => onChange('firstName', e.target.value)} />
      <TextField required label="Last name" value={lastName} onChange={(e) => onChange('lastName', e.target.value)} />
      <TextField
        required
        type="email"
        label="AIESEC email"
        value={email}
        onChange={(e) => onChange('email', e.target.value)}
        helperText="They sign in with this address."
      />
    </>
  )
}

export function AddPersonDialog(props: AdminDialogProps) {
  const api = useApi()
  const [values, setValues] = useState({ firstName: '', lastName: '', email: '' })
  const filled = values.firstName.trim() !== '' && values.lastName.trim() !== '' && values.email.trim() !== ''

  const submit = async () => {
    const result = await api.createPerson(values)
    return result.status === 'ok' ? null : result.message
  }

  return (
    <AdminDialogFrame {...props} title="Add person" submitLabel="Add person" canSubmit={filled} submit={submit}>
      <PersonFields {...values} onChange={(field, value) => setValues((v) => ({ ...v, [field]: value }))} />
      <Typography variant="body2" color="text.secondary">
        They can sign in once they have a membership. Assign one on the Memberships screen.
      </Typography>
    </AdminDialogFrame>
  )
}

export function EditPersonDialog({ person, ...props }: AdminDialogProps & { person: AdminPersonRow }) {
  const api = useApi()
  const [values, setValues] = useState({ firstName: person.firstName, lastName: person.lastName, email: person.email })
  const filled = values.firstName.trim() !== '' && values.lastName.trim() !== '' && values.email.trim() !== ''
  const changed =
    values.firstName.trim() !== person.firstName ||
    values.lastName.trim() !== person.lastName ||
    values.email.trim().toLowerCase() !== person.email.toLowerCase()

  const submit = async () => {
    const result = await api.updatePerson(person.id, values)
    return result.status === 'ok' ? null : result.message
  }

  return (
    <AdminDialogFrame
      {...props}
      title={`Edit ${fullName(person.firstName, person.lastName)}`}
      submitLabel="Save"
      canSubmit={filled && changed}
      submit={submit}
    >
      <PersonFields {...values} onChange={(field, value) => setValues((v) => ({ ...v, [field]: value }))} />
      <Typography variant="body2" color="text.secondary">
        Changing the email changes which account can sign in as this person.
      </Typography>
    </AdminDialogFrame>
  )
}

/** Deactivate (the soft delete) or reactivate. Both ask for confirmation (§2A). */
export function SetPersonActiveDialog({
  person,
  makeActive,
  ...props
}: AdminDialogProps & { person: AdminPersonRow; makeActive: boolean }) {
  const api = useApi()
  const name = fullName(person.firstName, person.lastName)

  const submit = async () => {
    const result = makeActive ? await api.reactivatePerson(person.id) : await api.deactivatePerson(person.id)
    return result.status === 'ok' ? null : result.message
  }

  return (
    <AdminDialogFrame
      {...props}
      title={makeActive ? `Reactivate ${name}` : `Deactivate ${name}`}
      submitLabel={makeActive ? 'Reactivate' : 'Deactivate'}
      canSubmit
      submit={submit}
    >
      {makeActive ? (
        <Typography>
          {name} will be able to sign in again once they have a current membership. Their ended memberships stay
          ended: assign a new one on the Memberships screen.
        </Typography>
      ) : (
        <Typography>
          {name} won&rsquo;t be able to sign in, and their current memberships end straight away. Nothing is deleted: their
          membership history and KPI records stay as they are, and you can reactivate them later.
        </Typography>
      )}
    </AdminDialogFrame>
  )
}
