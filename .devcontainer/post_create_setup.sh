#!/usr/bin/env bash
set -euo pipefail

CLAUDE_DIR="/home/vscode/.claude"
CLAUDE_JSON_LINK="/home/vscode/.claude.json"
CLAUDE_JSON_TARGET="$CLAUDE_DIR/.claude.json"

if command -v curl >/dev/null 2>&1; then
  TZ_NAME="$(curl -fsSL --max-time 3 https://ipapi.co/timezone || true)"

  if [ -n "$TZ_NAME" ] && [ -f "/usr/share/zoneinfo/$TZ_NAME" ]; then
    sudo ln -snf "/usr/share/zoneinfo/$TZ_NAME" /etc/localtime
    echo "$TZ_NAME" | sudo tee /etc/timezone >/dev/null || true
    echo "[timezone] Set timezone to $TZ_NAME"
  else
    echo "[timezone] Could not detect/apply timezone. Keeping default timezone."
  fi
else
  echo "[timezone] curl not found. Keeping default timezone."
fi

# Ensure the vscode user can read/write the persisted files.
sudo chown -R vscode:vscode "$CLAUDE_DIR"

# Setup .claude.json for persistence auth.
if [ ! -e "$CLAUDE_JSON_TARGET" ]; then printf '{}\n' > "$CLAUDE_JSON_TARGET"; fi
ln -s "$CLAUDE_JSON_TARGET" "$CLAUDE_JSON_LINK"

uv run .devcontainer/sync-claude-statusline.py