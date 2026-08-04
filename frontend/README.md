# PulseGrid dashboard

Vite + React 19 + TypeScript + Recharts. **Phase 1 ships the scaffold only** —
`src/App.tsx` is a placeholder. The real dashboard (Recharts panels for
latency, traffic, errors and saturation, fed live by the backend's
`/v1/stream` SSE channel) is built in phase 4.

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check + production bundle into dist/
npm run lint     # oxlint
```

The backend allows CORS from `localhost:5173`, so `npm run dev` talks to
`http://localhost:8000` with no proxy configuration.

See the [root README](../README.md) for the full stack and setup.
