/**
 * The "Metrics & custom fields" screen (spec §1.5, §4.2): the attribute catalog's rules
 * on the mock server, then the screen itself rendered for real, same approach as
 * `adminRoutes.test.tsx`.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import App from '../App'
import { AppProviders } from '../AppProviders'
import { createMockApi } from '../api/mock/mockApi'
import type { PersonaKey } from '../api/mock/seed'
import type { CreateAttributeInput } from '../api/types'

const NEW_KPI: CreateAttributeInput = {
  key: 'cold_calls',
  label: 'Cold calls',
  appliesTo: 'kpi',
  dataType: 'number',
  unit: 'count',
  enumOptions: null,
  validation: { required: true, min: 0 },
  functionKey: null,
}

async function apiAs(persona: PersonaKey) {
  const api = createMockApi({ persona, latencyMs: 0 })
  await api.signIn()
  return api
}

async function attributeByKey(api: Awaited<ReturnType<typeof apiAs>>, key: string) {
  const row = (await api.listAttributes()).find((r) => r.key === key)
  if (!row) throw new Error(`No attribute ${key}`)
  return row
}

async function renderScreen(persona: PersonaKey = 'mcvp') {
  const api = await apiAs(persona)
  render(
    <MemoryRouter initialEntries={['/admin/attributes']}>
      <AppProviders api={api}>
        <App />
      </AppProviders>
    </MemoryRouter>,
  )
  return api
}

const table = () => screen.findByRole('table', { name: 'Metrics & custom fields' })
const rowOf = async (label: string) => (await within(await table()).findByText(label)).closest('tr')!

async function chooseAction(label: string, action: string) {
  fireEvent.click(within(await rowOf(label)).getByRole('button', { name: `Actions for ${label}` }))
  fireEvent.click(await screen.findByRole('menuitem', { name: action }))
}

async function choose(dialog: HTMLElement, field: RegExp, option: string) {
  fireEvent.mouseDown(within(dialog).getByRole('combobox', { name: field }))
  fireEvent.click(await screen.findByRole('option', { name: option }))
}

beforeEach(() => sessionStorage.clear())

describe('attribute catalog rules on the server', () => {
  it('refuses every change to someone without `manage` on `attribute`', async () => {
    const api = await apiAs('lcvp')
    expect(await api.listAttributes()).toEqual([])
    expect((await api.createAttribute(NEW_KPI)).status).toBe('rejected')
    expect((await api.updateAttribute('attr-ol-signups', { label: 'New' })).status).toBe('rejected')
  })

  it('creates a KPI that starts active and unused', async () => {
    const api = await apiAs('mcvp')
    expect((await api.createAttribute(NEW_KPI)).status).toBe('ok')
    expect(await attributeByKey(api, 'cold_calls')).toMatchObject({ active: true, inUse: false, unit: 'count' })
  })

  it.each([
    ['a taken key', { key: 'ol_signups' }],
    ['a badly formed key', { key: 'Has Spaces' }],
    ['a blank label', { label: '  ' }],
    ['a KPI that is not a number', { dataType: 'text', validation: null }],
    ['min above max', { validation: { min: 5, max: 1 } }],
    ['a regex rule on a number', { validation: { regex: '.*' } }],
    ['options on a non-enum', { enumOptions: ['A'] }],
    ['an enum with no options', { appliesTo: 'person', dataType: 'enum', validation: null }],
    ['duplicate options', { appliesTo: 'person', dataType: 'enum', validation: null, enumOptions: ['A', 'A'] }],
    ['an unparseable regex', { appliesTo: 'person', dataType: 'text', validation: { regex: '(' } }],
  ] as const)('rejects %s', async (_name, overrides) => {
    const api = await apiAs('mcvp')
    const input = { ...NEW_KPI, ...overrides } as CreateAttributeInput
    expect((await api.createAttribute(input)).status).toBe('rejected')
  })

  it('locks the data type once values exist, but not the label or validation', async () => {
    const api = await apiAs('mcvp')
    expect(await api.updateAttribute('attr-shirt-size', { dataType: 'text', enumOptions: null })).toMatchObject({
      status: 'rejected',
    })
    expect((await api.updateAttribute('attr-shirt-size', { label: 'T-shirt size' })).status).toBe('ok')
    expect((await api.updateAttribute('attr-shirt-size', { validation: { required: true } })).status).toBe('ok')
  })

  it('allows an unused custom field to change data type', async () => {
    const api = await apiAs('mcvp')
    expect((await api.updateAttribute('attr-dietary', { dataType: 'number' })).status).toBe('ok')
  })

  it('refuses to remove an enum option in use, but allows removing the unused ones', async () => {
    const api = await apiAs('mcvp')
    expect(await api.updateAttribute('attr-shirt-size', { enumOptions: ['S', 'L'] })).toMatchObject({
      status: 'rejected',
      message: expect.stringContaining('M'),
    })
    expect((await api.updateAttribute('attr-shirt-size', { enumOptions: ['M', 'XXXL'] })).status).toBe('ok')
    expect((await attributeByKey(api, 'shirt_size')).enumOptions).toEqual(['M', 'XXXL'])
  })

  it('keeps a deactivated attribute in the list, still in use, so it can be brought back', async () => {
    const api = await apiAs('mcvp')
    await api.updateAttribute('attr-ol-signups', { active: false })
    expect(await attributeByKey(api, 'ol_signups')).toMatchObject({ active: false, inUse: true })
    await api.updateAttribute('attr-ol-signups', { active: true })
    expect((await attributeByKey(api, 'ol_signups')).active).toBe(true)
  })
})

describe('Metrics & custom fields screen', () => {
  it('is one sidebar entry, not separate KPI and custom field screens', async () => {
    await renderScreen()
    expect(await screen.findByRole('heading', { name: 'Metrics & custom fields' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Admin console' })
    expect(within(nav).getByRole('link', { name: 'Metrics & custom fields' })).toBeInTheDocument()
    expect(within(nav).queryByRole('link', { name: 'KPIs' })).not.toBeInTheDocument()
    expect(within(nav).queryByRole('link', { name: 'Custom fields' })).not.toBeInTheDocument()
  })

  it('filters the one list by what the attribute applies to', async () => {
    await renderScreen()
    expect(await within(await table()).findByText('Shirt size')).toBeInTheDocument()
    expect(within(await table()).getByText('OL Signups')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'KPIs' }))
    expect(within(await table()).getByText('OL Signups')).toBeInTheDocument()
    expect(within(await table()).queryByText('Shirt size')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Person fields' }))
    expect(within(await table()).getByText('Shirt size')).toBeInTheDocument()
    expect(within(await table()).queryByText('OL Signups')).not.toBeInTheDocument()
  })

  it('adds a KPI, suggesting the key from the label and fixing the data type to number', async () => {
    const api = await renderScreen()
    fireEvent.click(await screen.findByRole('button', { name: 'Add' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add metric or field' })

    fireEvent.change(within(dialog).getByRole('textbox', { name: /Label/ }), { target: { value: 'Cold calls!' } })
    expect(within(dialog).getByRole('textbox', { name: /^Key/ })).toHaveValue('cold_calls')
    expect(within(dialog).getByRole('combobox', { name: /Data type/ })).toHaveAttribute('aria-disabled', 'true')
    fireEvent.change(within(dialog).getByRole('textbox', { name: /Unit/ }), { target: { value: 'count' } })
    fireEvent.change(within(dialog).getByRole('spinbutton', { name: /Minimum/ }), { target: { value: '0' } })
    await choose(dialog, /Function/, 'Business Development (BD)')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }))

    expect(await within(await table()).findByText('Cold calls!')).toBeInTheDocument()
    expect(await attributeByKey(api, 'cold_calls')).toMatchObject({
      appliesTo: 'kpi',
      dataType: 'number',
      unit: 'count',
      validation: { min: 0 },
      functionKey: 'bd',
    })
  })

  it('asks for options only on an enum custom field', async () => {
    const api = await renderScreen()
    fireEvent.click(await screen.findByRole('button', { name: 'Add' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add metric or field' })

    await choose(dialog, /Applies to/, 'Membership')
    fireEvent.change(within(dialog).getByRole('textbox', { name: /Label/ }), { target: { value: 'Hoodie' } })
    expect(within(dialog).queryByRole('textbox', { name: /Options/ })).not.toBeInTheDocument()
    await choose(dialog, /Data type/, 'Choice from a list')
    fireEvent.change(within(dialog).getByRole('textbox', { name: /Options/ }), { target: { value: 'S\n\n M \n' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }))

    await within(await table()).findByText('Hoodie')
    expect((await attributeByKey(api, 'hoodie')).enumOptions).toEqual(['S', 'M'])
  })

  it('shows the server rejection and keeps the dialog open', async () => {
    await renderScreen()
    fireEvent.click(await screen.findByRole('button', { name: 'Add' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add metric or field' })
    fireEvent.change(within(dialog).getByRole('textbox', { name: /Label/ }), { target: { value: 'OL Signups' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/already exists/)
  })

  it('edits a label, with key and applies-to fixed and an in-use data type locked', async () => {
    await renderScreen()
    await chooseAction('Shirt size', 'Edit')
    const dialog = await screen.findByRole('dialog', { name: 'Edit Shirt size' })

    expect(within(dialog).getByRole('textbox', { name: /^Key/ })).toBeDisabled()
    expect(within(dialog).getByRole('combobox', { name: /Applies to/ })).toHaveAttribute('aria-disabled', 'true')
    expect(within(dialog).getByRole('combobox', { name: /Data type/ })).toHaveAttribute('aria-disabled', 'true')
    expect(within(dialog).getByText(/values have been recorded/)).toBeInTheDocument()

    fireEvent.change(within(dialog).getByRole('textbox', { name: /Label/ }), { target: { value: 'T-shirt size' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))
    expect(await within(await table()).findByText('T-shirt size')).toBeInTheDocument()
  })

  it('keeps data type editable on an unused custom field, and a no-change save just closes', async () => {
    await renderScreen()
    await chooseAction('Dietary requirements', 'Edit')
    const dialog = await screen.findByRole('dialog', { name: 'Edit Dietary requirements' })

    expect(within(dialog).getByRole('combobox', { name: /Data type/ })).not.toHaveAttribute('aria-disabled', 'true')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('deactivates and reactivates, with no delete option', async () => {
    await renderScreen()
    fireEvent.click(within(await rowOf('OL Signups')).getByRole('button', { name: 'Actions for OL Signups' }))
    expect(await screen.findByRole('menuitem', { name: 'Deactivate' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /delete/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Deactivate' }))

    const off = await screen.findByRole('dialog', { name: 'Deactivate OL Signups' })
    expect(within(off).getByText(/Recorded values are kept/)).toBeInTheDocument()
    fireEvent.click(within(off).getByRole('button', { name: 'Deactivate' }))
    await waitFor(async () => expect(within(await rowOf('OL Signups')).getByText('Inactive')).toBeInTheDocument())

    await chooseAction('OL Signups', 'Reactivate')
    const on = await screen.findByRole('dialog', { name: 'Reactivate OL Signups' })
    fireEvent.click(within(on).getByRole('button', { name: 'Reactivate' }))
    await waitFor(async () => expect(within(await rowOf('OL Signups')).getByText('Active')).toBeInTheDocument())
  })
})
