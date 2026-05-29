"""Dev Container CLI adapter.

Shells out to the official `devcontainer` CLI for Devcontainer lifecycle operations
(ADR-0003) — never Docker/Podman SDKs directly. Validates only that `local_path` is an
existing directory; all `devcontainer.json` validation is left to the CLI. Returns a
structured success/failure result that command handling turns into Runtime Events.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_STDERR_TAIL_CHARS = 4000


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str]], Awaitable[RunResult]]


@dataclass(frozen=True)
class DevcontainerSuccess:
    operation: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DevcontainerFailure:
    operation: str
    command: list[str]
    exit_code: int | None
    stderr_tail: str
    message: str


DevcontainerResult = DevcontainerSuccess | DevcontainerFailure


async def _default_runner(command: list[str]) -> RunResult:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return RunResult(
        returncode=process.returncode or 0,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
    )


def _last_json_object(text: str) -> dict[str, Any] | None:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _parse_up_output(stdout: str) -> dict[str, Any]:
    data = _last_json_object(stdout)
    if data is None:
        return {}
    mapping = {
        "container_id": "containerId",
        "remote_user": "remoteUser",
        "remote_workspace_folder": "remoteWorkspaceFolder",
    }
    return {key: data[source] for key, source in mapping.items() if source in data}


class DevcontainerCliAdapter:
    """Maps start/stop to `devcontainer up`/`stop` via an injectable runner."""

    def __init__(self, cli: str = "devcontainer", *, runner: Runner | None = None) -> None:
        self._cli = cli
        self._runner = runner or _default_runner

    async def start(self, local_path: str) -> DevcontainerResult:
        return await self._run("start", ["up", "--workspace-folder", local_path], local_path)

    async def stop(self, local_path: str) -> DevcontainerResult:
        return await self._run("stop", ["stop", "--workspace-folder", local_path], local_path)

    async def _run(self, operation: str, args: list[str], local_path: str) -> DevcontainerResult:
        command = [self._cli, *args]
        if not Path(local_path).is_dir():
            return DevcontainerFailure(
                operation=operation,
                command=command,
                exit_code=None,
                stderr_tail="",
                message=f"local_path is not an existing directory: {local_path}",
            )
        try:
            result = await self._runner(command)
        except FileNotFoundError:
            return DevcontainerFailure(
                operation=operation,
                command=command,
                exit_code=None,
                stderr_tail="",
                message=f"Dev Container CLI not found: {self._cli}",
            )
        if result.returncode != 0:
            return DevcontainerFailure(
                operation=operation,
                command=command,
                exit_code=result.returncode,
                stderr_tail=result.stderr[-_STDERR_TAIL_CHARS:],
                message=f"devcontainer {operation} failed with exit code {result.returncode}",
            )
        payload = _parse_up_output(result.stdout) if operation == "start" else {}
        return DevcontainerSuccess(operation=operation, payload=payload)
