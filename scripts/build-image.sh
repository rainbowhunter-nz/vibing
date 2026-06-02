#!/usr/bin/env bash
set -euo pipefail

# Always run from repo root regardless of where this script is called from
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

IMAGE="${IMAGE:-vibing}"

echo "Building image ${IMAGE}..."
docker build --load -t "$IMAGE" .
echo "Built ${IMAGE}."
