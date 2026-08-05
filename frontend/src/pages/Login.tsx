/**
 * The front door: a plain gate at `/` that has to be passed before the
 * dashboard renders.
 *
 * Nothing on it but the wordmark, which is also the way in. It resolves out of
 * noise on arrival, then keeps cycling through random glyphs; hovering or
 * focusing it locks the real word back in, and activating it blurs the page
 * behind a credential pill.
 *
 * Both motion effects are rebuilt on the free `motion` package — the originals
 * (`scrambleText`, `@motion/page-curtains`) are Motion+ exclusives and the
 * public package is a stub.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type RefObject,
} from 'react'
import { AnimatePresence, motion, useAnimationControls, useReducedMotion } from 'motion/react'

import '../App.css'
import './Login.css'
import { ApiError } from '../api'
import { usePageCurtain } from '../curtain'
import { useAuth } from '../session'

/** Credentials the demo stack seeds on first boot (`app/bootstrap.py`). */
const DEMO_EMAIL = 'admin@pulsegrid.dev'
const DEMO_PASSWORD = 'pulsegrid-demo'

/** Password floor enforced by the backend on registration. */
const MIN_PASSWORD = 8

/** The wordmark, and the only control on the page. */
const WORDMARK = 'PulseGrid.'

/* -------------------------------------------------------------------------- */
/* Scramble                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * Glyphs the title cycles through.
 *
 * Deliberately mixed alphanumerics and punctuation: an all-letters set reads
 * as a word being mistyped, while the symbols make it read as a signal that
 * has not locked yet, which is the association this product wants.
 */
const SCRAMBLE_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789<>-_/[]{}=+*^?#'

/**
 * How often the unresolved glyphs re-roll, in milliseconds.
 *
 * Fast enough to read as a character cycling rather than as the string being
 * swapped — the difference between a scramble and a strobe.
 */
const FLICKER_MS = 30

/**
 * How long every character scrambles before the first one locks in.
 *
 * This is `scrambleText`'s `duration`; {@link STAGGER_MS} is the per-character
 * offset added on top, i.e. `duration: stagger(0.06)`.
 */
const SETTLE_MS = 420

/** Extra scramble time each successive character gets, in milliseconds. */
const STAGGER_MS = 60

/** How long the resolved word is held before the cycle runs again. */
const HOLD_MS = 900

/** How long the first cycle waits, so it starts as the curtains part. */
const START_DELAY_MS = 260

/** One random glyph from {@link SCRAMBLE_CHARS}. */
function randomChar(): string {
  return SCRAMBLE_CHARS[Math.floor(Math.random() * SCRAMBLE_CHARS.length)]
}

/**
 * Run the scramble on `ref`'s text content for as long as `active`.
 *
 * Modelled on `scrambleText`'s staggered form — every character flickers from
 * the start and they lock in progressively, left to right, rather than a
 * cursor wiping across a static string:
 *
 * ```js
 * scrambleText(element, { duration: stagger(0.06) })
 * ```
 *
 * so character `i` settles at `SETTLE_MS + i * STAGGER_MS`. Once the whole
 * word is up it is held for {@link HOLD_MS} and the cycle repeats, which is
 * what keeps the title alive without it ever becoming a strobe.
 *
 * Writes straight to the DOM node instead of through state: at ~33 repaints a
 * second, forever, React reconciliation is pure overhead, and the glyphs are
 * decorative anyway — the real word lives on the trigger's `aria-label`.
 */
function useScrambleText(ref: RefObject<HTMLElement | null>, text: string, active: boolean): void {
  useEffect(() => {
    const node = ref.current
    if (!node) return

    if (!active) {
      node.textContent = text
      return
    }

    /** When the last character of the word locks in. */
    const settledAt = SETTLE_MS + Math.max(0, text.length - 1) * STAGGER_MS
    const cycleMs = settledAt + HOLD_MS

    let frame = 0
    let cycleStart = 0
    let lastPaint = 0
    let delay = START_DELAY_MS

    const step = (now: number) => {
      if (!cycleStart) cycleStart = now
      const elapsed = now - cycleStart - delay

      if (elapsed >= cycleMs) {
        // Every cycle after the first starts immediately; only the arrival
        // waits for the curtains.
        cycleStart = now
        delay = 0
        lastPaint = 0
      } else if (elapsed >= 0 && now - lastPaint >= FLICKER_MS) {
        lastPaint = now
        let next = ''
        for (let index = 0; index < text.length; index++) {
          const char = text[index]
          if (!char.trim()) next += char
          else next += elapsed >= SETTLE_MS + index * STAGGER_MS ? char : randomChar()
        }
        node.textContent = next
      }

      frame = requestAnimationFrame(step)
    }

    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [ref, text, active])
}

/* -------------------------------------------------------------------------- */
/* The gate                                                                    */
/* -------------------------------------------------------------------------- */

/** Which credential flow the form is in. */
type Mode = 'signin' | 'signup'

/**
 * The rejection shake: a decaying horizontal oscillation, as macOS uses on a
 * refused password.
 *
 * Additive only. The failure is already carried by the message in the
 * `aria-live` region and by `aria-invalid` on the fields, so nothing depends
 * on seeing the movement.
 */
const SHAKE_X = [0, -10, 9, -7, 5, -3, 0]

/** The `/` gate: a wordmark that opens a credential pill. */
export default function LoginPage() {
  const auth = useAuth()
  const curtain = usePageCurtain()
  const reduced = useReducedMotion()
  const shake = useAnimationControls()

  const [open, setOpen] = useState(false)
  const [held, setHeld] = useState(false)

  const [mode, setMode] = useState<Mode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<'form' | 'demo' | null>(null)

  const triggerRef = useRef<HTMLButtonElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const emailRef = useRef<HTMLInputElement>(null)
  const wordRef = useRef<HTMLSpanElement>(null)

  // The cycle runs continuously, and stops on the real word whenever the
  // title is pointed at, focused, or opened.
  useScrambleText(wordRef, WORDMARK, !reduced && !held && !open)

  const close = useCallback(() => {
    setOpen(false)
    setError(null)
    // Send focus back where it came from, rather than dropping it on <body>.
    triggerRef.current?.focus()
  }, [])

  // Focus the first field on open. Without this the dialog claims to be modal
  // while the caret is still out on the page behind it.
  useEffect(() => {
    if (open) emailRef.current?.focus()
  }, [open])

  /**
   * Run one credential attempt.
   *
   * Navigation is deliberately not handled here: the route guard watches the
   * session and moves the app on its own. This only draws the curtain across
   * first, so the swap happens behind it, and leaves `busy` set on success so
   * the form cannot be submitted twice in that gap.
   */
  const attempt = async (kind: 'form' | 'demo', address: string, secret: string) => {
    setError(null)
    setBusy(kind)
    try {
      if (mode === 'signup' && kind === 'form') await auth.signUp(address, secret)
      else await auth.signIn(address, secret)
      curtain.cover()
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : 'Could not reach PulseGrid. Is the backend running?',
      )
      setBusy(null)
      if (!reduced) void shake.start({ x: SHAKE_X, transition: { duration: 0.45 } })
      emailRef.current?.focus()
    }
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    void attempt('form', email, password)
  }

  const useDemo = () => {
    setMode('signin')
    setEmail(DEMO_EMAIL)
    setPassword(DEMO_PASSWORD)
    void attempt('demo', DEMO_EMAIL, DEMO_PASSWORD)
  }

  /**
   * Escape closes; Tab cycles inside.
   *
   * `aria-modal` tells assistive tech the rest of the page is inert, so the
   * keyboard has to actually behave that way.
   */
  const onDialogKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      close()
      return
    }
    if (event.key !== 'Tab' || !dialogRef.current) return

    const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
      'input:not([disabled]), button:not([disabled])',
    )
    if (!focusable.length) return

    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <>
      <main className="gate" data-open={open ? 'true' : 'false'}>
        <div className="gate__stage">
          <h1 className="gate__heading">
            <button
              ref={triggerRef}
              type="button"
              className="gate__wordmark"
              aria-label={`${WORDMARK} Sign in`}
              aria-expanded={open}
              onMouseEnter={() => setHeld(true)}
              onMouseLeave={() => setHeld(false)}
              onFocus={() => setHeld(true)}
              onBlur={() => setHeld(false)}
              onClick={() => setOpen(true)}
            >
              {/* Seeded with the real word so the first paint is never empty;
                  the scramble takes the node over on mount. */}
              <span ref={wordRef} aria-hidden="true">
                {WORDMARK}
              </span>
            </button>
          </h1>

          {/* The title is the only control on the page, and a cycling string
              does not look like one. This is the smallest hint that still
              makes the page usable without instruction. */}
          <p className="gate__hint" aria-hidden="true">
            click to sign in
          </p>
        </div>

        <AnimatePresence>
          {open ? (
            <motion.div
              className="gate__scrim"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: reduced ? 0 : 0.26, ease: 'easeOut' }}
              onClick={close}
            >
              <motion.div
                ref={dialogRef}
                className="gate__panel"
                role="dialog"
                aria-modal="true"
                aria-label="Sign in to PulseGrid"
                initial={{ opacity: 0, y: 12, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 8, scale: 0.99 }}
                transition={
                  reduced ? { duration: 0 } : { duration: 0.44, ease: [0.16, 1, 0.3, 1], delay: 0.08 }
                }
                onClick={(event) => event.stopPropagation()}
                onKeyDown={onDialogKeyDown}
              >
                {/* Two grouped rows rather than one horizontal capsule: a
                    capsule has to carry the field ring and the group ring at
                    once, which is what made the borders read as doubled. */}
                <form className="signin" onSubmit={submit}>
                  <motion.div className="signin__group" animate={shake}>
                    <div className="signin__row">
                      <label className="sr-only" htmlFor="gate-email">
                        Email
                      </label>
                      <input
                        ref={emailRef}
                        id="gate-email"
                        className="signin__field"
                        type="email"
                        name="email"
                        required
                        autoComplete="email"
                        placeholder="Email"
                        aria-invalid={error !== null}
                        value={email}
                        disabled={busy !== null}
                        onChange={(event) => setEmail(event.target.value)}
                      />
                    </div>

                    <div className="signin__row">
                      <label className="sr-only" htmlFor="gate-password">
                        Password
                      </label>
                      <input
                        id="gate-password"
                        className="signin__field"
                        type="password"
                        name="password"
                        required
                        // Only registration has a floor to enforce. Applying it
                        // to sign-in would lock out any account made before it
                        // existed.
                        minLength={mode === 'signup' ? MIN_PASSWORD : undefined}
                        autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                        placeholder="Password"
                        aria-invalid={error !== null}
                        value={password}
                        disabled={busy !== null}
                        onChange={(event) => setPassword(event.target.value)}
                      />

                      <button
                        type="submit"
                        className="signin__go"
                        disabled={busy !== null}
                        aria-label={mode === 'signin' ? 'Sign in' : 'Create account'}
                      >
                        {busy === 'form' ? (
                          <span className="signin__spinner" aria-hidden="true" />
                        ) : (
                          <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true">
                            <path
                              d="M2 8h11M9 4l4 4-4 4"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="1.9"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        )}
                      </button>
                    </div>
                  </motion.div>
                </form>

                {/* Mounted whether or not it holds a message, so assistive tech
                    is already watching the region when a failure lands. */}
                <div className="gate__errorSlot" role="alert" aria-live="assertive">
                  {error ? <p className="gate__error">{error}</p> : null}
                </div>

                <div className="gate__links">
                  <button
                    type="button"
                    className="gate__link"
                    onClick={() => {
                      setMode((current) => (current === 'signin' ? 'signup' : 'signin'))
                      setError(null)
                    }}
                  >
                    {mode === 'signin' ? 'Create an account' : 'I already have an account'}
                  </button>
                  <span className="gate__linkDot" aria-hidden="true" />
                  <button
                    type="button"
                    className="gate__link"
                    onClick={useDemo}
                    disabled={busy !== null}
                  >
                    {busy === 'demo' ? 'Signing in…' : 'Use the demo account'}
                  </button>
                </div>
              </motion.div>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </main>
    </>
  )
}

/**
 * Held while a stored token is checked against `/v1/auth/me`.
 *
 * Shares the gate's plane and mono wordmark so the handoff into either the
 * login screen or the dashboard is a continuation rather than a flash of a
 * third, unrelated screen.
 */
export function SessionSplash() {
  return (
    <div className="splash">
      <span className="splash__mark">{WORDMARK}</span>
      <p className="splash__note" role="status">
        Restoring your session…
      </p>
    </div>
  )
}
