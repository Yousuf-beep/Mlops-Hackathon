import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

/**
 * The dashboard talks to the backend over *relative* paths, and this proxy
 * forwards them in development. Same-origin requests mean no CORS preflight and
 * no absolute URL baked into the bundle — and, crucially, `text/event-stream`
 * passes through untouched, which is what keeps `/v1/stream` streaming.
 *
 * Point the API elsewhere with `PULSEGRID_API` (dev proxy) or `VITE_API_BASE`
 * (absolute URL compiled into the bundle).
 */
const target = process.env.PULSEGRID_API ?? 'http://127.0.0.1:8000'

const proxied = ['/v1', '/proxy', '/health', '/docs', '/redoc', '/openapi.json']

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      proxied.map((path) => [path, { target, changeOrigin: true, ws: false }]),
    ),
  },
})
