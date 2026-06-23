"""Subprocess seam for harness commands.

One factory builds a HarnessProcess from (argv, cwd, extra_env); production runs a real
subprocess, tests inject a fake. Adapters use run_to_completion for short commands
(install / auth-check); the DelegatedRunManager keeps the HarnessProcess to terminate it.
"""

import asyncio
import os
import signal
from collections.abc import Callable
from dataclasses import dataclass

_SIGTERM_GRACE_SECONDS = 5.0


@dataclass(frozen=True)
class CompletedCommand:
    returncode: int
    stdout: str
    stderr: str


class HarnessProcess:
    """Handle to a running (or fake) harness subprocess."""

    async def wait(self) -> CompletedCommand:
        raise NotImplementedError

    async def terminate(self) -> None:
        raise NotImplementedError


HarnessProcessFactory = Callable[[list[str], str | None, dict[str, str] | None], HarnessProcess]


class _RealProcess(HarnessProcess):
    def __init__(self, argv: list[str], cwd: str | None, env: dict[str, str] | None) -> None:
        self._argv = argv
        self._cwd = cwd
        self._env = {**os.environ, **env} if env else None
        self._proc: asyncio.subprocess.Process | None = None

    async def wait(self) -> CompletedCommand:
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self._argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
                env=self._env,
            )
        except FileNotFoundError:
            return CompletedCommand(returncode=127, stdout="", stderr="binary not found")
        out_b, err_b = await self._proc.communicate()
        return CompletedCommand(
            returncode=self._proc.returncode or 0,
            stdout=out_b.decode(errors="replace"),
            stderr=err_b.decode(errors="replace"),
        )

    async def terminate(self) -> None:
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        try:
            proc.send_signal(signal.SIGTERM)
            await asyncio.wait_for(proc.wait(), timeout=_SIGTERM_GRACE_SECONDS)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass


def real_process_factory(
    argv: list[str], cwd: str | None, env: dict[str, str] | None
) -> HarnessProcess:
    return _RealProcess(argv, cwd, env)


async def run_to_completion(
    factory: HarnessProcessFactory,
    argv: list[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> CompletedCommand:
    return await factory(argv, cwd, env).wait()
