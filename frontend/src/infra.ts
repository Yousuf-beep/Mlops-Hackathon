/**
 * Presentation rules for discovered runtime infrastructure.
 *
 * The backend addresses every published port as `localhost`, because that is
 * what it is for the machine running the stack. The one decision left to the
 * client is the *host* in a link: when a port is bound to every interface and
 * the dashboard is being read from somewhere else — a second laptop, the
 * browser driving a projector, a phone on the same network — `localhost` would
 * be that reader's own machine and the link would go nowhere.
 */

import type { ContainerPort } from './types'

/** Hostnames that mean "the machine this browser is running on". */
const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]', '::1', ''])

/**
 * Rewrite a discovered URL onto an address this browser can actually reach.
 *
 * Only applies to ports bound to every interface. A port published on one
 * specific IP is reachable at that IP and nowhere else, so its URL is left
 * exactly as the runtime reported it rather than being rewritten into a lie.
 *
 * @param url The address as discovered, e.g. `http://localhost:5173`.
 * @param wildcardBind Whether the port is bound to every host interface.
 * @returns An address that resolves from wherever the dashboard is being read.
 */
export function resolveUrl(url: string, wildcardBind: boolean): string {
  if (!wildcardBind) return url
  const viewing = window.location.hostname
  if (LOOPBACK_HOSTS.has(viewing)) return url
  try {
    const parsed = new URL(url)
    parsed.hostname = viewing
    return parsed.toString().replace(/\/$/, '')
  } catch {
    // A scheme the URL parser will not take apart. The discovered address is
    // still correct for the host, so show that rather than nothing.
    return url
  }
}

/** Human-readable label for a Docker lifecycle state. */
const STATE_LABEL: Record<string, string> = {
  running: 'Running',
  exited: 'Stopped',
  created: 'Created',
  paused: 'Paused',
  restarting: 'Restarting',
  removing: 'Removing',
  dead: 'Dead',
}

/** Human-readable label for a healthcheck verdict. */
const HEALTH_LABEL: Record<string, string> = {
  healthy: 'Healthy',
  unhealthy: 'Unhealthy',
  starting: 'Starting',
}

/**
 * Title-case a runtime word this build has no label for.
 *
 * Docker gains states over time, and a future one should read as `Paused` does
 * rather than as a raw lowercase token — the panel degrades to plain English
 * instead of to something that looks broken.
 */
function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

/** Name a Docker lifecycle state the way a person would, whatever it is. */
export function stateLabel(state: string): string {
  return STATE_LABEL[state] ?? titleCase(state)
}

/** Name a healthcheck verdict the way a person would. */
export function healthLabel(health: string): string {
  return HEALTH_LABEL[health] ?? titleCase(health)
}

/**
 * Name a status word that could be either.
 *
 * The backend collapses a service to one word for the compact cards, and that
 * word is a health verdict when the container declares a healthcheck and a
 * lifecycle state otherwise — so both vocabularies are consulted.
 */
export function runtimeLabel(status: string): string {
  return HEALTH_LABEL[status] ?? STATE_LABEL[status] ?? titleCase(status)
}

/**
 * Render one port mapping the way `docker ps` does: host first, then the port
 * inside the container. An unpublished port has no host side to show.
 *
 * @param port The mapping to render.
 * @returns e.g. `5173 → 8080/tcp`, or `8080/tcp` when nothing is published.
 */
export function portLabel(port: ContainerPort): string {
  const target = `${port.container_port}/${port.protocol}`
  return port.host_port === null ? target : `${port.host_port} → ${target}`
}
