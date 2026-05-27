#!/usr/bin/env bash
set -euo pipefail

# Always run from repo root regardless of where this script is called from
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

IMAGE=vibing
CONTAINER=vibing
PORT=8080

echo "Building image..."
docker build -t "$IMAGE" .

echo "Starting container..."
docker rm -f "$CONTAINER" 2>/dev/null || true
docker run -d \
  --name "$CONTAINER" \
  -p "${PORT}:${PORT}" \
  -v vibing-data:/data \
  "$IMAGE"

echo "Vibing is running at http://localhost:${PORT}"
