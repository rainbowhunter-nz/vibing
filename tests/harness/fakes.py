"""FakeExecutor: an in-memory Executor for descriptor tests. `run` returns the scripted
result whose key is the longest prefix of the command (so `cursor-agent status` and
`cursor-agent models` can be scripted apart); read/write hit an in-memory filesystem."""

from collections.abc import AsyncIterator

from vibing_harness.executor import CommandResult


class FakeExecutor:
    def __init__(self, results: dict[str, CommandResult] | None = None) -> None:
        self._results = results or {}
        self.files: dict[str, bytes] = {}
        self.modes: dict[str, int] = {}
        self.runs: list[list[str]] = []
        self.run_envs: list[dict[str, str] | None] = []

    async def run(self, argv: list[str], env: dict[str, str] | None = None) -> CommandResult:
        self.runs.append(argv)
        self.run_envs.append(env)
        joined = " ".join(argv)
        matches = [(k, v) for k, v in self._results.items() if joined.startswith(k)]
        if not matches:
            return CommandResult(0, "", "")
        return max(matches, key=lambda kv: len(kv[0]))[1]

    async def read(self, path: str) -> bytes | None:
        return self.files.get(path)

    async def write(self, path: str, data: bytes, mode: int = 0o600) -> None:
        self.files[path] = data
        self.modes[path] = mode

    async def stream(self, argv: list[str]) -> AsyncIterator[str]:
        self.runs.append(argv)
        return
        yield  # make this an async generator
