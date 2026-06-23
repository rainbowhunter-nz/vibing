"""FakeExecutor: an in-memory Executor for descriptor tests. `run` returns scripted
results keyed by argv[0] (or a default); read/write hit an in-memory filesystem."""

from collections.abc import AsyncIterator

from vibing_harness.executor import CommandResult


class FakeExecutor:
    def __init__(self, results: dict[str, CommandResult] | None = None) -> None:
        self._results = results or {}
        self.files: dict[str, bytes] = {}
        self.modes: dict[str, int] = {}
        self.runs: list[list[str]] = []

    async def run(self, argv: list[str]) -> CommandResult:
        self.runs.append(argv)
        return self._results.get(argv[0], CommandResult(0, "", ""))

    async def read(self, path: str) -> bytes | None:
        return self.files.get(path)

    async def write(self, path: str, data: bytes, mode: int = 0o600) -> None:
        self.files[path] = data
        self.modes[path] = mode

    async def stream(self, argv: list[str]) -> AsyncIterator[str]:
        self.runs.append(argv)
        return
        yield  # make this an async generator
