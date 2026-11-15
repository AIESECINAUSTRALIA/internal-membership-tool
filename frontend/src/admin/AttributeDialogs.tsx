/**
 * Dialogs for the Metrics & custom fields screen (spec §1.5, §4.2): one form for adding
 * and editing a catalog row, and the deactivate/reactivate confirmation.
 *
 * The form only shows the inputs that make sense for the chosen data type (unit for
 * numbers, options for a choice list, min/max for numbers and dates, a format for text),
 * and turns them into the `attribute` row the server expects. The server re-checks
 * everything; the form only keeps people from building something it would reject.
 */
import { Checkbox, FormControlLabel, MenuItem, TextField, Typography } from '@mui/material'
import { useState } from 'react'

import { useApi } from '../api/ApiContext'
import { useReferenceData } from '../api/ReferenceDataContext'
import type {
  AttributeAppliesTo,
  AttributeDataType,
  AttributeValidation,
  CatalogAttribute,
  CreateAttributeInput,
  UpdateAttributeInput,
} from '../api/types'
import { APPLIES_TO_LABELS, DATA_TYPE_LABELS } from '../lib/labels'
import { AdminDialogFrame, type AdminDialogProps } from './AdminDialogFrame'

/** The fields an edit may change, in the order the server lists them. */
const EDITABLE_FIELDS = ['label', 'dataType', 'unit', 'enumOptions', 'validation', 'functionKey'] as const

/** Everything the form holds, as the inputs hold it (strings, mostly). */
interface FormState {
  label: string
  key: string
  /** Once the admin types a key themself, stop suggesting one from the label. */
  keyEdited: boolean
  appliesTo: AttributeAppliesTo
  dataType: AttributeDataType
  unit: string
  /** One option per line. */
  options: string
  required: boolean
  min: string
  max: string
  regex: string
  /** '' means every function. */
  functionKey: string
}

/** "Cold calls!" -> "cold_calls": a key the server accepts (lowercase, a-z 0-9 _). */
function suggestKey(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^[^a-z]+/, '')
    .replace(/_+$/, '')
}

function formFrom(attribute: CatalogAttribute | null): FormState {
  const v = attribute?.validation ?? {}
  return {
    label: attribute?.label ?? '',
    key: attribute?.key ?? '',
    keyEdited: attribute !== null,
    appliesTo: attribute?.appliesTo ?? 'kpi',
    dataType: attribute?.dataType ?? 'number',
    unit: attribute?.unit ?? '',
    options: (attribute?.enumOptions ?? []).join('\n'),
    required: v.required === true,
    min: v.min === undefined ? '' : String(v.min),
    max: v.max === undefined ? '' : String(v.max),
    regex: v.regex ?? '',
    functionKey: attribute?.functionKey ?? '',
  }
}

function toValidation(form: FormState): AttributeValidation | null {
  const validation: AttributeValidation = {}
  if (form.required) validation.required = true
  if (form.dataType === 'number' || form.dataType === 'date') {
    const parse = (value: string) => (form.dataType === 'number' ? Number(value) : value)
    if (form.min.trim() !== '') validation.min = parse(form.min.trim())
    if (form.max.trim() !== '') validation.max = parse(form.max.trim())
  }
  if (form.dataType === 'text' && form.regex.trim() !== '') validation.regex = form.regex.trim()
  return Object.keys(validation).length ? validation : null
}

/** The catalog row this form describes. Inputs that don't apply to the data type are dropped. */
function toInput(form: FormState): CreateAttributeInput {
  const unit = form.unit.trim()
  return {
    key: form.key.trim(),
    label: form.label.trim(),
    appliesTo: form.appliesTo,
    dataType: form.dataType,
    unit: form.dataType === 'number' && unit !== '' ? unit : null,
    enumOptions:
      form.dataType === 'enum'
        ? form.options
            .split('\n')
            .map((option) => option.trim())
            .filter(Boolean)
        : null,
    validation: toValidation(form),
    functionKey: form.functionKey === '' ? null : form.functionKey,
  }
}

/** Only the fields that differ, so an unchanged save sends (and audit-logs) nothing. Both
 * sides go through the same form conversion, so `{ required: false }` equals `null`. */
function changedFields(attribute: CatalogAttribute, form: FormState): UpdateAttributeInput {
  const before = toInput(formFrom(attribute))
  const after = toInput(form)
  const changes: UpdateAttributeInput = {}
  for (const field of EDITABLE_FIELDS) {
    if (JSON.stringify(before[field]) !== JSON.stringify(after[field])) {
      Object.assign(changes, { [field]: after[field] })
    }
  }
  return changes
}

function dataTypeHelp(appliesTo: AttributeAppliesTo, inUse: boolean): string | undefined {
  if (inUse) return 'Locked: values have been recorded. To change it, deactivate this and add a new one.'
  if (appliesTo === 'kpi') return 'KPIs are always numbers.'
  return undefined
}

/**
 * Add a new catalog row (`attribute` null) or edit an existing one. On edit, `key` and
 * "applies to" are fixed, and the data type is locked once values have been recorded.
 */
export function AttributeFormDialog({ attribute, ...props }: AdminDialogProps & { attribute: CatalogAttribute | null }) {
  const api = useApi()
  const { reference } = useReferenceData()
  const [form, setForm] = useState<FormState>(() => formFrom(attribute))
  const isEdit = attribute !== null
  const inUse = attribute?.inUse ?? false

  const update = (changes: Partial<FormState>) => setForm((current) => ({ ...current, ...changes }))
  const setLabel = (label: string) => update(form.keyEdited ? { label } : { label, key: suggestKey(label) })
  // A KPI is always a number (`kpi_record` only stores numbers), so picking KPI fixes it.
  const setAppliesTo = (appliesTo: AttributeAppliesTo) =>
    update(appliesTo === 'kpi' ? { appliesTo, dataType: 'number' } : { appliesTo })

  // Active functions, plus the current one if it has since been deactivated.
  const functions = (reference?.functions ?? []).filter((f) => f.active || f.key === form.functionKey)
  const options = toInput(form).enumOptions
  const canSubmit =
    form.label.trim() !== '' && form.key.trim() !== '' && (form.dataType !== 'enum' || (options?.length ?? 0) > 0)
  const isRange = form.dataType === 'number' || form.dataType === 'date'

  const submit = async () => {
    if (!isEdit) {
      const result = await api.createAttribute(toInput(form))
      return result.status === 'ok' ? null : result.message
    }
    const changes = changedFields(attribute, form)
    if (Object.keys(changes).length === 0) return null
    const result = await api.updateAttribute(attribute.id, changes)
    return result.status === 'ok' ? null : result.message
  }

  return (
    <AdminDialogFrame
      {...props}
      title={isEdit ? `Edit ${attribute.label}` : 'Add metric or field'}
      submitLabel={isEdit ? 'Save' : 'Add'}
      canSubmit={canSubmit}
      submit={submit}
      maxWidth="sm"
    >
      <TextField
        select
        required
        label="Applies to"
        value={form.appliesTo}
        onChange={(e) => setAppliesTo(e.target.value as AttributeAppliesTo)}
        disabled={isEdit}
        helperText={isEdit ? "Can't change after it is created." : 'A KPI is tracked over time; a field holds one value.'}
      >
        {(Object.keys(APPLIES_TO_LABELS) as AttributeAppliesTo[]).map((value) => (
          <MenuItem key={value} value={value}>
            {APPLIES_TO_LABELS[value]}
          </MenuItem>
        ))}
      </TextField>
      <TextField required autoFocus label="Label" value={form.label} onChange={(e) => setLabel(e.target.value)} />
      <TextField
        required
        label="Key"
        value={form.key}
        onChange={(e) => update({ key: e.target.value, keyEdited: true })}
        disabled={isEdit}
        helperText="How code and reports refer to it. Lowercase letters, digits and _. Can't change later."
      />
      <TextField
        select
        required
        label="Data type"
        value={form.dataType}
        onChange={(e) => update({ dataType: e.target.value as AttributeDataType })}
        disabled={form.appliesTo === 'kpi' || inUse}
        helperText={dataTypeHelp(form.appliesTo, inUse)}
      >
        {(Object.keys(DATA_TYPE_LABELS) as AttributeDataType[]).map((value) => (
          <MenuItem key={value} value={value}>
            {DATA_TYPE_LABELS[value]}
          </MenuItem>
        ))}
      </TextField>
      {form.dataType === 'number' && (
        <TextField
          label="Unit"
          value={form.unit}
          onChange={(e) => update({ unit: e.target.value })}
          helperText='Optional, e.g. "count" or "AUD".'
        />
      )}
      {form.dataType === 'enum' && (
        <TextField
          required
          multiline
          minRows={3}
          label="Options"
          value={form.options}
          onChange={(e) => update({ options: e.target.value })}
          helperText={inUse ? 'One per line. An option someone has chosen can’t be removed.' : 'One per line.'}
        />
      )}
      {isRange && (
        <>
          <TextField
            type={form.dataType}
            label="Minimum"
            value={form.min}
            onChange={(e) => update({ min: e.target.value })}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            type={form.dataType}
            label="Maximum"
            value={form.max}
            onChange={(e) => update({ max: e.target.value })}
            slotProps={{ inputLabel: { shrink: true } }}
          />
        </>
      )}
      {form.dataType === 'text' && (
        <TextField
          label="Format (regular expression)"
          value={form.regex}
          onChange={(e) => update({ regex: e.target.value })}
          helperText="Optional. A value must match it in full."
        />
      )}
      <FormControlLabel
        control={<Checkbox checked={form.required} onChange={(e) => update({ required: e.target.checked })} />}
        label="Required"
      />
      <TextField
        select
        label="Function"
        value={form.functionKey}
        onChange={(e) => update({ functionKey: e.target.value })}
        helperText="Limit it to one function, or leave it for every function."
      >
        <MenuItem value="">All functions</MenuItem>
        {functions.map((f) => (
          <MenuItem key={f.key} value={f.key}>
            {f.label}
          </MenuItem>
        ))}
      </TextField>
      {isEdit && (
        <Typography variant="body2" color="text.secondary">
          New rules apply to values recorded from now on. Values already recorded are not changed.
        </Typography>
      )}
    </AdminDialogFrame>
  )
}

/** Deactivate (the soft delete) or bring a deactivated attribute back. */
export function SetAttributeActiveDialog({
  attribute,
  makeActive,
  ...props
}: AdminDialogProps & { attribute: CatalogAttribute; makeActive: boolean }) {
  const api = useApi()
  const action = makeActive ? 'Reactivate' : 'Deactivate'

  const submit = async () => {
    const result = await api.updateAttribute(attribute.id, { active: makeActive })
    return result.status === 'ok' ? null : result.message
  }

  return (
    <AdminDialogFrame {...props} title={`${action} ${attribute.label}`} submitLabel={action} canSubmit submit={submit}>
      <Typography>
        {makeActive
          ? 'It can take new values again.'
          : 'Recorded values are kept and still count in reports and history. It stops taking new values. You can reactivate it later.'}
      </Typography>
    </AdminDialogFrame>
  )
}
