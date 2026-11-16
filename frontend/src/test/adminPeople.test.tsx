/**
 * The People and Memberships screens (spec §1.5, §2A.2, DEV-47): their rules on the mock
 * server (the same rules as the backend's `repositories/admin_people.py`), then the
 * screens rendered for real, same approach as `adminAttributes.test.tsx`.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import dayjs from 'dayjs'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import App from '../App'
import { AppProviders } from '../AppProviders'
import { createMockApi } from '../api/mock/mockApi'
import type { PersonaKey } from '../api/mock/seed'
import type { Api } from '../api/types'

const TODAY = dayjs().format('YYYY-MM-DD')
const YESTERDAY = dayjs().subtract(1, 'day').format('YYYY-MM-DD')
const inDays = (n: number) => dayjs().add(n, 'day').format('YYYY-MM-DD')

async function apiAs(persona: PersonaKey) {
  const api = createMockApi({ persona, latencyMs: 0 })
  await api.signIn()
  return api
}

/** Seeded people are "Member 1", "Member 2", ... so look them up by their seed email. */
async function personByEmail(api: Api, email: string) {
  const row = (await api.listPeopleAdmin({ search: email, page: 0, pageSize: 10 })).rows.find((r) => r.email === email)
  if (!row) throw new Error(`No person ${email}`)
  return row
}

const SAM = 'sam@aiesec.example' // Member, USYD, oGV, in a team
const MORGAN = 'morgan@aiesec.example' // LCP, USYD
const MCP = 'mcp@aiesec.example'
const RILEY = 'riley@aiesec.example' // the MCVP persona

beforeEach(() => sessionStorage.clear())

describe('people rules on the server', () => {
  it('refuses everything to someone without `manage` on `person` / `membership`', async () => {
    const api = await apiAs('lcvp')
    expect((await api.listPeopleAdmin({ search: '', page: 0, pageSize: 10 })).total).toBe(0)
    expect((await api.createPerson({ firstName: 'A', lastName: 'B', email: 'a@b.example' })).status).toBe('rejected')
    expect((await api.deactivatePerson('p-sam')).status).toBe('rejected')
    expect(await api.listPersonMemberships('p-sam')).toEqual([])
    expect((await api.endMembership('m-1', TODAY)).status).toBe('rejected')
  })

  it('adds a person, and refuses a duplicate email whatever its case', async () => {
    const api = await apiAs('mcvp')
    expect((await api.createPerson({ firstName: ' Nina ', lastName: 'New', email: 'Nina@AIESEC.example' })).status).toBe('ok')
    const nina = await personByEmail(api, 'nina@aiesec.example')
    expect(nina).toMatchObject({ firstName: 'Nina', active: false, status: 'active' })
    expect(await api.createPerson({ firstName: 'A', lastName: 'B', email: 'NINA@aiesec.example' })).toEqual({
      status: 'rejected',
      message: 'Someone already has that email address.',
    })
  })

  it('edits all or nothing', async () => {
    const api = await apiAs('mcvp')
    const sam = await personByEmail(api, SAM)
    expect((await api.updatePerson(sam.id, { lastName: 'Halfway', email: MORGAN })).status).toBe('rejected')
    expect((await personByEmail(api, SAM)).lastName).toBe(sam.lastName)
    expect((await api.updatePerson(sam.id, { lastName: 'Renamed' })).status).toBe('ok')
    expect((await personByEmail(api, SAM)).lastName).toBe('Renamed')
  })

  it('never lets you edit or deactivate someone who outranks you (their email is their sign-in)', async () => {
    const api = await apiAs('mcvp')
    const mcp = await personByEmail(api, MCP)
    expect((await api.updatePerson(mcp.id, { email: 'takeover@aiesec.example' })).status).toBe('rejected')
    expect((await api.deactivatePerson(mcp.id)).status).toBe('rejected')
    const me = await personByEmail(api, RILEY)
    expect(await api.deactivatePerson(me.id)).toEqual({ status: 'rejected', message: "You can't do this to your own record." })
  })

  it('deactivates without deleting: current memberships end yesterday, and they lose access', async () => {
    const api = await apiAs('mcvp')
    const sam = await personByEmail(api, SAM)
    const before = await api.listPersonMemberships(sam.id)
    expect((await api.deactivatePerson(sam.id)).status).toBe('ok')

    const after = await api.listPersonMemberships(sam.id)
    expect(after.map((m) => m.id)).toEqual(before.map((m) => m.id)) // nothing removed
    expect(after.every((m) => !m.current)).toBe(true)
    expect(after.find((m) => m.id === before.find((b) => b.current)!.id)!.endDate).toBe(YESTERDAY)
    expect(await personByEmail(api, SAM)).toMatchObject({ status: 'inactive', active: false })

    expect((await api.deactivatePerson(sam.id)).status).toBe('rejected') // already
    expect((await api.reactivatePerson(sam.id)).status).toBe('ok')
    expect((await personByEmail(api, SAM)).status).toBe('active')
  })

  it('Add member in the main app cannot bring a deactivated person back', async () => {
    const api = await apiAs('mcvp')
    expect((await api.deactivatePerson('p-sam')).status).toBe('ok')
    const result = await api.addMember({
      email: SAM,
      lcId: 'lc-mu',
      positionKey: 'lcvp',
      functionKey: 'bnm',
      startDate: inDays(1),
      endDate: inDays(60),
      confirmedExisting: true,
    })
    expect(result).toEqual({ status: 'rejected', message: "This person can't be added. Contact your MC." })
  })
})

describe('membership rules on the server', () => {
  const assign = (overrides: Record<string, unknown> = {}) => ({
    lcId: 'lc-mu',
    positionKey: 'member',
    functionKey: 'bnm',
    startDate: inDays(5),
    endDate: inDays(90),
    ...overrides,
  })

  it('assigns in any LC; a new LC is a transfer that ends the old one the day before', async () => {
    const api = await apiAs('mcvp')
    const sam = await personByEmail(api, SAM)
    expect((await api.assignMembership(sam.id, assign())).status).toBe('ok')
    const rows = await api.listPersonMemberships(sam.id)
    const usyd = rows.find((m) => m.lc.id === 'lc-usyd' && m.current)!
    expect(usyd.endDate).toBe(inDays(4))
    expect(rows.some((m) => m.lc.id === 'lc-mu' && m.startDate === inDays(5))).toBe(true)
  })

  it.each([
    ['an MC position in an LC (§3.6)', assign({ positionKey: 'mcd' }), "can't be used in an LC"],
    ['an LC position in the MC (§3.6)', assign({ lcId: 'lc-mc' }), "can't be used in the MC"],
    ['a position at or above your own (§3.4)', assign({ lcId: 'lc-mc', positionKey: 'mcvp', functionKey: 'tm' }), 'at or above your own'],
    ['an end before the start', assign({ endDate: inDays(1) }), 'end date'],
    ['the same function twice in one LC', assign({ lcId: 'lc-usyd', functionKey: 'ogv' }), 'already holds that function'],
  ])('refuses %s', async (_label, input, message) => {
    const api = await apiAs('mcvp')
    const result = await api.assignMembership('p-sam', input)
    expect(result.status).toBe('rejected')
    expect(result.status === 'rejected' && result.message).toContain(message)
  })

  it('refuses to assign yourself or a deactivated person', async () => {
    const api = await apiAs('mcvp')
    expect((await api.assignMembership('p-riley', assign({ lcId: 'lc-mc', positionKey: 'mcd', functionKey: 'tm' }))).status).toBe('rejected')
    await api.deactivatePerson('p-sam')
    const result = await api.assignMembership('p-sam', assign())
    expect(result.status === 'rejected' && result.message).toContain('Reactivate')
  })

  it('corrects a position, but not a function once the membership has a team', async () => {
    const api = await apiAs('mcvp')
    const current = (await api.listPersonMemberships('p-sam')).find((m) => m.current)!
    expect((await api.correctMembership(current.id, { positionKey: 'lcvp' })).status).toBe('ok')
    expect((await api.listPersonMemberships('p-sam')).find((m) => m.id === current.id)!.position?.key).toBe('lcvp')

    const refused = await api.correctMembership(current.id, { functionKey: 'bnm' })
    expect(refused.status === 'rejected' && refused.message).toContain('team')
  })

  it('ends a membership early, never later or before it began', async () => {
    const api = await apiAs('mcvp')
    const current = (await api.listPersonMemberships('p-sam')).find((m) => m.current)!
    expect((await api.endMembership(current.id, '1900-01-01')).status).toBe('rejected')
    expect((await api.endMembership(current.id, current.endDate!)).status).toBe('rejected')
    expect((await api.endMembership(current.id, TODAY)).status).toBe('ok')
  })
})

describe('the People and Memberships screens', () => {
  async function renderAt(path: string) {
    const api = await apiAs('mcvp')
    render(
      <MemoryRouter initialEntries={[path]}>
        <AppProviders api={api}>
          <App />
        </AppProviders>
      </MemoryRouter>,
    )
    return api
  }

  const peopleTable = () => screen.findByRole('table', { name: 'People' })

  async function chooseAction(table: HTMLElement, rowText: string, action: string) {
    const row = (await within(table).findByText(rowText)).closest('tr')!
    fireEvent.click(within(row).getByRole('button', { name: /^Actions for/ }))
    fireEvent.click(await screen.findByRole('menuitem', { name: action }))
  }

  it('deactivates someone after asking, and shows them as deactivated', async () => {
    await renderAt('/admin/people')
    await chooseAction(await peopleTable(), SAM, 'Deactivate')

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/Nothing is deleted/)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Deactivate' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const row = (await within(await peopleTable()).findByText(SAM)).closest('tr')!
    await within(row).findByText('Deactivated')
  })

  it('adds a person from the dialog', async () => {
    await renderAt('/admin/people')
    fireEvent.click(await screen.findByRole('button', { name: 'Add person' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText(/First name/), { target: { value: 'Nina' } })
    fireEvent.change(within(dialog).getByLabelText(/Last name/), { target: { value: 'New' } })
    fireEvent.change(within(dialog).getByLabelText(/AIESEC email/), { target: { value: 'nina@aiesec.example' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add person' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Search people'), { target: { value: 'nina' } })
    expect(await within(await peopleTable()).findByText('nina@aiesec.example')).toBeInTheDocument()
  })

  it('shows the server’s reason when an edit is refused', async () => {
    await renderAt('/admin/people')
    await chooseAction(await peopleTable(), SAM, 'Edit')
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText(/AIESEC email/), { target: { value: MORGAN } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))
    expect(await within(dialog).findByText('Someone already has that email address.')).toBeInTheDocument()
  })

  it('opens a person’s memberships from People, and ends one', async () => {
    await renderAt('/admin/people')
    await chooseAction(await peopleTable(), SAM, 'Manage memberships')

    expect(await screen.findByRole('heading', { name: 'Memberships', level: 1 })).toBeInTheDocument()
    const table = await screen.findByRole('table')
    const current = (await within(table).findByText('Current')).closest('tr')!
    fireEvent.click(within(current).getByRole('button', { name: /^Actions for/ }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'End' }))

    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'End membership' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    // Ending today keeps it current until tonight: the end date now shows today.
    expect(await within(table).findByText(dayjs().format('DD/MM/YYYY'))).toBeInTheDocument()
  })

  it('asks you to choose a person first', async () => {
    await renderAt('/admin/memberships')
    expect(await screen.findByText('Choose a person to see their memberships.')).toBeInTheDocument()
  })

  it('is hidden from, and refused to, someone without `manage` on `membership`', async () => {
    const api = await apiAs('lcvp')
    render(
      <MemoryRouter initialEntries={['/admin/memberships']}>
        <AppProviders api={api}>
          <App />
        </AppProviders>
      </MemoryRouter>,
    )
    expect(await screen.findByText(/don.t have access to the admin console/)).toBeInTheDocument()
  })
})
