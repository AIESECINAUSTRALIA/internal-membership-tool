/**
 * The Manage membership dialogs when the backend fails (DEV-0043).
 *
 * The mock never failed, so the dialogs only ever saw success. The real backend can
 * be unreachable or answer 401/404/500 while a dialog loads a membership's details:
 * the person must see an error, not "Loading…" forever.
 *
 * The dialogs are rendered directly: in routes.test.tsx the per-row menu that opens
 * them lives inside the Data Grid, which jsdom cannot lay out.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { AppProviders } from '../AppProviders'
import { createMockApi } from '../api/mock/mockApi'
import type { Api, MemberSummaryRow } from '../api/types'
import { ManageMembershipDialog } from '../features/membership/ManageMembershipDialog'
import { ManageMembershipPanel } from '../features/membership/ManageMembershipPanel'

const LOAD_ERROR = 'Could not load this membership. Close and try again.'

const row: MemberSummaryRow = {
  personId: '1',
  firstName: 'Ada',
  lastName: 'Lovelace',
  lc: { id: '3', name: 'USYD', type: 'lc', state: 'NSW', active: true },
  roles: [
    {
      membershipId: '42',
      position: {
        key: 'member',
        label: 'Member',
        level: 'lc',
        rank: 1,
        canAddSameRank: false,
        presidential: false,
        homeChartScope: 'team',
        holdsTeam: true,
      },
      function: { key: 'ogv', label: 'oGV' },
      teamId: null,
    },
  ],
}

/** The mock, except loading a membership's details always fails. */
function failingDetailApi(): Api {
  return {
    ...createMockApi({ latencyMs: 0 }),
    getMembershipDetail: () => Promise.reject(new Error('GET /api/v1/members/42 → 500')),
  }
}

function renderWithApi(api: Api, ui: React.ReactNode) {
  render(
    <MemoryRouter>
      <AppProviders api={api}>{ui}</AppProviders>
    </MemoryRouter>,
  )
}

describe('when membership details fail to load', () => {
  it.each(['extend', 'move'] as const)('the %s dialog shows an error instead of loading forever', async (kind) => {
    renderWithApi(
      failingDetailApi(),
      <ManageMembershipDialog kind={kind} row={row} eligibleRoleIds={['42']} onClose={() => {}} onDone={() => {}} />,
    )

    expect(await screen.findByText(LOAD_ERROR)).toBeInTheDocument()
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument()
  })

  it('the Manage membership panel shows an error instead of loading forever', async () => {
    renderWithApi(
      failingDetailApi(),
      <ManageMembershipPanel
        row={row}
        teamEligibleRoleIds={['42']}
        termEligibleRoleIds={['42']}
        canAddFunction={false}
        onClose={() => {}}
        onDone={() => {}}
        onAddFunction={() => {}}
      />,
    )

    expect(await screen.findByText(LOAD_ERROR)).toBeInTheDocument()
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument()
  })
})
