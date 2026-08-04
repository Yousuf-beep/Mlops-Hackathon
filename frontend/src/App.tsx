import './App.css'

/**
 * Phase-1 placeholder for the PulseGrid dashboard.
 *
 * The real dashboard — Recharts panels for latency, traffic, errors and
 * saturation, fed live by the `/v1/stream` SSE channel — is built in phase 4.
 * Recharts is already installed so that phase is a pure code change.
 */
function App() {
  return (
    <main className="shell">
      <header className="header">
        <span className="pulse" aria-hidden="true" />
        <h1>PulseGrid</h1>
      </header>

      <p className="tagline">
        Enterprise API analytics &amp; performance management — Golden Signals,
        ML anomaly detection and traffic forecasting over live APIs.
      </p>

      <section className="panel">
        <h2>Dashboard placeholder</h2>
        <p>
          The backend runs at <code>http://localhost:8000</code>. Browse the API
          at <code>/docs</code>, or watch the live event stream with{' '}
          <code>curl -N http://localhost:8000/v1/stream</code>.
        </p>
      </section>

      <ol className="phases">
        <li className="done">Phase 1 — skeleton, schema, auth, registry, CI</li>
        <li>Phase 2 — reverse proxy, rollups, analytics endpoints</li>
        <li>Phase 3 — forecasting and explained anomaly detection</li>
        <li>Phase 4 — this dashboard, plus Kubernetes manifests</li>
      </ol>
    </main>
  )
}

export default App
