/**
 * The Admin console (spec §2A.2): its own guard tree, own sign-in, own screens.
 * Rendered for real with the mock API, same approach as `routes.test.tsx`.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import App from '../App'
import { AppProviders } from '../AppProviders'
import { createMockApi } from '../api/mock/mockApi'
import type { PersonaKey } from '../api/mock/seed'

async function renderApp(persona: PersonaKey, path: string, signedIn = false) {
  const api = createMockApi({ persona, latencyMs: 0 })
  if (signedIn) await api.signIn()
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppProviders api={api}>
        <App />
      </AppProviders>
    </MemoryRouter>,
  )
  return { api }
}

beforeEach(() => sessionStorage.clear())

describe('admin console guards', () => {
  it('sends a signed-out visitor to the admin sign-in page, not the main one', async () => {
    await renderApp('mcvp', '/admin/lcs')
    expect(await screen.findByRole('heading', { name: 'Admin console' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('denies an LC Vice President, who holds no admin_console permission', async () => {
    await renderApp('lcvp', '/admin', true)
    expect(
      await screen.findByRole('heading', { name: 'Admin console' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/don.t have access to the admin console/)).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Admin console' })).not.toBeInTheDocument()
  })

  it('lets an MC Vice President in, landing on LCs', async () => {
    await renderApp('mcvp', '/admin', true)
    expect(await screen.findByRole('heading', { name: 'LCs' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Admin console' })
    expect(nav).toHaveTextContent('LCs')
    expect(nav).toHaveTextContent('People')
    expect(nav).toHaveTextContent('Auditing')
    // Only the screens built this term appear; the rest stay hidden until their own tickets land.
    expect(nav).not.toHaveTextContent('Memberships')
    expect(nav).not.toHaveTextContent('Permission matrix')
  })

  it('never puts an admin link in the main sidebar, or in the profile menu for a non-admin', async () => {
    await renderApp('lcvp', '/', true)
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    expect(nav).not.toHaveTextContent('Admin')
    fireEvent.click(screen.getByRole('button', { name: 'Open profile menu' }))
    expect(screen.queryByRole('menuitem', { name: 'Admin console' })).not.toBeInTheDocument()
  })

  it('shows an "Admin console" link in the profile menu, only for someone holding admin_console', async () => {
    await renderApp('mcvp', '/', true)
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    expect(nav).not.toHaveTextContent('Admin') // still never in the sidebar itself
    fireEvent.click(screen.getByRole('button', { name: 'Open profile menu' }))
    const link = screen.getByRole('menuitem', { name: 'Admin console' })
    expect(link).toHaveAttribute('href', '/admin')
    fireEvent.click(link)
    expect(await screen.findByRole('heading', { name: 'LCs' })).toBeInTheDocument()
  })
})

describe('admin console screens', () => {
  it('shows the LCs table with state and status, and an Add LC action', async () => {
    await renderApp('mcvp', '/admin/lcs', true)
    const table = await screen.findByRole('table', { name: 'LCs' })
    expect(await within(table).findByText('USYD')).toBeInTheDocument()
    // The MC row's name ("MC") and its type column ("MC") both render "MC".
    expect(within(table).getAllByText('MC')).toHaveLength(2)
    expect(within(table).getAllByText('NSW').length).toBeGreaterThan(0)
    expect(within(table).getAllByText('Active').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Add LC' })).toBeInTheDocument()
  })

  it('adds an LC with a state', async () => {
    await renderApp('mcvp', '/admin/lcs', true)
    await screen.findByRole('table', { name: 'LCs' })

    fireEvent.click(screen.getByRole('button', { name: 'Add LC' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add LC' })
    fireEvent.change(within(dialog).getByRole('textbox', { name: /Name/ }), { target: { value: 'UWA' } })
    fireEvent.mouseDown(within(dialog).getByRole('combobox', { name: /State/ }))
    fireEvent.click(await screen.findByRole('option', { name: /WA \(Australia\/Perth\)/ }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add LC' }))

    const table = await screen.findByRole('table', { name: 'LCs' })
    expect(await within(table).findByText('UWA')).toBeInTheDocument()
    expect(within(table).getByText('WA')).toBeInTheDocument()
  })

  it('renames an LC', async () => {
    await renderApp('mcvp', '/admin/lcs', true)
    const table = await screen.findByRole('table', { name: 'LCs' })
    fireEvent.click(await within(table).findByRole('button', { name: 'Actions for USYD' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Rename' }))

    const dialog = await screen.findByRole('dialog', { name: 'Rename USYD' })
    fireEvent.change(within(dialog).getByRole('textbox', { name: /Name/ }), { target: { value: 'University of Sydney' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Rename' }))

    expect(await within(await screen.findByRole('table', { name: 'LCs' })).findByText('University of Sydney')).toBeInTheDocument()
  })

  it('shows the server message when a rename clashes with an existing LC', async () => {
    await renderApp('mcvp', '/admin/lcs', true)
    const table = await screen.findByRole('table', { name: 'LCs' })
    fireEvent.click(await within(table).findByRole('button', { name: 'Actions for USYD' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Rename' }))

    const dialog = await screen.findByRole('dialog', { name: 'Rename USYD' })
    fireEvent.change(within(dialog).getByRole('textbox', { name: /Name/ }), { target: { value: 'mu' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Rename' }))

    expect(await within(dialog).findByText('An LC with that name already exists.')).toBeInTheDocument()
  })

  it('marks an LC inactive and then active again, with no delete option', async () => {
    await renderApp('mcvp', '/admin/lcs', true)
    const table = await screen.findByRole('table', { name: 'LCs' })
    fireEvent.click(await within(table).findByRole('button', { name: 'Actions for UNSW' }))
    expect(screen.queryByRole('menuitem', { name: /delete/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Mark inactive' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Mark UNSW inactive' })).getByRole('button', { name: 'Mark inactive' }))

    const unswRow = async () => (await within(await screen.findByRole('table', { name: 'LCs' })).findByText('UNSW')).closest('tr')!
    await waitFor(async () => expect(within(await unswRow()).getByText('Inactive')).toBeInTheDocument())

    fireEvent.click(within(await unswRow()).getByRole('button', { name: 'Actions for UNSW' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Mark active' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Mark UNSW active' })).getByRole('button', { name: 'Mark active' }))
    await waitFor(async () => expect(within(await unswRow()).getByText('Active')).toBeInTheDocument())
  })

  it('merges an LC into another, reports the result, and marks the source inactive', async () => {
    await renderApp('mcvp', '/admin/lcs', true)
    const table = await screen.findByRole('table', { name: 'LCs' })
    fireEvent.click(await within(table).findByRole('button', { name: 'Actions for MU' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Merge into another LC' }))

    const dialog = await screen.findByRole('dialog', { name: 'Merge MU' })
    fireEvent.mouseDown(within(dialog).getByRole('combobox', { name: /Merge into/ }))
    fireEvent.click(await screen.findByRole('option', { name: 'USYD' }))
    expect(within(dialog).getByText(/Their past records and KPIs stay under MU/)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Merge' }))

    expect(await screen.findByRole('dialog', { name: 'Merge complete' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    const muRow = (await within(await screen.findByRole('table', { name: 'LCs' })).findByText('MU')).closest('tr')!
    await waitFor(() => expect(within(muRow).getByText('Inactive')).toBeInTheDocument())
  })

  it('does not offer the MC as something to merge or deactivate', async () => {
    await renderApp('mcvp', '/admin/lcs', true)
    const table = await screen.findByRole('table', { name: 'LCs' })
    fireEvent.click(await within(table).findByRole('button', { name: 'Actions for MC' }))
    expect(screen.queryByRole('menuitem', { name: 'Merge into another LC' })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Mark inactive' })).not.toBeInTheDocument()
  })

  it('shows the People table, searchable, with email and status', async () => {
    await renderApp('mcvp', '/admin/people', true)
    expect(await screen.findByRole('heading', { name: 'People' })).toBeInTheDocument()
    const table = await screen.findByRole('table', { name: 'People' })
    expect(within(table).getByText('temp_ogv@aiesec.example')).toBeInTheDocument()
    expect(within(table).getAllByText('Active').length).toBeGreaterThan(0)

    fireEvent.change(screen.getByLabelText('Search people'), { target: { value: 'casey' } })
    expect(await within(await screen.findByRole('table', { name: 'People' })).findByText('casey@aiesec.example')).toBeInTheDocument()
  })

  it('paginates the People table server-side, 10 at a time by default', async () => {
    await renderApp('mcvp', '/admin/people', true)
    const table = await screen.findByRole('table', { name: 'People' })
    // The seed has more than 10 people, so only a page's worth of rows renders.
    expect(within(table).getAllByRole('row')).toHaveLength(11) // header + 10 data rows
    expect(await screen.findByText('1–10 of 53')).toBeInTheDocument()
  })

  it('shows the Auditing screen as a "not built yet" placeholder', async () => {
    await renderApp('mcvp', '/admin/auditing', true)
    expect(await screen.findByRole('heading', { name: 'Auditing' })).toBeInTheDocument()
    expect(screen.getByText(/Not built yet\./)).toBeInTheDocument()
  })

  it('lets an admin exit back to the main app and sign out from the admin header menu', async () => {
    await renderApp('mcvp', '/admin', true)
    await screen.findByRole('heading', { name: 'LCs' })
    fireEvent.click(screen.getByRole('button', { name: 'Open profile menu' }))
    expect(screen.getByRole('menuitem', { name: 'Exit to main app' })).toHaveAttribute('href', '/')
    fireEvent.click(screen.getByRole('menuitem', { name: 'Sign out' }))
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })
})
