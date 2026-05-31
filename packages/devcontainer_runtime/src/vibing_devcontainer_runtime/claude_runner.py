"""ClaudeCodeRunner: runs `claude` as a subprocess, injectable runner for tests."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

_STDERR_TAIL_CHARS = 4000


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str]], Awaitable[RunResult]]


@dataclass(frozen=True)
class ClaudeSuccess:
    result: str


@dataclass(frozen=True)
class ClaudeFailure:
    exit_code: int | None
    stderr_tail: str
    message: str


ClaudeResult = ClaudeSuccess | ClaudeFailure


async def _default_runner(command: list[str], cwd: str | None = None) -> RunResult:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await process.communicate()
    return RunResult(
        returncode=process.returncode or 0,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
    )


class ClaudeCodeRunner:
    """Runs `claude -p <prompt> --output-format json --permission-mode bypassPermissions`.

    Uses bypassPermissions because approval detection is deferred to the
    --permission-prompt-tool integration (future work).
    """

    def __init__(
        self,
        binary: str = "claude",
        cwd: str | None = None,
        runner: Runner | None = None,
    ) -> None:
        self._binary = binary
        self._cwd = cwd
        self._runner = runner

    def _build_command(self, prompt: str) -> list[str]:
        return [
            self._binary,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--permission-mode",
            "bypassPermissions",
        ]

    async def run(self, prompt: str) -> ClaudeResult:
        command = self._build_command(prompt)
        try:
            if self._runner is not None:
                result = await self._runner(command)
            else:
                result = await _default_runner(command, self._cwd)
        except FileNotFoundError:
            return ClaudeFailure(exit_code=None, stderr_tail="", message="claude binary not found")
        if result.returncode != 0:
            return ClaudeFailure(
                exit_code=result.returncode,
                stderr_tail=result.stderr[-_STDERR_TAIL_CHARS:],
                message=f"claude exited with code {result.returncode}",
            )
        return ClaudeSuccess(result=result.stdout)
