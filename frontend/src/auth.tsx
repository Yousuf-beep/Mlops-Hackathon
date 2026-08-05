/**
 * The one place the session is instantiated.
 *
 * `useAuthState` must run *once* for the whole app: the route guards and the
 * dashboard both read the session, and two independent copies would drift the
 * moment one of them signed out. Consumers read it back with `useAuth()` from
 * `session.ts`.
 */

import type { ReactNode } from 'react'

import { useAuthState } from './hooks'
import { AuthContext } from './session'

/** Owns the one session instance every route reads from. */
export function AuthProvider({ children }: { children: ReactNode }) {
  return <AuthContext.Provider value={useAuthState()}>{children}</AuthContext.Provider>
}
