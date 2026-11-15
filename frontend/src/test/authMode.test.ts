/** The sign-in placeholder must be off in deployed builds unless explicitly chosen (§2A.3). */
import { describe, expect, it } from 'vitest'

import { pickAuthMode } from '../api/authMode'

describe('pickAuthMode', () => {
  it('uses real sign-in in a production build when nothing is set', () => {
    expect(pickAuthMode({ PROD: true })).toBe('supabase')
  })

  it('uses the development sign-in on the dev server and in tests when nothing is set', () => {
    expect(pickAuthMode({ PROD: false })).toBe('mock')
  })

  it('always follows an explicit VITE_AUTH_MODE', () => {
    expect(pickAuthMode({ PROD: true, VITE_AUTH_MODE: 'mock' })).toBe('mock')
    expect(pickAuthMode({ PROD: false, VITE_AUTH_MODE: 'supabase' })).toBe('supabase')
  })

  it('treats an unknown value like an unset one', () => {
    expect(pickAuthMode({ PROD: true, VITE_AUTH_MODE: 'Supabase ' })).toBe('supabase')
    expect(pickAuthMode({ PROD: false, VITE_AUTH_MODE: 'yes' })).toBe('mock')
  })
})
