#!/usr/bin/env bash
set -euo pipefail

# Always run from repo root regardless of where this script is called from
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

IMAGE="${IMAGE:-vibing}"

echo "Building image ${IMAGE}..."
# Disable BuildKit: the buildx docker-container driver boots a BuildKit
# container that fails under the host's podman/netavark networking. The
# Dockerfile uses no BuildKit features, so the native builder suffices.
DOCKER_BUILDKIT=0 docker build -t "$IMAGE" .
echo "Built ${IMAGE}."
