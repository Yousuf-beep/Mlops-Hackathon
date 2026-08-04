# Kubernetes manifests

Plain YAML with Kustomize, no Helm. The stack is four workloads with almost no
per-environment templating, so a chart would add a values file, a template
language and a release lifecycle to express what `kubectl apply -k` already
expresses.

## Layout: one base, three environments

```
k8s/
├── kustomization.yaml        # repo-root pointer → overlays/production (the default)
├── base/                     # every workload, no environment opinions
└── overlays/
    ├── production/           # = base, plus the GHCR image tag
    ├── qa/                   # separate namespace, smaller HPA ceiling, qa.pulsegrid.local
    └── dev/                  # separate namespace, no HPA, 1 replica everywhere, DEBUG logs
```

**Production is the default.** `kubectl apply -k k8s/` resolves through the
root pointer to `overlays/production` — the same way `git checkout main` gets
you `main` without naming it. The base manifests were already written as the
production configuration (2 API/web replicas, HPA, prod-sized resource
requests), so the production overlay adds almost nothing on top; it exists so
"production" has an explicit, named target next to `qa` and `dev` rather than
being an implicit default no overlay actually owns.

## Apply

```bash
# Production (the default)
kubectl apply -k k8s/
kubectl -n pulsegrid rollout status deploy/pulsegrid-api
kubectl -n pulsegrid port-forward svc/pulsegrid-web 8080:80

# QA
kubectl apply -k k8s/overlays/qa
kubectl -n pulsegrid-qa rollout status deploy/pulsegrid-api

# Dev
kubectl apply -k k8s/overlays/dev
kubectl -n pulsegrid-dev rollout status deploy/pulsegrid-api
```

Then open <http://localhost:8080>. To see what an overlay actually changes
before applying it: `kubectl kustomize k8s/overlays/qa | less`, or diff two
overlays directly with `diff <(kubectl kustomize k8s/overlays/qa) <(kubectl kustomize k8s/overlays/dev)`.

## What differs between the three

| | `production` | `qa` | `dev` |
| --- | --- | --- | --- |
| Namespace | `pulsegrid` | `pulsegrid-qa` | `pulsegrid-dev` |
| Ingress host | `pulsegrid.local` | `qa.pulsegrid.local` | `dev.pulsegrid.local` |
| API / web replicas | 2 | 1 | 1 |
| HPA | 2–8, CPU 70% | 1–3, CPU 70% | none — nothing to scale on 1 replica |
| API / web image | `ghcr.io/…/mlops-hackathon:latest` / `…-web:latest` (CI-published) | `pulsegrid-api:dev` / `pulsegrid-web:dev` (locally built) | same as `qa` |
| `ENV` | `prod` | `qa` | `dev` |
| `LOG_LEVEL` | `INFO` | `INFO` | `DEBUG` |
| API request sizing | 100m / 512Mi | 100m / 512Mi (unchanged — QA should behave like prod) | 50m / 256Mi |

`DEMO_AUTOSEED` stays on in all three: every environment needs something to
show on first boot, and the seeded demo APIs plus the k6 loadgen
(`load/k6/traffic.js`, run via `docker compose`, not deployed to the cluster)
are what make that traffic real rather than static. Turn it off with a patch
in whichever overlay first points at a real upstream.

**Both images are published.** `.github/workflows/ci.yml`'s `docker` job runs
as a two-way matrix: `api` (from `backend/Dockerfile`, also what
`pulsegrid-demo-target` runs — one image, two entrypoints) and `web` (from
`frontend/Dockerfile`), each to its own GHCR package
(`ghcr.io/<repo>` and `ghcr.io/<repo>-web`), tagged with the commit SHA and
`latest` on every push to `main`. `qa` and `dev` still run the locally-built
`:dev` tags on purpose — they're meant to run whatever you have on disk, not
force a registry round-trip for a throwaway environment.

## What is in `base/`

| File | Contents |
| --- | --- |
| `00-namespace.yaml` | The namespace object (renamed per-overlay by Kustomize's `namespace:` field) |
| `01-config.yaml` | Non-secret configuration; a Secret carries credentials |
| `10-postgres.yaml` | StatefulSet + headless Service + a 10Gi volume claim |
| `20-api.yaml` | API Deployment and Service, with migrations in an init container |
| `30-demo-target.yaml` | The synthetic upstream, so a cluster install has something to monitor |
| `40-web.yaml` | The dashboard behind nginx, which also reverse-proxies `/v1` to the API |
| `50-ingress.yaml` | Single host, routing everything to the web Service |
| `60-hpa.yaml` | CPU-based autoscaling for the API (removed entirely in `dev`) |
| `kustomization.yaml` | Resource list and the base image tags each overlay overrides |

## Decisions worth knowing

**PostgreSQL is a StatefulSet with one replica, not a Deployment.** A Deployment
would let two pods mount the same volume during a rolling update and corrupt the
data directory; the StatefulSet's ordered, at-most-one guarantee is exactly what
prevents that. For anything past a demo, use a managed database instead — this
manifest exists so the stack is *complete*, not because self-hosting PostgreSQL
in-cluster is a good idea.

**Migrations run in an init container, not in the app command.** With
`replicas: 2`, putting `alembic upgrade head` in the container command runs it
once per replica, concurrently, against the same schema. The init container
still runs per pod, but it completes before the server binds, so a pod never
serves traffic against a schema it does not expect, and Alembic's version table
makes the second run a no-op.

**The API runs two replicas while the scheduler is in-process.** That means the
rollup and probe jobs run twice per interval. The rollup is idempotent by design
(see `backend/app/jobs/rollup.py`), so double execution is harmless, and the
prober simply probes twice as often. If you scale past a handful of replicas,
set `SCHEDULER_ENABLED=false` on this Deployment and run one single-replica
scheduler Deployment beside it — the switch already exists in `app/config.py`.

**Probes point at `/health`, which performs a real `SELECT 1`.** Readiness
therefore means "can actually serve queries", not "process is up". Liveness is
given a slower period so a brief database blip pulls the pod out of the Service
without also restarting it.

**nginx proxies the API rather than the browser calling it cross-origin.** The
dashboard uses relative paths, so one origin serves both — which keeps CORS out
of the picture and, importantly, lets `text/event-stream` through unbuffered
(`proxy_buffering off`). An ingress that buffers the stream is the classic way a
live dashboard silently stops being live.
