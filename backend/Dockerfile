# syntax=docker/dockerfile:1
#
# Multi-stage build for the PulseGrid backend.
#
# Stage 1 resolves and installs dependencies with uv into a self-contained
# virtualenv at /opt/venv. Stage 2 copies only that virtualenv plus the source,
# so no build tooling, no uv and no wheel cache reach the runtime image.
#
# The virtualenv deliberately lives *outside* /app: docker-compose bind-mounts
# the host's ./backend over /app for hot reload, and anything installed under
# /app would be shadowed by that mount.

# --------------------------------------------------------------------------- #
# Stage 1 — builder                                                            #
# --------------------------------------------------------------------------- #
FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

RUN pip install --no-cache-dir uv

WORKDIR /build

# Only the manifest is copied first, so the (slow) dependency layer is reused
# whenever application code changes but dependencies do not.
COPY pyproject.toml ./

RUN uv venv /opt/venv \
    && VIRTUAL_ENV=/opt/venv uv pip install --no-cache -r pyproject.toml

# --------------------------------------------------------------------------- #
# Stage 2 — runtime                                                            #
# --------------------------------------------------------------------------- #
FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="PulseGrid backend" \
      org.opencontainers.image.description="Enterprise API analytics and performance-management platform" \
      org.opencontainers.image.licenses="MIT"

ENV PATH="/opt/venv/bin:${PATH}" \
    VIRTUAL_ENV=/opt/venv \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Run as an unprivileged user: a compromised proxy handler should not be root.
RUN groupadd --system --gid 1001 pulsegrid \
    && useradd --system --uid 1001 --gid pulsegrid --create-home pulsegrid

COPY --from=builder --chown=pulsegrid:pulsegrid /opt/venv /opt/venv

WORKDIR /app
COPY --chown=pulsegrid:pulsegrid . .

USER pulsegrid

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
