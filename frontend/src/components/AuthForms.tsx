/**
 * The two forms that make the fleet editable from the browser: signing in
 * (or creating an account) and registering a new API to monitor. Both were
 * previously curl-only — the backend routes (`/v1/auth/*`, `POST /v1/apis`)
 * already existed and are unchanged; this is the UI in front of them.
 */

import { useState, type FormEvent } from 'react'

import { ApiError, createApi } from '../api'
import type { Auth } from '../hooks'

/** Credentials the demo stack seeds on first boot (`app/bootstrap.py`). */
const DEMO_EMAIL = 'admin@pulsegrid.dev'
const DEMO_PASSWORD = 'pulsegrid-demo'

/** Props for {@link SignInForm}. */
export interface SignInFormProps {
  auth: Auth
  onSuccess: () => void
}

/**
 * Sign in to an existing account, or switch to creating a new one.
 *
 * A new account always registers as `viewer` — see {@link registerUser} — so
 * this form never exposes a role picker; there is nothing to choose.
 */
export function SignInForm({ auth, onSuccess }: SignInFormProps) {
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (mode === 'signin') await auth.signIn(email, password)
      else await auth.signUp(email, password)
      onSuccess()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Something went wrong. Try again.')
    } finally {
      setBusy(false)
    }
  }

  const fillDemoAccount = () => {
    setMode('signin')
    setEmail(DEMO_EMAIL)
    setPassword(DEMO_PASSWORD)
  }

  return (
    <form className="form" onSubmit={submit}>
      <div className="segmented" role="group" aria-label="Sign in or create an account">
        <button
          type="button"
          className={mode === 'signin' ? 'segmented__on' : undefined}
          onClick={() => setMode('signin')}
        >
          Sign in
        </button>
        <button
          type="button"
          className={mode === 'signup' ? 'segmented__on' : undefined}
          onClick={() => setMode('signup')}
        >
          Create account
        </button>
      </div>

      <label className="form__row">
        <span className="form__label">Email</span>
        <input
          className="form__input"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </label>

      <label className="form__row">
        <span className="form__label">Password</span>
        <input
          className="form__input"
          type="password"
          required
          minLength={8}
          autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>

      {error ? <p className="form__error">{error}</p> : null}

      <div className="form__actions">
        <button type="submit" className="form__submit" disabled={busy}>
          {busy ? 'Working…' : mode === 'signin' ? 'Sign in' : 'Create account'}
        </button>
      </div>

      {mode === 'signin' ? (
        <p className="form__hint">
          Demo account seeded on first boot:{' '}
          <button type="button" className="form__linklike" onClick={fillDemoAccount}>
            {DEMO_EMAIL}
          </button>
        </p>
      ) : null}
    </form>
  )
}

/** Props for {@link RegisterApiForm}. */
export interface RegisterApiFormProps {
  token: string
  onRegistered: () => void
}

/**
 * Register a new API for monitoring — the form in front of `POST /v1/apis`.
 *
 * Field defaults match the backend schema's own defaults (`slo_target=0.99`,
 * `slo_latency_ms=500`) so leaving them untouched produces the same row a
 * bare API call would.
 */
export function RegisterApiForm({ token, onRegistered }: RegisterApiFormProps) {
  const [name, setName] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [upstreamUrl, setUpstreamUrl] = useState('')
  const [sloTarget, setSloTarget] = useState('0.99')
  const [sloLatencyMs, setSloLatencyMs] = useState('500')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await createApi(
        {
          name,
          base_url: baseUrl,
          upstream_url: upstreamUrl,
          slo_target: Number(sloTarget),
          slo_latency_ms: Number(sloLatencyMs),
        },
        token,
      )
      onRegistered()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not register that API.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      <label className="form__row">
        <span className="form__label">Name</span>
        <input
          className="form__input"
          required
          placeholder="Payments API"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>

      <label className="form__row">
        <span className="form__label">Proxy slug</span>
        <input
          className="form__input"
          required
          placeholder="/payments"
          value={baseUrl}
          onChange={(event) => setBaseUrl(event.target.value)}
        />
        <span className="form__note">
          PulseGrid will measure calls made to <code>/proxy{baseUrl || '/…'}</code>.
        </span>
      </label>

      <label className="form__row">
        <span className="form__label">Upstream URL</span>
        <input
          className="form__input"
          required
          placeholder="http://payments-service:8080"
          value={upstreamUrl}
          onChange={(event) => setUpstreamUrl(event.target.value)}
        />
        <span className="form__note">The real service the proxy forwards to.</span>
      </label>

      <div className="form__grid2">
        <label className="form__row">
          <span className="form__label">Availability SLO</span>
          <input
            className="form__input"
            type="number"
            step="0.001"
            min="0.5"
            max="1"
            value={sloTarget}
            onChange={(event) => setSloTarget(event.target.value)}
          />
        </label>
        <label className="form__row">
          <span className="form__label">Latency SLO (ms)</span>
          <input
            className="form__input"
            type="number"
            min="1"
            value={sloLatencyMs}
            onChange={(event) => setSloLatencyMs(event.target.value)}
          />
        </label>
      </div>

      {error ? <p className="form__error">{error}</p> : null}

      <div className="form__actions">
        <button type="submit" className="form__submit" disabled={busy}>
          {busy ? 'Registering…' : 'Register API'}
        </button>
      </div>
    </form>
  )
}
