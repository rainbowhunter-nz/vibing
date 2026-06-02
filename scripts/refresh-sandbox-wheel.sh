#!/usr/bin/env bash
# Rebuild the vibing wheel and drop it into the sandbox devcontainer build context.
# Run after changing src/ so the test container picks up new code (then rebuild the container).
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
wheels_dir="$repo_root/test_projects/sandbox/.devcontainer/wheels"

cd "$repo_root"
uv build --wheel
rm -f "$wheels_dir"/*.whl
cp dist/vibing-*.whl "$wheels_dir"/
echo "Refreshed: $(ls "$wheels_dir"/*.whl)"
