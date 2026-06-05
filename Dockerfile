# Stage 1: build frontend
FROM node:24-slim AS builder
WORKDIR /build
RUN corepack enable && corepack install -g pnpm@11.3.0
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web/ ./
RUN pnpm build

# Stage 2: run backend + host-runtime + serve built frontend
FROM python:3.13-slim AS final
COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /usr/local/bin/uv

# Node 24 (for the Dev Container CLI) — same glibc base, safe to copy in.
COPY --from=node:24-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:24-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm

# docker CLI client — the Dev Container CLI drives the mounted daemon socket through it.
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker

# git (devcontainer features), supervisor (runs both processes).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git supervisor \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @devcontainers/cli \
    && npm cache clean --force

WORKDIR /repo

# Install Python dependencies (separate layer for cache efficiency)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen --no-install-project

# Copy source and complete install
COPY src ./src
RUN uv sync --no-dev --frozen

# Build a copyable wheel for injection into arbitrary devcontainers (VIB-98)
RUN uv build --wheel --out-dir /opt/vibing/wheels

# Copy built frontend assets
COPY --from=builder /build/dist ./dist

# Process manager config
COPY deploy/supervisord.conf /etc/supervisor/conf.d/vibing.conf

ENV VIBING_DATABASE_URL=sqlite:////data/vibing.db
ENV VIBING_STATIC_DIR=/repo/dist
ENV VIBING_CONTROL_PLANE_URL=ws://127.0.0.1:8080/api/v1/runtime/ws
ENV VIBING_AGENT_CONTROL_PLANE_URL=ws://host.docker.internal:8080/api/v1/runtime/agent/ws
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
VOLUME /data

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/vibing.conf"]
