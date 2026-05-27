# Stage 1: build frontend
FROM node:24-slim AS builder
WORKDIR /build
RUN corepack enable
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
RUN corepack install -g pnpm@11.3.0 && pnpm install --frozen-lockfile
COPY apps/web/ ./
RUN pnpm build

# Stage 2: run backend + serve built frontend
FROM python:3.13-slim AS final
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Install Python dependencies (separate layer for cache efficiency)
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/README.md ./
RUN uv sync --no-dev --frozen --no-install-project

# Copy source and complete install
COPY apps/api/src ./src
RUN uv sync --no-dev --frozen

# Copy built frontend assets
COPY --from=builder /build/dist /app/dist

ENV VIBING_DATABASE_URL=sqlite:////data/vibing.db
ENV VIBING_STATIC_DIR=/app/dist
EXPOSE 8080

CMD ["uv", "run", "uvicorn", "vibing_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
