/**
 * The page curtain: one slanted sheet that wipes across the viewport to cover
 * a route change, then wipes off to reveal what replaced it.
 *
 * Modelled on Motion+'s `PageCurtain`, which is a single overlay panel doing a
 * diagonal clip-wipe in one continuous motion — not a pair of panels parting.
 * Rebuilt on the free `motion` package for the same reason as the scramble:
 * the original is a Motion+ exclusive. Under reduced motion it is an instant
 * swap, as the original is.
 *
 * It sits above the router rather than inside a route, which is what lets one
 * uninterrupted sweep span the moment the page underneath is replaced.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { useLocation } from 'react-router-dom'

import './PageCurtain.css'
import { CurtainContext, type PageCurtain } from './curtain'

/** Slant of the leading edge, in degrees. Motion+'s `angle` defaults to 9. */
const ANGLE = 9

/** How long the sheet takes to cover the viewport, in seconds. */
const SWEEP_IN_S = 0.5

/** How long the sheet takes to clear it again, in seconds. */
const SWEEP_OUT_S = 0.62

/**
 * How far off-screen the sheet parks.
 *
 * Comfortably past the viewport plus the overhang the skew adds, so no corner
 * of the page is ever uncovered mid-sweep.
 */
const OFFSCREEN = '165vw'

/** Longest the covered sheet waits for the route to change, in milliseconds. */
const MAX_HOLD_MS = 1500

/**
 * Where the sheet is in its travel.
 *
 * - `idle` — not rendered.
 * - `in` — sweeping on, left to right, to cover the page.
 * - `covered` — holding, while the route underneath is replaced.
 * - `out` — sweeping off, revealing whatever is now beneath.
 */
type Phase = 'idle' | 'in' | 'covered' | 'out'

/** Owns the one curtain, and reveals the first page on arrival. */
export function PageCurtainProvider({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion()
  const location = useLocation()

  // First paint starts covered and sweeps off, so arriving at the app is the
  // same gesture as moving between its pages.
  const [phase, setPhase] = useState<Phase>(() => (reduced ? 'idle' : 'out'))
  const [entryFrom, setEntryFrom] = useState('0vw')
  const coveredAt = useRef(location.pathname)

  const cover = useCallback(() => {
    if (reduced) return
    coveredAt.current = location.pathname
    setEntryFrom(`-${OFFSCREEN}`)
    setPhase('in')
  }, [reduced, location.pathname])

  // Uncover as soon as the route has actually changed. The timeout is the
  // escape hatch: a navigation that never happens must not leave the sheet
  // parked over the app.
  useEffect(() => {
    if (phase !== 'covered') return
    if (location.pathname !== coveredAt.current) {
      setPhase('out')
      return
    }
    const timer = window.setTimeout(() => setPhase('out'), MAX_HOLD_MS)
    return () => window.clearTimeout(timer)
  }, [phase, location.pathname])

  // Guards are held while the sheet is inbound, so a dropped `onAnimationComplete`
  // would strand the app on its current page. Time it out independently.
  useEffect(() => {
    if (phase !== 'in') return
    const timer = window.setTimeout(
      () => setPhase((current) => (current === 'in' ? 'covered' : current)),
      SWEEP_IN_S * 1000 + 400,
    )
    return () => window.clearTimeout(timer)
  }, [phase])

  const curtain: PageCurtain = { cover, blocking: phase === 'in' }

  return (
    <CurtainContext.Provider value={curtain}>
      {children}

      {phase === 'idle' ? null : (
        <motion.div
          className="pageCurtain"
          aria-hidden="true"
          initial={{ x: entryFrom, skewX: -ANGLE }}
          animate={{ x: phase === 'out' ? OFFSCREEN : '0vw', skewX: -ANGLE }}
          transition={{
            duration: phase === 'out' ? SWEEP_OUT_S : SWEEP_IN_S,
            // Decelerating on the reveal, so the page it uncovers settles
            // rather than snapping into place.
            ease: phase === 'out' ? [0.16, 1, 0.3, 1] : [0.4, 0, 0.2, 1],
          }}
          onAnimationComplete={() => {
            setPhase((current) =>
              current === 'in' ? 'covered' : current === 'out' ? 'idle' : current,
            )
          }}
        />
      )}
    </CurtainContext.Provider>
  )
}
