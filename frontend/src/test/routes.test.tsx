/**
 * Route guards and the fixed wording from the spec, rendered for real with the mock API.
 * The Data Grid is not rendered here (jsdom cannot lay it out), so the Membership page
 * itself is covered in the browser check and by the logic tests.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import App from '../App'
import { AppProviders } from '../AppProviders'
import { createMockApi } from '../api/mock/mockApi'
import type { PersonaKey } from '../api/mock/seed'

async function renderApp(persona: PersonaKey, path = '/', signedIn = false) {
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

describe('route guards', () => {
  it('sends a signed-out visitor to the sign-in page', async () => {
    await renderApp('lcvp', '/membership')
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    // The product title sits on the blue panel.
    expect(screen.getByText('AIESEC in Australia')).toBeInTheDocument()
    expect(screen.getByText('Internal Membership Tool')).toBeInTheDocument()
  })

  it('signs in and lands on the homepage, with only the pages this person may see', async () => {
    await renderApp('lcvp', '/sign-in')
    fireEvent.click(await screen.findByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('heading', { name: 'Home' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(nav).toHaveTextContent('Membership')
  })

  it('shows a Member no Membership link', async () => {
    await renderApp('member', '/sign-in')
    fireEvent.click(await screen.findByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('heading', { name: 'Home' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Main' })).not.toHaveTextContent('Membership')
  })

  it('tells a Member "Page not available" if they type the Membership address', async () => {
    await renderApp('member', '/membership', true)
    expect(await screen.findByRole('heading', { name: 'Page not available' })).toBeInTheDocument()
  })

  it('shows the not-allocated message, verbatim, to someone with no active membership', async () => {
    await renderApp('unallocated', '/sign-in')
    fireEvent.click(await screen.findByRole('button', { name: 'Sign in' }))
    expect(
      await screen.findByRole('heading', {
        name: 'You have not been allocated yet, please contact someone in your EB or MC',
      }),
    ).toBeInTheDocument()
  })

  it('signs out from the profile menu and returns to sign-in', async () => {
    await renderApp('lcvp', '/sign-in')
    fireEvent.click(await screen.findByRole('button', { name: 'Sign in' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile menu' }))
    expect(screen.getByRole('menuitem', { name: 'Profile' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Sign out' }))
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })
})

describe('placeholder pages and the profile', () => {
  it('shows Tracking, Data and Settings in the sidebar for a Vice President', async () => {
    await renderApp('lcvp', '/', true)
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    for (const label of ['Home', 'Membership', 'Tracking', 'Data', 'Settings']) {
      expect(nav).toHaveTextContent(label)
    }
  })

  it('says what a placeholder page will do', async () => {
    await renderApp('lcvp', '/tracking', true)
    expect(await screen.findByRole('heading', { name: 'Tracking' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Not built yet' })).toBeInTheDocument()
  })

  it('keeps Data away from a Member, who has no analytics permission', async () => {
    await renderApp('member', '/data', true)
    expect(await screen.findByRole('heading', { name: 'Page not available' })).toBeInTheDocument()
  })

  it('shows the Functions block on Settings to MC positions only', async () => {
    await renderApp('mcvp', '/settings', true)
    expect(await screen.findByRole('heading', { name: 'Functions' })).toBeInTheDocument()
  })

  it('does not show the Functions block on Settings to an LC Vice President', async () => {
    await renderApp('lcvp', '/settings', true)
    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Functions' })).not.toBeInTheDocument()
  })

  it('has no "About you" box on Profile while there are no person-level fields', async () => {
    await renderApp('lcvp', '/profile', true)
    expect(await screen.findByRole('heading', { name: 'Position history' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'About you' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Shirt size')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Pronouns')).not.toBeInTheDocument()
  })
})
