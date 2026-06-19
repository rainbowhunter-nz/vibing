"""RunningSessions: tracks in-flight Claude runs by agent-session id.

Owns the (process, task) pair per session and the stop ordering — cancel the task,
then terminate the process — with auto-removal when a run finishes. Concentrates the
stop-vs-natural-completion race in one place: stop only terminates a run still in flight.
"""

import asyncio

from vibing_devcontainer_runtime.claude_runner import ClaudeProcess


class RunningSessions:
    def __init__(self) -> None:
        self._processes: dict[str, ClaudeProcess] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def track(self, session_id: str, process: ClaudeProcess, task: asyncio.Task) -> None:
        self._processes[session_id] = process
        self._tasks[session_id] = task
        task.add_done_callback(lambda _: self._forget(session_id))

    def _forget(self, session_id: str) -> None:
        self._processes.pop(session_id, None)
        self._tasks.pop(session_id, None)

    async def stop(self, session_id: str) -> None:
        """Cancel and terminate the run if still in flight; a finished run is a no-op."""
        process = self._processes.pop(session_id, None)
        task = self._tasks.pop(session_id, None)
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        if process is not None:
            await process.terminate()

    async def drain(self) -> None:
        """Await every in-flight run to settle (shutdown / tests)."""
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
