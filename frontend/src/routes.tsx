/**
 * Routing and the session gate.
 *
 * Two routes: `/` is the login gate and `/dashboard` is the dashboard, and the
 * session decides which one you are allowed to see. Both guards defer while the
 * session is `pending` — a stored token being validated, or the beat between a
 * successful sign-in and `/v1/auth/me` answering — because redirecting during
 * that gap would bounce an authenticated visitor back to the login screen and
 * then immediately forward again.
 *
 * nginx already serves unknown paths as `index.html` (see `nginx.conf.template`),
 * so a deep link to `/dashboard` reaches this router in production too.
 */

import { Navigate, Route, Routes } from 'react-router-dom'

import App from './App'
import { PageCurtainProvider } from './PageCurtain'
import { usePageCurtain } from './curtain'
import LoginPage, { SessionSplash } from './pages/Login'
import { sessionPhase, useAuth } from './session'

/** The dashboard, for signed-in operators only. */
function Dashboard() {
  const phase = sessionPhase(useAuth())
  if (phase === 'pending') return <SessionSplash />
  if (phase === 'out') return <Navigate to="/" replace />
  return <App />
}

/**
 * The gate. Anyone already signed in is sent straight through — but not until
 * the curtain has finished covering, so the handover happens out of sight
 * rather than in the gap beside a half-drawn sheet.
 */
function Gate() {
  const phase = sessionPhase(useAuth())
  const { blocking } = usePageCurtain()
  if (phase === 'pending') return <SessionSplash />
  if (phase === 'in' && !blocking) return <Navigate to="/dashboard" replace />
  return <LoginPage />
}

/**
 * The route table, under the curtain.
 *
 * The curtain is mounted outside `<Routes>` on purpose: it has to survive the
 * swap it is covering, which it could not do from inside the route being
 * replaced.
 */
export function AppRoutes() {
  return (
    <PageCurtainProvider>
      <Routes>
        <Route path="/" element={<Gate />} />
        <Route path="/dashboard" element={<Dashboard />} />
        {/* Anything else is not a page; send it to the gate, which forwards
            signed-in visitors on to the dashboard by itself. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </PageCurtainProvider>
  )
}
