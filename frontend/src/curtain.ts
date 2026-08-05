/**
 * Access to the page curtain.
 *
 * Kept apart from the provider so this module holds no components — a file
 * that mixes the two breaks React Fast Refresh for both.
 */

import { createContext, useContext } from 'react'

/** What a caller can ask the curtain to do, and what it needs back. */
export interface PageCurtain {
  /**
   * Sweep the curtain across the viewport, hold while the route changes, then
   * sweep off to reveal whatever replaced it.
   *
   * Safe to call when the route change is driven by something else (a guard
   * reacting to the session, say) — the curtain waits for the location to
   * actually change before uncovering, and gives up after a moment if it
   * never does.
   */
  cover: () => void

  /**
   * True while the sheet is still travelling and has not yet covered the page.
   *
   * Route guards must hold their current page for as long as this is set.
   * Sign-in resolves in a few hundred milliseconds, comfortably less than the
   * sweep takes, so without this the page would be swapped underneath a sheet
   * that is only part-way across and the new route would appear in the gap —
   * which is the whole thing the curtain exists to prevent.
   */
  blocking: boolean
}

/** Carries the one curtain created by `PageCurtainProvider`. */
export const CurtainContext = createContext<PageCurtain | null>(null)

/**
 * Read the page curtain.
 *
 * @throws If called outside `PageCurtainProvider` — a wiring bug, not a
 *   runtime state, so it fails loudly rather than silently doing nothing.
 */
export function usePageCurtain(): PageCurtain {
  const curtain = useContext(CurtainContext)
  if (!curtain) throw new Error('usePageCurtain() must be called inside <PageCurtainProvider>')
  return curtain
}
