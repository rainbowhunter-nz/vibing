"""ClaudeCodeRunner: runs `claude` as a subprocess, injectable runner for tests."""

import asyncio
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from logzero import logger
from vibing_protocol import extract_claude_result_text

_STDERR_TAIL_CHARS = 4000
_LOG_PREVIEW_CHARS = 500
_SIGTERM_GRACE_SECONDS = 5.0


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


def _preview(text: str, limit: int = _LOG_PREVIEW_CHARS) -> str:
    collapsed = text.replace("\n", "\\n")
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[:limit]}... ({len(text)} chars total)"


def _log_run_result(command: list[str], cwd: str | None, result: RunResult) -> None:
    logger.info(
        "Claude subprocess finished (exit_code=%d, stdout_len=%d, stderr_len=%d, cwd=%s)",
        result.returncode,
        len(result.stdout),
        len(result.stderr),
        cwd,
    )
    logger.info("Claude command: %s", " ".join(command))
    if result.stdout:
        logger.info("Claude stdout: %s", _preview(result.stdout))
    if result.stderr:
        logger.info("Claude stderr: %s", _preview(result.stderr))


def _map_run_result(result: RunResult) -> ClaudeResult:
    if result.returncode != 0:
        return ClaudeFailure(
            exit_code=result.returncode,
            stderr_tail=result.stderr[-_STDERR_TAIL_CHARS:],
            message=f"claude exited with code {result.returncode}",
        )
    return ClaudeSuccess(result=extract_claude_result_text(result.stdout))


class ClaudeProcess:
    """Handle to a running (or fake) Claude process.

    Subclasses implement wait() and terminate() — real subprocess or test fake.
    """

    async def wait(self) -> ClaudeResult:
        raise NotImplementedError

    async def terminate(self) -> None:
        raise NotImplementedError


class _RealClaudeProcess(ClaudeProcess):
    """Wraps a real asyncio.subprocess.Process."""

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self._proc = proc

    async def wait(self) -> ClaudeResult:
        stdout_b, stderr_b = await self._proc.communicate()
        returncode = self._proc.returncode or 0
        return _map_run_result(
            RunResult(
                returncode=returncode,
                stdout=stdout_b.decode(errors="replace"),
                stderr=stderr_b.decode(errors="replace"),
            )
        )

    async def terminate(self) -> None:
        if self._proc.returncode is not None:
            return
        try:
            self._proc.send_signal(signal.SIGTERM)
            await asyncio.wait_for(self._proc.wait(), timeout=_SIGTERM_GRACE_SECONDS)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                self._proc.kill()
            except ProcessLookupError:
                pass


class _FakeRunnerProcess(ClaudeProcess):
    """Wraps an injectable Runner callable as a ClaudeProcess for testing."""

    def __init__(self, command: list[str], runner: Runner) -> None:
        self._command = command
        self._runner = runner

    async def wait(self) -> ClaudeResult:
        try:
            result = await self._runner(self._command)
        except FileNotFoundError:
            return ClaudeFailure(exit_code=None, stderr_tail="", message="claude binary not found")
        return _map_run_result(result)

    async def terminate(self) -> None:
        pass  # fake; test override handles cancellation if needed


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

    def _build_command(
        self, prompt: str, session_id: str | None = None, resume: bool = False
    ) -> list[str]:
        cmd = [
            self._binary,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--permission-mode",
            "bypassPermissions",
        ]
        if session_id is not None:
            # ADR-0008: resume continues the same on-disk thread via --resume; a fresh
            # run names the session via --session-id. Never both (and no --fork-session).
            cmd += ["--resume", session_id] if resume else ["--session-id", session_id]
        return cmd

    def start(
        self, prompt: str, session_id: str | None = None, resume: bool = False
    ) -> ClaudeProcess:
        """Return a ClaudeProcess handle. For the injected-runner path, returns synchronously."""
        command = self._build_command(prompt, session_id, resume)
        if self._runner is not None:
            return _FakeRunnerProcess(command, self._runner)
        return _LazyRealProcess(command, self._cwd)

    async def run(
        self, prompt: str, session_id: str | None = None, resume: bool = False
    ) -> ClaudeResult:
        """Convenience wrapper: start() + wait()."""
        return await self.start(prompt, session_id, resume).wait()


class _LazyRealProcess(ClaudeProcess):
    """Launches the real subprocess lazily on first wait() call."""

    def __init__(self, command: list[str], cwd: str | None) -> None:
        self._command = command
        self._cwd = cwd
        self._proc: asyncio.subprocess.Process | None = None

    async def wait(self) -> ClaudeResult:
        logger.info("Launching claude subprocess (cwd=%s): %s", self._cwd, " ".join(self._command))
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self._command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
            )
            stdout_b, stderr_b = await self._proc.communicate()
        except FileNotFoundError:
            logger.warning("Claude binary not found: %s", self._command[0])
            return ClaudeFailure(exit_code=None, stderr_tail="", message="claude binary not found")
        returncode = self._proc.returncode or 0
        run_result = RunResult(
            returncode=returncode,
            stdout=stdout_b.decode(errors="replace"),
            stderr=stderr_b.decode(errors="replace"),
        )
        _log_run_result(self._command, self._cwd, run_result)
        return _map_run_result(run_result)

    async def terminate(self) -> None:
        if self._proc is None or self._proc.returncode is not None:
            return
        try:
            self._proc.send_signal(signal.SIGTERM)
            await asyncio.wait_for(self._proc.wait(), timeout=_SIGTERM_GRACE_SECONDS)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                self._proc.kill()
            except ProcessLookupError:
                pass
