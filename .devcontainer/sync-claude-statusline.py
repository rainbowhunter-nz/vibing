#!/usr/bin/env python3

import json
import os
import shlex
import shutil
import stat
from pathlib import Path


HOST_CLAUDE_DIR = Path(os.environ.get("HOST_CLAUDE_MOUNT", "/mnt/host-claude"))
CONTAINER_HOME = Path(os.environ.get("CONTAINER_HOME", "/home/vscode"))

HOST_SETTINGS = HOST_CLAUDE_DIR / "settings.json"
CONTAINER_CLAUDE_DIR = CONTAINER_HOME / ".claude"
CONTAINER_SETTINGS = CONTAINER_CLAUDE_DIR / "settings.json"

INTERPRETERS = {
    "bash",
    "sh",
    "zsh",
    "python",
    "python3",
    "node",
    "bun",
    "deno",
}


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        backup = path.with_suffix(path.suffix + ".invalid.bak")
        shutil.copy2(path, backup)
        print(f"Warning: invalid JSON at {path}; backed up to {backup}")
        return {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def looks_like_script_path(value: str) -> bool:
    return (
        value.startswith("~/")
        or value.startswith("$HOME/")
        or value.startswith("${HOME}/")
        or value.startswith("/")
        or value.startswith("./")
        or value.startswith("../")
        or "/" in value
    )


def find_script_token(tokens: list[str]) -> int | None:
    if not tokens:
        return None

    # Example:
    #   ~/.claude/statusline-command.sh
    #   /home/hank/.claude/statusline-command.sh
    if looks_like_script_path(tokens[0]):
        return 0

    # Example:
    #   bash ~/.claude/statusline-command.sh
    #   python3 /home/hank/.claude/statusline.py
    if Path(tokens[0]).name in INTERPRETERS:
        for index, token in enumerate(tokens[1:], start=1):
            if token.startswith("-"):
                continue

            if looks_like_script_path(token):
                return index

    return None


def main() -> None:
    host_settings = read_json(HOST_SETTINGS)
    host_statusline = host_settings.get("statusLine")

    if not isinstance(host_statusline, dict):
        print(f"No statusLine found in {HOST_SETTINGS}; nothing to sync.")
        return

    command = host_statusline.get("command")

    if not isinstance(command, str) or not command.strip():
        print("Host statusLine.command is empty; nothing to sync.")
        return

    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        print(f"Could not parse host statusLine.command: {exc}")
        print("Leaving container statusLine unchanged.")
        return

    script_index = find_script_token(tokens)

    if script_index is None:
        print("Could not identify a statusline script file in host statusLine.command.")
        print(f"Command was: {command}")
        print("This script only supports file-based statusline commands.")
        return

    # Important simplification:
    # We assume the real host statusline script is directly inside host ~/.claude.
    # So for /home/hank/.claude/statusline-command.sh, we only keep:
    #   statusline-command.sh
    script_basename = Path(tokens[script_index]).name

    if not script_basename:
        print(f"Could not determine script basename from: {tokens[script_index]}")
        return

    host_script = HOST_CLAUDE_DIR / script_basename

    if not host_script.exists() or not host_script.is_file():
        print(f"Could not find host statusline script:")
        print(f"  expected: {host_script}")
        print(f"  from command: {command}")
        return

    CONTAINER_CLAUDE_DIR.mkdir(parents=True, exist_ok=True)

    container_script = CONTAINER_CLAUDE_DIR / script_basename
    shutil.copy2(host_script, container_script)

    mode = container_script.stat().st_mode
    container_script.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Replace only the script path, keeping the interpreter and any extra args.
    #
    # Example:
    #   bash /home/hank/.claude/statusline-command.sh
    #
    # becomes:
    #   bash /home/vscode/.claude/statusline-command.sh
    tokens[script_index] = str(container_script)
    container_command = shlex.join(tokens)

    container_settings = read_json(CONTAINER_SETTINGS)

    new_statusline = dict(host_statusline)
    new_statusline["type"] = "command"
    new_statusline["command"] = container_command

    container_settings["statusLine"] = new_statusline
    write_json(CONTAINER_SETTINGS, container_settings)

    print("Synced Claude statusline script.")
    print(f"  host settings:      {HOST_SETTINGS}")
    print(f"  host script:        {host_script}")
    print(f"  container script:   {container_script}")
    print(f"  container settings: {CONTAINER_SETTINGS}")
    print(f"  container command:  {container_command}")


if __name__ == "__main__":
    main()