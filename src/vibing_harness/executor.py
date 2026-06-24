"""Executor: the seam each consumer implements to run commands and read/write files
in a harness's environment. The Control Plane runs them via `devcontainer exec`; the
Runtime runs them as local subprocess + direct file IO. Descriptors are written against
this protocol and never execute anything themselves."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class Executor(Protocol):
    async def run(self, argv: list[str], env: dict[str, str] | None = None) -> CommandResult: ...
    async def read(self, path: str) -> bytes | None: ...
    async def write(self, path: str, data: bytes, mode: int = 0o600) -> None: ...
