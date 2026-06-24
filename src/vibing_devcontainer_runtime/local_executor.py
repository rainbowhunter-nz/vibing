"""LocalExecutor: vibing_harness.Executor for the in-container runtime — local
subprocess + direct file IO. Home-relative paths join the runtime's $HOME."""

import asyncio
import os
from pathlib import Path

from vibing_harness import CommandResult


class LocalExecutor:
    def __init__(self, home: Path | None = None) -> None:
        self._home = home or Path.home()

    async def run(self, argv: list[str], env: dict[str, str] | None = None) -> CommandResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **env} if env else None,
            )
        except FileNotFoundError:
            return CommandResult(127, "", "binary not found")
        out, err = await proc.communicate()
        return CommandResult(
            proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")
        )

    async def read(self, path: str) -> bytes | None:
        target = self._home / path
        if not target.exists():
            return None
        return target.read_bytes()

    async def write(self, path: str, data: bytes, mode: int = 0o600) -> None:
        target = self._home / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(mode)
