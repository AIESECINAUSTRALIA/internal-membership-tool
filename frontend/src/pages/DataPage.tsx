import { PlannedPage } from '../components/PlannedPage'

/** Data (spec §2A.7). Placeholder: needs the KPI catalog (§4.3) and the dashboard design (§6). */
export function DataPage() {
  return (
    <PlannedPage
      title="Data"
      intro="Summaries and graphs for your LC, function or team."
      willDo={[
        'Read summary tables for LCs, functions, teams and members.',
        'Choose your own start and end dates.',
        'Switch between graph types and build your own graphs.',
        'See an Australia-wide summary.',
      ]}
    />
  )
}
