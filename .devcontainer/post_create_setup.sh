#!/usr/bin/env bash
set -euo pipefail

CLAUDE_DIR="/home/vscode/.claude"
CLAUDE_JSON_LINK="/home/vscode/.claude.json"
CLAUDE_JSON_TARGET="$CLAUDE_DIR/.claude.json"

mkdir -p "$CLAUDE_DIR"

# If Claude already created a real ~/.claude.json, preserve it.
if [ -f "$CLAUDE_JSON_LINK" ] && [ ! -L "$CLAUDE_JSON_LINK" ] && [ ! -e "$CLAUDE_JSON_TARGET" ]; then
  mv "$CLAUDE_JSON_LINK" "$CLAUDE_JSON_TARGET"
fi

# If no persisted file exists yet, create a valid empty JSON object.
if [ ! -e "$CLAUDE_JSON_TARGET" ]; then
  printf '{}\n' > "$CLAUDE_JSON_TARGET"
fi

# Replace ~/.claude.json with a symlink into the persisted .claude volume.
rm -f "$CLAUDE_JSON_LINK"
ln -s "$CLAUDE_JSON_TARGET" "$CLAUDE_JSON_LINK"


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
sudo chown -h vscode:vscode "$CLAUDE_JSON_LINK"

uv run .devcontainer/sync-claude-statusline.py