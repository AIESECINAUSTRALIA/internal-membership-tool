import { ToggleButton, ToggleButtonGroup } from '@mui/material'

export interface ToggleOption<T extends string> {
  value: T
  label: string
  /** Falls back to `label` when omitted. */
  ariaLabel?: string
}

/** A row of exclusive toggle buttons (e.g. the Data page's scope tabs, Tracking's
 * function switcher), hidden entirely when there's only one option. */
export function OptionToggleGroup<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value: T | null
  options: ToggleOption<T>[]
  onChange: (v: T) => void
  ariaLabel: string
}) {
  if (options.length <= 1) return null
  return (
    <ToggleButtonGroup
      value={value}
      exclusive
      onChange={(_e, next) => {
        if (next) onChange(next)
      }}
      aria-label={ariaLabel}
      size="small"
    >
      {options.map((o) => (
        <ToggleButton key={o.value} value={o.value} aria-label={o.ariaLabel ?? o.label}>
          {o.label}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  )
}
