/**
 * The People and Memberships screens (spec §1.5, §2A.2, DEV-47): their rules on the mock
 * server (the same rules as the backend's `repositories/admin_people.py`), then the
 * screens rendered for real, same approach as `adminAttributes.test.tsx`.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import dayjs from 'dayjs'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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

describe('EXPA link rules on the server', () => {
  const UNLINKED = 'gen-0@aiesec.example' // a seeded person who has never signed in

  it('shows who is linked, and unlinking clears it', async () => {
    const api = await apiAs('mcvp')
    expect((await personByEmail(api, SAM)).expaLinked).toBe(true)
    expect((await personByEmail(api, UNLINKED)).expaLinked).toBe(false)

    expect((await api.unlinkExpa((await personByEmail(api, SAM)).id)).status).toBe('ok')
    expect((await personByEmail(api, SAM)).expaLinked).toBe(false)
  })

  it('refuses to unlink someone who is not linked, yourself, or someone who outranks you', async () => {
    const api = await apiAs('mcvp')
    const unlinked = await personByEmail(api, UNLINKED)
    expect(await api.unlinkExpa(unlinked.id)).toEqual({ status: 'rejected', message: "This person isn't linked to EXPA." })
    const me = await personByEmail(api, RILEY)
    expect(await api.unlinkExpa(me.id)).toEqual({ status: 'rejected', message: "You can't do this to your own record." })
    const mcp = await personByEmail(api, MCP)
    expect((await api.unlinkExpa(mcp.id)).status).toBe('rejected')
    expect((await personByEmail(api, MCP)).expaLinked).toBe(true)
  })

  it('refuses someone who no longer exists, and someone without `manage` on `person`', async () => {
    const api = await apiAs('mcvp')
    expect((await api.unlinkExpa('p-nobody')).status).toBe('rejected')
    const lcvp = await apiAs('lcvp')
    expect((await lcvp.unlinkExpa('p-sam')).status).toBe('rejected')
  })

  it('a person added on the console starts not linked', async () => {
    const api = await apiAs('mcvp')
    await api.createPerson({ firstName: 'Nina', lastName: 'New', email: 'nina@aiesec.example' })
    expect((await personByEmail(api, 'nina@aiesec.example')).expaLinked).toBe(false)
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

  it('refuses a new membership while one in another LC has not started and overlaps', async () => {
    const api = await apiAs('mcvp')
    expect((await api.assignMembership('p-sam', assign())).status).toBe('ok') // MU, starts in 5 days
    const result = await api.assignMembership('p-sam', assign({ lcId: 'lc-unsw', startDate: inDays(2) }))
    expect(result.status === 'rejected' && result.message).toContain("membership in MU starts on")
    expect(result.status === 'rejected' && result.message).toContain(dayjs(inDays(5)).format('DD MMM YYYY'))
    // Not overlapping (the new one ends before MU starts) is still fine.
    expect((await api.assignMembership('p-sam', assign({ lcId: 'lc-unsw', startDate: inDays(1), endDate: inDays(3) }))).status).toBe('ok')
  })

  it('Add member refuses the same case with a vague message', async () => {
    const api = await apiAs('mcvp')
    expect((await api.assignMembership('p-sam', assign())).status).toBe('ok')
    const result = await api.addMember({
      email: SAM,
      lcId: 'lc-unsw',
      positionKey: 'lcvp',
      functionKey: 'bnm',
      startDate: inDays(2),
      endDate: inDays(100),
      confirmedExisting: true,
    })
    expect(result).toEqual({
      status: 'rejected',
      message: 'This person already has a membership coming up elsewhere. Contact your MC.',
    })
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

  /** The table is paged, so narrow it to one person first. */
  const searchFor = (text: string) => fireEvent.change(screen.getByLabelText('Search people'), { target: { value: text } })

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

  it('has an EXPA column that says Linked or Not linked in words', async () => {
    await renderAt('/admin/people')
    const table = await peopleTable()
    expect(within(table).getByRole('columnheader', { name: 'EXPA' })).toBeInTheDocument()
    searchFor('sam@')
    const linked = (await within(table).findByText(SAM)).closest('tr')!
    expect(within(linked).getByText('Linked')).toBeInTheDocument()
    searchFor('gen-0@')
    const unlinked = (await within(table).findByText('gen-0@aiesec.example')).closest('tr')!
    expect(within(unlinked).getByText('Not linked')).toBeInTheDocument()
  })

  it('offers Unlink EXPA only for linked people', async () => {
    await renderAt('/admin/people')
    const table = await peopleTable()
    await chooseAction(table, SAM, 'Unlink EXPA') // finds the item, so it is there
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    searchFor('gen-0@')
    const row = (await within(table).findByText('gen-0@aiesec.example')).closest('tr')!
    fireEvent.click(within(row).getByRole('button', { name: /^Actions for/ }))
    await screen.findByRole('menuitem', { name: 'Edit' })
    expect(screen.queryByRole('menuitem', { name: 'Unlink EXPA' })).not.toBeInTheDocument()
  })

  it('unlinks after explaining the email order, then shows Not linked', async () => {
    const api = await renderAt('/admin/people')
    const unlinkExpa = vi.spyOn(api, 'unlinkExpa')
    await chooseAction(await peopleTable(), SAM, 'Unlink EXPA')

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/correct the email first, then unlink/)).toBeInTheDocument()
    expect(within(dialog).getByText(/signed out/)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Unlink' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(unlinkExpa).toHaveBeenCalledWith('p-sam')
    const row = (await within(await peopleTable()).findByText(SAM)).closest('tr')!
    await within(row).findByText('Not linked')
  })

  it('tells you, when editing a linked person, that the email does not change who signs in', async () => {
    await renderAt('/admin/people')
    await chooseAction(await peopleTable(), SAM, 'Edit')
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/linked to an EXPA account/)).toBeInTheDocument()
    expect(within(dialog).getByText(/use Unlink EXPA/)).toBeInTheDocument()
  })

  it('does not say that when editing a person who is not linked', async () => {
    await renderAt('/admin/people')
    const table = await peopleTable()
    searchFor('gen-0@')
    await chooseAction(table, 'gen-0@aiesec.example', 'Edit')
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByText(/linked to an EXPA account/)).not.toBeInTheDocument()
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

  it('edit person sends only changed fields', async () => {
    const api = await renderAt('/admin/people')
    const updatePerson = vi.spyOn(api, 'updatePerson')
    await chooseAction(await peopleTable(), SAM, 'Edit')
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText(/First name/), { target: { value: 'Samantha' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(updatePerson).toHaveBeenCalledTimes(1)
    expect(updatePerson.mock.calls[0][1]).toEqual({ firstName: 'Samantha' })
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
