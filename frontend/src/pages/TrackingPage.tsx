import { PlannedPage } from '../components/PlannedPage'

/** Tracking (spec §2A.6). Placeholder: the KPI catalog is still a spec TODO (§4.3). */
export function TrackingPage() {
  return (
    <PlannedPage
      title="Tracking"
      intro="Enter and view KPI numbers. What you track depends on your function."
      willDo={[
        'Enter and view your own numbers.',
        'Pick a person below you and enter or view their numbers, if your position allows it.',
        'Switch between your functions, if you hold more than one.',
      ]}
    />
  )
}
