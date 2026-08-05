/**
 * Reading the signed-in session.
 *
 * `useAuthState` in `hooks.ts` owns the state, `AuthProvider` in `auth.tsx`
 * runs it exactly once, and everything else reads it through here. Kept apart
 * from the provider so this module holds no components — a file that mixes the
 * two breaks React Fast Refresh for both.
 */

import { createContext, useContext } from 'react'

import type { Auth } from './hooks'

/** Carries the one session instance created by `AuthProvider`. */
export const AuthContext = createContext<Auth | null>(null)

/**
 * Read the current session.
 *
 * @returns The signed-in account, token and the sign-in/up/out actions.
 * @throws If called outside `AuthProvider` — a wiring bug, not a runtime state,
 *   so it fails loudly rather than silently rendering as signed out.
 */
export function useAuth(): Auth {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth() must be called inside <AuthProvider>')
  return auth
}

/**
 * Where the session currently stands, as the route guards need to read it.
 *
 * `pending` covers both halves of the gap that would otherwise bounce an
 * authenticated visitor back to the login screen: a stored token being
 * validated against `/v1/auth/me` on load, *and* the render immediately after
 * a successful sign-in, where the token exists but `/v1/auth/me` has not
 * answered yet.
 */
export type SessionPhase = 'pending' | 'in' | 'out'

/** Collapse the session into the three states a guard has to distinguish. */
export function sessionPhase({ user, token, resolving }: Auth): SessionPhase {
  if (user) return 'in'
  if (resolving || token) return 'pending'
  return 'out'
}
