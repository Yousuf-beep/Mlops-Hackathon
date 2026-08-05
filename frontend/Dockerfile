# Multi-stage: Node builds the bundle, nginx serves it. The runtime image
# carries no Node, no node_modules and no source — a few megabytes of static
# files and a web server, which is the entire attack surface it needs.

# --- build ------------------------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /app

# Dependencies are installed from the lockfile alone, so this layer is reused
# on every build that does not change a dependency.
COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig*.json vite.config.ts index.html ./
COPY public ./public
COPY src ./src

RUN npm run build

# --- runtime ----------------------------------------------------------------
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime

# The unprivileged image already runs as uid 101 and binds 8080, so no root and
# no capability juggling to listen on a low port.
COPY --from=build /app/dist /usr/share/nginx/html

# The base image's entrypoint runs envsubst over /etc/nginx/templates, which is
# how one image serves both compose and Kubernetes without a rebuild.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

ENV API_UPSTREAM=http://api:8000

# Makes the base image's entrypoint export NGINX_LOCAL_RESOLVERS from the
# container's own /etc/resolv.conf, which nginx.conf.template needs for its
# `resolver` directive. Without this the variable is empty and the generated
# config is invalid, so it is not optional.
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=4s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/index.html >/dev/null || exit 1
