# Stage 1: build frontend
FROM node:24-slim AS builder
WORKDIR /build
RUN corepack enable && corepack install -g pnpm@11.3.0
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web/ ./
RUN pnpm build

# Stage 2: run backend + serve built frontend
FROM python:3.13-slim AS final
COPY --from=ghcr.io/astral-sh/uv:0.7.8 /uv /usr/local/bin/uv
# Mirror the repo layout so apps/api's ../../packages path deps resolve
WORKDIR /repo/apps/api

# Workspace path dependencies (vibing-host-runtime, vibing-protocol)
COPY packages /repo/packages

# Install Python dependencies (separate layer for cache efficiency)
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/README.md ./
RUN uv sync --no-dev --frozen --no-install-project

# Copy source and complete install
COPY apps/api/src ./src
RUN uv sync --no-dev --frozen

# Copy built frontend assets
COPY --from=builder /build/dist ./dist

ENV VIBING_DATABASE_URL=sqlite:////data/vibing.db
ENV VIBING_STATIC_DIR=/repo/apps/api/dist
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
VOLUME /data

CMD ["uv", "run", "uvicorn", "vibing_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
