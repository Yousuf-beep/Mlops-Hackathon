# Kubernetes manifests

Plain YAML with Kustomize, no Helm. The stack is four workloads with almost no
per-environment templating, so a chart would add a values file, a template
language and a release lifecycle to express what `kubectl apply -k` already
expresses. Kustomize covers the one thing that *does* vary — image tags —
without any of that.

## Apply

```bash
kubectl apply -k k8s/
kubectl -n pulsegrid rollout status deploy/pulsegrid-api
kubectl -n pulsegrid port-forward svc/pulsegrid-web 8080:80
```

Then open <http://localhost:8080>.

## What is in here

| File | Contents |
| --- | --- |
| `00-namespace.yaml` | The `pulsegrid` namespace |
| `01-config.yaml` | Non-secret configuration; a Secret carries credentials |
| `10-postgres.yaml` | StatefulSet + headless Service + a 10Gi volume claim |
| `20-api.yaml` | API Deployment and Service, with migrations in an init container |
| `30-demo-target.yaml` | The synthetic upstream, so a cluster install has something to monitor |
| `40-web.yaml` | The dashboard behind nginx, which also reverse-proxies `/v1` to the API |
| `50-ingress.yaml` | Single host, routing everything to the web Service |
| `60-hpa.yaml` | CPU-based autoscaling for the API |
| `kustomization.yaml` | Apply order and the image tags to override |

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
