"""ClaudeCodeRunner: runs `claude` as a streaming subprocess, injectable for tests.

ADR-0010: the invocation is incremental `--output-format stream-json --verbose
--include-partial-messages`, read line-by-line. Each line is normalized (see
stream_normalizer) into turn-deltas that flow to an `on_delta` callback as they
arrive; the terminal `result` event drives the success/failure mapping that produces
session_completed/session_failed. `--resume`/`--session-id` semantics (ADR-0008) are
unchanged. The injectable seam yields a SEQUENCE of stream-json lines so a fake can
emit deltas, not just a final result.
"""

import asyncio
import signal
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from logzero import logger
from vibing_protocol import TurnDelta

from vibing_devcontainer_runtime.stream_normalizer import StreamNormalizer, TerminalResult

_STDERR_TAIL_CHARS = 4000
_SIGTERM_GRACE_SECONDS = 5.0

# Test seam: given the command, yield Claude's stdout stream-json lines in order.
StreamRunner = Callable[[list[str]], AsyncIterator[str]]

# Per-delta callback invoked as deltas are normalized off the stream.
OnDelta = Callable[[TurnDelta], Awaitable[None]]


@dataclass(frozen=True)
class ClaudeSuccess:
    result: str


@dataclass(frozen=True)
class ClaudeFailure:
    exit_code: int | None
    stderr_tail: str
    message: str


ClaudeResult = ClaudeSuccess | ClaudeFailure


def _map_terminal(terminal: TerminalResult | None, returncode: int, stderr: str) -> ClaudeResult:
    """Map the stream's terminal result + exit code to success/failure."""
    if terminal is not None and not terminal.is_error and returncode == 0:
        return ClaudeSuccess(result=terminal.result_text)
    if terminal is not None and terminal.is_error:
        return ClaudeFailure(
            exit_code=returncode,
            stderr_tail=stderr[-_STDERR_TAIL_CHARS:],
            message="claude reported an error result",
        )
    if returncode != 0:
        return ClaudeFailure(
            exit_code=returncode,
            stderr_tail=stderr[-_STDERR_TAIL_CHARS:],
            message=f"claude exited with code {returncode}",
        )
    # Exit 0 but no result event: the run did not complete cleanly.
    return ClaudeFailure(
        exit_code=returncode,
        stderr_tail=stderr[-_STDERR_TAIL_CHARS:],
        message="claude stream ended without a result event",
    )


async def _drain(lines: AsyncIterator[str], on_delta: OnDelta) -> TerminalResult | None:
    """Feed each line through the normalizer, dispatching deltas as they arrive."""
    normalizer = StreamNormalizer()
    terminal: TerminalResult | None = None
    async for line in lines:
        normalized = normalizer.feed(line)
        for delta in normalized.deltas:
            await on_delta(delta)
        if normalized.terminal is not None:
            terminal = normalized.terminal
    return terminal


class ClaudeProcess:
    """Handle to a running (or fake) Claude process.

    Subclasses implement wait() and terminate() — real subprocess or test fake.
    """

    async def wait(self, on_delta: OnDelta) -> ClaudeResult:
        raise NotImplementedError

    async def terminate(self) -> None:
        raise NotImplementedError


class _FakeRunnerProcess(ClaudeProcess):
    """Wraps an injectable StreamRunner as a ClaudeProcess for testing."""

    def __init__(self, command: list[str], runner: StreamRunner) -> None:
        self._command = command
        self._runner = runner

    async def wait(self, on_delta: OnDelta) -> ClaudeResult:
        try:
            terminal = await _drain(self._runner(self._command), on_delta)
        except FileNotFoundError:
            return ClaudeFailure(exit_code=None, stderr_tail="", message="claude binary not found")
        return _map_terminal(terminal, returncode=0, stderr="")

    async def terminate(self) -> None:
        pass  # fake; test override handles cancellation if needed


class ClaudeCodeRunner:
    """Runs `claude -p <prompt> --output-format stream-json --verbose
    --include-partial-messages --permission-mode bypassPermissions`.

    Uses bypassPermissions because approval detection is deferred to the
    --permission-prompt-tool integration (future work).
    """

    def __init__(
        self,
        binary: str = "claude",
        cwd: str | None = None,
        runner: StreamRunner | None = None,
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
            "stream-json",
            "--verbose",
            "--include-partial-messages",
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


class _LazyRealProcess(ClaudeProcess):
    """Launches the real subprocess lazily on first wait() call, reading stdout line-by-line."""

    def __init__(self, command: list[str], cwd: str | None) -> None:
        self._command = command
        self._cwd = cwd
        self._proc: asyncio.subprocess.Process | None = None

    async def wait(self, on_delta: OnDelta) -> ClaudeResult:
        logger.info("Launching claude subprocess (cwd=%s): %s", self._cwd, " ".join(self._command))
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self._command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
            )
        except FileNotFoundError:
            logger.warning("Claude binary not found: %s", self._command[0])
            return ClaudeFailure(exit_code=None, stderr_tail="", message="claude binary not found")

        terminal = await _drain(self._stdout_lines(), on_delta)
        stderr_b = await self._proc.stderr.read() if self._proc.stderr is not None else b""
        returncode = await self._proc.wait()
        stderr = stderr_b.decode(errors="replace")
        result = _map_terminal(terminal, returncode, stderr)
        logger.info(
            "Claude subprocess finished (exit_code=%d, stderr_len=%d, cwd=%s)",
            returncode,
            len(stderr),
            self._cwd,
        )
        return result

    async def _stdout_lines(self) -> AsyncIterator[str]:
        assert self._proc is not None and self._proc.stdout is not None
        async for raw in self._proc.stdout:
            line = raw.decode(errors="replace").strip()
            if line:
                yield line

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
