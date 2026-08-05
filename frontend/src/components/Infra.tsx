/**
 * The runtime-infrastructure panels: what is running, and where to reach it.
 *
 * Every value below comes from `/v1/infra/snapshot`, which reads the live
 * container runtime. No port, service name or URL is written into this file —
 * a service that starts publishing a new port appears here on the next tick,
 * and one that stops appears as stopped rather than silently disappearing.
 * The link-host rule these panels apply is in `infra.ts`.
 */

import { useState } from 'react'

import { since } from '../format'
import { healthLabel, portLabel, resolveUrl, runtimeLabel, stateLabel } from '../infra'
import type { ReadingMode } from '../narrate'
import { RUNTIME_COLOR } from '../theme'
import type {
  ContainerRead,
  DeploymentEnvironment,
  InfraSnapshot,
  ServiceEndpoint,
  WebService,
} from '../types'
import { Empty } from './Primitives'

/** Pick a string for the reading mode in force. */
function say(mode: ReadingMode, plain: string, engineer: string): string {
  return mode === 'plain' ? plain : engineer
}

/**
 * A runtime state, always a dot *and* its label.
 *
 * Same rule as every other status in this dashboard: colour restates what the
 * text already says, and never carries the meaning by itself.
 */
function RuntimeBadge({ status, label }: { status: string; label: string }) {
  return (
    <span className="badge">
      <span
        className="badge__dot"
        style={{ background: RUNTIME_COLOR[status] ?? RUNTIME_COLOR.none }}
        aria-hidden="true"
      />
      {label}
    </span>
  )
}

/** How long a container has been up. Em-dash when it is not up at all. */
function uptimeOf(container: ContainerRead): string {
  if (container.state !== 'running' || !container.started_at) return '—'
  const elapsed = since(container.started_at)
  return elapsed === 'just now' ? 'just started' : `up ${elapsed.replace(' ago', '')}`
}

/**
 * One discovered address.
 *
 * HTTP endpoints are links. Everything else — a database, a cache, a broker —
 * is rendered as plain text, because a `postgresql://` link that opens a blank
 * tab is worse than a string you can copy.
 */
function EndpointLink({ endpoint }: { endpoint: ServiceEndpoint }) {
  const href = resolveUrl(endpoint.url, endpoint.wildcard_bind)

  // The scheme is already the first word of the address, so it is not repeated
  // as a tag; the missing link colour and arrow are what say "not clickable".
  if (!endpoint.browsable) {
    return (
      <span className="endpoint endpoint--plain">
        <code>{href}</code>
      </span>
    )
  }

  return (
    <a className="endpoint" href={href} target="_blank" rel="noreferrer">
      <code>{href}</code>
      <span className="endpoint__go" aria-hidden="true">
        ↗
      </span>
    </a>
  )
}

/**
 * What a container's endpoint cell says when there is nothing to link to.
 *
 * An empty cell reads as a rendering bug. These three cases are genuinely
 * different — not published, nothing exposed, not running — and saying which
 * one it is takes the reader straight to the reason.
 */
function noEndpointReason(container: ContainerRead, mode: ReadingMode): string {
  if (container.state !== 'running') {
    return say(mode, 'Not running — nothing to open', 'Container stopped')
  }
  if (container.ports.length > 0) {
    return say(mode, 'Reachable inside the stack only', 'Exposed, not published to the host')
  }
  return say(mode, 'No ports — nothing to open', 'No ports exposed')
}

/** Props for {@link ContainerTable}. */
export interface ContainerTableProps {
  snapshot: InfraSnapshot | null
  mode: ReadingMode
}

/**
 * Every container in the stack, with the addresses its ports resolve to.
 *
 * State and health are separate columns on purpose. A container can be up and
 * failing its own healthcheck, and collapsing the two into one word would hide
 * exactly the case worth seeing — so does the reverse, showing "unhealthy" for
 * an image that simply never declared a healthcheck.
 */
export function ContainerTable({ snapshot, mode }: ContainerTableProps) {
  if (snapshot === null) return <Empty message="Reading the container runtime…" />

  if (!snapshot.available) {
    return (
      <Empty
        message={`Container runtime unavailable — ${snapshot.reason ?? 'no reason given'}. Mount /var/run/docker.sock into the API to enable discovery.`}
      />
    )
  }

  if (!snapshot.containers.length) {
    return <Empty message="The runtime is reachable, but no containers were found." />
  }

  return (
    <div className="tablewrap">
      <table className="table table--infra">
        <thead>
          <tr>
            <th scope="col">{say(mode, 'Service', 'Service / image')}</th>
            <th scope="col">Container</th>
            <th scope="col">{say(mode, 'Is it up?', 'State')}</th>
            <th scope="col">{say(mode, 'Is it well?', 'Health')}</th>
            <th scope="col">{say(mode, 'Ports (host → inside)', 'Ports')}</th>
            <th scope="col">{say(mode, 'Open it at', 'Endpoints')}</th>
          </tr>
        </thead>
        <tbody>
          {snapshot.containers.map((container) => (
            <tr key={container.id} className={container.state === 'running' ? undefined : 'row--off'}>
              <th scope="row">
                <span className="infra__service">{container.service}</span>
                <span className="infra__sub">{container.image}</span>
              </th>
              <td>
                <code>{container.name}</code>
                <span className="infra__sub">{container.id}</span>
              </td>
              <td>
                <RuntimeBadge status={container.state} label={stateLabel(container.state)} />
                <span className="infra__sub">{uptimeOf(container)}</span>
              </td>
              <td>
                {container.health === 'none' ? (
                  <span className="infra__none">{say(mode, 'Not checked', 'No healthcheck')}</span>
                ) : (
                  <RuntimeBadge status={container.health} label={healthLabel(container.health)} />
                )}
              </td>
              <td>
                {container.ports.length ? (
                  <span className="chips">
                    {container.ports.map((port) => (
                      <span
                        key={`${port.container_port}/${port.protocol}/${port.host_port ?? 'x'}`}
                        className={port.host_port === null ? 'chip chip--muted' : 'chip'}
                      >
                        {portLabel(port)}
                      </span>
                    ))}
                  </span>
                ) : (
                  <span className="infra__none">—</span>
                )}
              </td>
              <td>
                {container.endpoints.length ? (
                  <span className="endpoints">
                    {container.endpoints.map((endpoint) => (
                      <EndpointLink key={endpoint.url} endpoint={endpoint} />
                    ))}
                  </span>
                ) : (
                  <span className="infra__none">{noEndpointReason(container, mode)}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** One web endpoint, as a card. */
function WebServiceCard({ service, mode }: { service: WebService; mode: ReadingMode }) {
  const href = resolveUrl(service.url, service.wildcard_bind)
  const live = service.state === 'running'

  return (
    <li className={live ? 'weburl' : 'weburl weburl--off'}>
      <div className="weburl__head">
        <span className="weburl__service">{service.service}</span>
        <RuntimeBadge status={service.status} label={runtimeLabel(service.status)} />
      </div>

      {live ? (
        <a className="weburl__link" href={href} target="_blank" rel="noreferrer">
          {href}
        </a>
      ) : (
        <span className="weburl__link weburl__link--dead">{href}</span>
      )}

      <p className="weburl__meta">
        <code>{service.container}</code>
        <span>
          {say(mode, 'port', 'host')} {service.host_port} → {service.container_port}
        </span>
        {service.reachable === true ? (
          <span className="weburl__ok">{say(mode, 'answering', 'probe ok')}</span>
        ) : null}
        {service.reachable === false ? (
          <span className="weburl__bad">{say(mode, 'not answering', 'probe refused')}</span>
        ) : null}
      </p>

      <a
        className={live ? 'btn btn--primary weburl__open' : 'btn weburl__open'}
        href={href}
        target="_blank"
        rel="noreferrer"
        aria-disabled={live ? undefined : true}
        onClick={live ? undefined : (event) => event.preventDefault()}
      >
        Open ↗
      </a>
    </li>
  )
}

/**
 * What to say, and what to run, when an environment has nothing in it.
 *
 * An empty state that only says "empty" leaves the reader to work out whether
 * that is expected. The command is the difference between a dead end and a next
 * step, and it is the same command that would populate this tab.
 */
const EMPTY_HINTS: Record<DeploymentEnvironment, { lead: string; command: string }> = {
  development: { lead: 'Start the local stack with', command: 'docker compose up -d' },
  qa: { lead: 'Bring QA up with', command: 'kubectl apply -k k8s/overlays/qa' },
  production: { lead: 'Deploy with', command: 'kubectl apply -k k8s/overlays/production' },
}

/** Props for {@link WebEnvironments}. */
export interface WebEnvironmentsProps {
  snapshot: InfraSnapshot | null
  mode: ReadingMode
}

/**
 * Web endpoints, one tab per environment.
 *
 * All three tabs are always present, including the empty ones. An environment
 * that has nothing running is a fact about the system, and a tab strip that
 * changes shape as services come and go is one the reader has to re-learn every
 * time they look at it.
 *
 * Until the reader picks a tab, the panel shows the first environment that has
 * something in it — opening on content rather than on an empty state they then
 * have to click past. That default is *derived* rather than stored, so it keeps
 * tracking the data as services appear, and stops the moment a tab is clicked.
 */
export function WebEnvironments({ snapshot, mode }: WebEnvironmentsProps) {
  const [selected, setSelected] = useState<DeploymentEnvironment | null>(null)

  if (snapshot === null) return <Empty message="Reading the container runtime…" />

  if (!snapshot.available) {
    return (
      <Empty
        message={`Container runtime unavailable — ${snapshot.reason ?? 'no reason given'}. Endpoints cannot be discovered until it is reachable.`}
      />
    )
  }

  const groups = snapshot.environments
  const active =
    groups.find((group) => group.environment === selected) ??
    groups.find((group) => group.services.length > 0) ??
    groups[0]
  if (!active) return <Empty message="No environments to show." />

  return (
    <div className="envs">
      <div className="envtabs" role="tablist" aria-label="Deployment environment">
        {groups.map((group) => (
          <button
            key={group.environment}
            type="button"
            role="tab"
            id={`envtab-${group.environment}`}
            aria-selected={group.environment === active.environment}
            aria-controls={`envpanel-${group.environment}`}
            className={group.environment === active.environment ? 'envtab envtab--on' : 'envtab'}
            onClick={() => setSelected(group.environment)}
          >
            {group.label}
            <span className={group.services.length ? 'envtab__count' : 'envtab__count envtab__count--zero'}>
              {group.services.length}
            </span>
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`envpanel-${active.environment}`}
        aria-labelledby={`envtab-${active.environment}`}
      >
        {active.services.length ? (
          <ul className="weburls">
            {active.services.map((service) => (
              <WebServiceCard key={`${service.container}-${service.host_port}`} service={service} mode={mode} />
            ))}
          </ul>
        ) : (
          <div className="envempty">
            <p className="envempty__head">No {active.label} services are running.</p>
            <p className="envempty__hint">
              {EMPTY_HINTS[active.environment].lead}{' '}
              <code>{EMPTY_HINTS[active.environment].command}</code>, or label a stack{' '}
              <code>PULSEGRID_ENV={active.environment}</code>.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
