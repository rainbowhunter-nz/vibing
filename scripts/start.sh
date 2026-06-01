#!/usr/bin/env bash
set -euo pipefail

# Always run from repo root regardless of where this script is called from
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

IMAGE=vibing
CONTAINER=vibing
PORT=8080

if [[ "${1:-}" == "--stop" ]]; then
  echo "Stopping container..."
  docker rm -f "$CONTAINER" 2>/dev/null || true
  echo "Stopped."
  exit 0
fi

echo "Building image..."
docker build --load -t "$IMAGE" .

echo "Starting container..."
docker rm -f "$CONTAINER" 2>/dev/null || true
docker run -d \
  --name "$CONTAINER" \
  -p "${PORT}:${PORT}" \
  -v vibing-data:/data \
  "$IMAGE"

# Reach the published port via host.docker.internal (docker-outside-of-docker)
HEALTH="http://host.docker.internal:${PORT}/api/v1/health"
echo "Waiting for Vibing to become ready..."
for _ in $(seq 1 30); do
  if curl -fsS "$HEALTH" >/dev/null 2>&1; then
    echo "Vibing is running at http://localhost:${PORT}"
    exit 0
  fi
  sleep 1
done

echo "Vibing did not become ready in time. Recent logs:" >&2
docker logs --tail 30 "$CONTAINER" >&2
exit 1
