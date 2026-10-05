/**
 * The Admin console (spec §2A.2): its own guard tree, own sign-in, own screens.
 * Rendered for real with the mock API, same approach as `routes.test.tsx`.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
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

  it('never shows a link to the admin console from the main app', async () => {
    await renderApp('mcvp', '/', true)
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    expect(nav).not.toHaveTextContent('Admin')
    expect(screen.queryByRole('link', { name: /admin/i })).not.toBeInTheDocument()
  })
})

describe('admin console screens', () => {
  it('shows the LCs table with real reference data, and an Add LC action that is not built yet', async () => {
    await renderApp('mcvp', '/admin/lcs', true)
    const table = await screen.findByRole('table', { name: 'LCs' })
    expect(within(table).getByText('USYD')).toBeInTheDocument()
    // The MC row's name ("MC") and its type column ("MC") both render "MC".
    expect(within(table).getAllByText('MC')).toHaveLength(2)

    fireEvent.click(screen.getByRole('button', { name: 'Add LC' }))
    expect(await screen.findByRole('heading', { name: 'Add LC' })).toBeInTheDocument()
    expect(screen.getByText(/Not built yet\./)).toBeInTheDocument()
  })

  it('lets an admin rename an LC through the stub action', async () => {
    await renderApp('mcvp', '/admin/lcs', true)
    const table = await screen.findByRole('table', { name: 'LCs' })
    fireEvent.click(within(table).getByRole('button', { name: 'Actions for USYD' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Rename' }))
    expect(await screen.findByRole('heading', { name: 'Rename USYD' })).toBeInTheDocument()
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
