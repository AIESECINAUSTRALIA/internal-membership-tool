/**
 * The attribute catalog's definition rules (§4.2), as the mock server applies them.
 * A copy of `_check_definition` in `backend/app/repositories/attribute.py`, with the
 * same messages, so the screen behaves the same once the real backend is swapped in.
 * Delete this with the rest of `api/mock/`.
 */
import dayjs from 'dayjs'

import type { AttributeDataType, AttributeValidation, CreateAttributeInput } from '../types'

/** `attribute.key` is what code refers to, so it stays machine-friendly. */
export const KEY_PATTERN = /^[a-z][a-z0-9_]*$/

/** Which validation rules mean something for each data type. */
const ALLOWED_RULES: Record<AttributeDataType, readonly (keyof AttributeValidation)[]> = {
  text: ['required', 'regex'],
  number: ['required', 'min', 'max'],
  date: ['required', 'min', 'max'],
  boolean: ['required'],
  enum: ['required'],
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

function boundProblem(dataType: AttributeDataType, rule: string, bound: unknown): string | null {
  if (dataType === 'date') {
    const ok = typeof bound === 'string' && ISO_DATE.test(bound) && dayjs(bound).isValid()
    return ok ? null : `${rule} must be an ISO date (YYYY-MM-DD)`
  }
  return typeof bound === 'number' && Number.isFinite(bound) ? null : `${rule} must be a number`
}

function validationProblem(dataType: AttributeDataType, validation: AttributeValidation | null): string | null {
  if (validation === null) return null

  const unknown = Object.keys(validation).filter((rule) => !ALLOWED_RULES[dataType].includes(rule as keyof AttributeValidation))
  if (unknown.length) return `${unknown.sort().join(', ')} can't be used on a ${dataType} attribute`
  if (validation.required !== undefined && typeof validation.required !== 'boolean') {
    return 'required must be true or false'
  }

  const { min, max, regex } = validation
  for (const [rule, bound] of [['min', min], ['max', max]] as const) {
    if (bound === undefined) continue
    const problem = boundProblem(dataType, rule, bound)
    if (problem) return problem
  }
  // ISO dates compare correctly as plain strings, numbers as numbers.
  if (min !== undefined && max !== undefined && min > max) return "min can't be above max"

  if (regex !== undefined) {
    try {
      new RegExp(regex)
    } catch {
      return 'regex is not a valid pattern'
    }
  }
  return null
}

/** Why this definition can't be saved, or null when it can. `key` is checked separately
 * because it is only set on create. */
export function definitionProblem(
  def: Pick<CreateAttributeInput, 'label' | 'appliesTo' | 'dataType' | 'enumOptions' | 'validation'>,
): string | null {
  if (!def.label.trim()) return 'Enter a label'
  // kpi_record only has a number column, so a KPI must be a number.
  if (def.appliesTo === 'kpi' && def.dataType !== 'number') return 'A KPI must have data type number'

  if (def.dataType !== 'enum') {
    if (def.enumOptions !== null) return 'Only enum attributes can have options'
  } else {
    if (!def.enumOptions?.length || def.enumOptions.some((option) => !option.trim())) {
      return 'An enum attribute needs at least one non-blank option'
    }
    if (new Set(def.enumOptions).size !== def.enumOptions.length) return 'Enum options must be unique'
  }

  return validationProblem(def.dataType, def.validation)
}
