/**
 * The "Positions & functions" screen (spec §1.5, §2A.2, DEV-0049): the mock server's
 * rules first (same rules as the backend), then the screen rendered for real, same
 * approach as `adminAttributes.test.tsx`.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import App from '../App'
import { AppProviders } from '../AppProviders'
import { createMockApi } from '../api/mock/mockApi'
import type { PersonaKey } from '../api/mock/seed'

async function apiAs(persona: PersonaKey) {
  const api = createMockApi({ persona, latencyMs: 0 })
  await api.signIn()
  return api
}

type TestApi = Awaited<ReturnType<typeof apiAs>>

async function positionByKey(api: TestApi, key: string) {
  const row = (await api.listPositionsAdmin()).find((p) => p.key === key)
  if (!row) throw new Error(`No position ${key}`)
  return row
}

async function functionByKey(api: TestApi, key: string) {
  const row = (await api.listFunctionsAdmin()).find((f) => f.key === key)
  if (!row) throw new Error(`No function ${key}`)
  return row
}

const ALL_MEMBERS = { search: '', sort: null, page: 0, pageSize: 500, lcId: null }

describe('mock API: positions', () => {
  it('lets an MCVP add a position ranked below them', async () => {
    const api = await apiAs('mcvp')

    const result = await api.createPosition({ label: 'Coordinator', level: 'lc', rank: 2 })

    expect(result.status).toBe('ok')
    const created = await positionByKey(api, 'coordinator')
    expect(created).toMatchObject({ label: 'Coordinator', level: 'lc', rank: 2, active: true })
  })

  it('refuses to let an MCVP rename the MCP position (hierarchy rule)', async () => {
    const api = await apiAs('mcvp')
    const mcp = await positionByKey(api, 'mcp')

    const result = await api.updatePosition(mcp.id, { label: 'Boss' })

    expect(result.status).toBe('rejected')
  })

  it('refuses to let an MCVP give a position their own rank', async () => {
    const api = await apiAs('mcvp')
    const lcp = await positionByKey(api, 'lcp')

    const result = await api.updatePosition(lcp.id, { rank: 6 })

    expect(result.status).toBe('rejected')
  })

  it('refuses to deactivate a position that gives admin access', async () => {
    const api = await apiAs('mcvp')
    const mcd = await positionByKey(api, 'mcd')

    const result = await api.updatePosition(mcd.id, { active: false })

    expect(result.status).toBe('rejected')
  })

  it('refuses a name that differs from an existing one only by case', async () => {
    const api = await apiAs('mcvp')

    const result = await api.createPosition({ label: 'member', level: 'lc', rank: 1 })

    expect(result.status).toBe('rejected')
  })

  it('gives a new key a _2 suffix when the plain key is taken', async () => {
    const api = await apiAs('mcvp')

    // "Member!" isn't the same name as "Member", but it makes the same key.
    await api.createPosition({ label: 'Member!', level: 'lc', rank: 1 })

    expect((await positionByKey(api, 'member_2')).label).toBe('Member!')
  })

  it('never gives a new position a key that the permission rules use', async () => {
    const api = await apiAs('mcvp')

    // No "admin" position exists yet, but its key carries admin permissions.
    await api.createPosition({ label: 'Admin', level: 'mc', rank: 1 })

    const created = (await api.listPositionsAdmin()).find((p) => p.label === 'Admin')
    expect(created?.key).toBe('admin_2')
  })

  it('stops offering a deactivated position, but existing memberships still show it', async () => {
    const api = await apiAs('mcvp')
    const tl = await positionByKey(api, 'team_leader')

    await api.updatePosition(tl.id, { active: false })

    const reference = await api.getReferenceData()
    expect(reference.positions.map((p) => p.key)).not.toContain('team_leader')
    const members = await api.listMembers(ALL_MEMBERS)
    const roles = members.rows.flatMap((row) => row.roles)
    expect(roles.some((role) => role.position.key === 'team_leader')).toBe(true)
  })
})

describe('mock API: functions', () => {
  it('offers a new function in the reference data', async () => {
    const api = await apiAs('mcvp')

    await api.createFunction({ label: 'Partnerships' })

    const reference = await api.getReferenceData()
    expect(reference.functions.find((f) => f.key === 'partnerships')).toMatchObject({ active: true })
  })

  it('marks a deactivated function inactive in the reference data', async () => {
    const api = await apiAs('mcvp')
    const ogv = await functionByKey(api, 'ogv')

    await api.updateFunction(ogv.id, { active: false })

    const reference = await api.getReferenceData()
    expect(reference.functions.find((f) => f.key === 'ogv')?.active).toBe(false)
  })

  it('refuses a blank name', async () => {
    const api = await apiAs('mcvp')

    const result = await api.createFunction({ label: '   ' })

    expect(result.status).toBe('rejected')
  })
})

async function renderScreen(persona: PersonaKey = 'mcvp') {
  const api = await apiAs(persona)
  const referenceSpy = vi.spyOn(api, 'getReferenceData')
  render(
    <MemoryRouter initialEntries={['/admin/positions-functions']}>
      <AppProviders api={api}>
        <App />
      </AppProviders>
    </MemoryRouter>,
  )
  await screen.findByRole('table', { name: 'Positions' })
  return { api, referenceSpy }
}

async function choose(dialog: HTMLElement, field: string, option: string) {
  fireEvent.mouseDown(within(dialog).getByRole('combobox', { name: field }))
  fireEvent.click(await screen.findByRole('option', { name: option }))
}

describe('Positions & functions screen', () => {
  it('only offers actions on positions ranked below the signed-in MCVP', async () => {
    await renderScreen('mcvp')

    expect(await screen.findByRole('button', { name: 'Actions for LC President (LCP)' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Actions for MC President (MCP)' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Actions for MC Vice President (MCVP)' })).not.toBeInTheDocument()
  })

  it('says that a new position has no permissions yet', async () => {
    await renderScreen('mcvp')

    expect(screen.getByText(/New positions have no permissions/)).toBeInTheDocument()
  })

  it('needs a name, a level and a rank before a position can be added', async () => {
    await renderScreen('mcvp')
    fireEvent.click(screen.getByRole('button', { name: 'Add position' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add position' })
    const submit = within(dialog).getByRole('button', { name: 'Add position' })

    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Name' }), { target: { value: 'Coordinator' } })
    expect(submit).toBeDisabled()
    await choose(dialog, 'Level', 'LC')
    expect(submit).toBeDisabled()
    fireEvent.change(within(dialog).getByRole('spinbutton', { name: 'Rank' }), { target: { value: '2' } })

    expect(submit).toBeEnabled()
  })

  it('refreshes the shared reference data after a change, so Add member sees it', async () => {
    const { referenceSpy } = await renderScreen('mcvp')
    const callsBefore = referenceSpy.mock.calls.length

    fireEvent.click(screen.getByRole('button', { name: 'Add function' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add function' })
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Name' }), { target: { value: 'Partnerships' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add function' }))

    await waitFor(() => expect(referenceSpy.mock.calls.length).toBeGreaterThan(callsBefore))
  })
})
