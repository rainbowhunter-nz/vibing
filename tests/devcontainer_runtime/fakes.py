"""Test adapters at the one ClaudeProcess seam — no real subprocess.

`ScriptedProcess` drains a scripted sequence of stream-json lines through the real
normalizer; `scripted_runner` wires it behind a ClaudeCodeRunner factory. Timing fakes
(controlled wait/terminate) are plain ClaudeProcess subclasses injected the same way.
"""

from collections.abc import AsyncIterator, Callable

from vibing_devcontainer_runtime.claude_runner import (
    ClaudeCodeRunner,
    ClaudeFailure,
    ClaudeProcess,
    ClaudeResult,
    OnDelta,
    _drain,
    _map_terminal,
)

# Given the command, yield Claude's stdout stream-json lines in order (may raise).
LineProducer = Callable[[list[str]], AsyncIterator[str]]


class ScriptedProcess(ClaudeProcess):
    def __init__(self, command: list[str], produce: LineProducer) -> None:
        self._command = command
        self._produce = produce

    async def wait(self, on_delta: OnDelta) -> ClaudeResult:
        try:
            terminal = await _drain(self._produce(self._command), on_delta)
        except FileNotFoundError:
            return ClaudeFailure(exit_code=None, stderr_tail="", message="claude binary not found")
        return _map_terminal(terminal, returncode=0, stderr="")

    async def terminate(self) -> None:
        pass


def scripted_runner(produce: LineProducer) -> ClaudeCodeRunner:
    return ClaudeCodeRunner(process_factory=lambda command: ScriptedProcess(command, produce))
