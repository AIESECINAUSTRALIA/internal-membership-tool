/** The sign-in placeholder must be off in every deployed build (§2A.3). */
import { describe, expect, it } from 'vitest'

import { pickAuthMode } from '../api/authMode'

describe('pickAuthMode', () => {
  it('uses real sign-in in a production build when nothing is set', () => {
    expect(pickAuthMode({ PROD: true })).toBe('expa')
  })

  it('uses the development sign-in on the dev server and in tests when nothing is set', () => {
    expect(pickAuthMode({ PROD: false })).toBe('mock')
  })

  it('never allows mock sign-in in a production build', () => {
    expect(pickAuthMode({ PROD: true, VITE_AUTH_MODE: 'mock' })).toBe('expa')
  })

  it('allows explicit EXPA sign-in on the dev server', () => {
    expect(pickAuthMode({ PROD: false, VITE_AUTH_MODE: 'expa' })).toBe('expa')
  })

  it('allows explicit mock sign-in on the dev server', () => {
    expect(pickAuthMode({ PROD: false, VITE_AUTH_MODE: 'mock' })).toBe('mock')
  })

  it('treats an unknown value like an unset one', () => {
    expect(pickAuthMode({ PROD: true, VITE_AUTH_MODE: 'yes' })).toBe('expa')
    expect(pickAuthMode({ PROD: false, VITE_AUTH_MODE: 'yes' })).toBe('mock')
  })
})
