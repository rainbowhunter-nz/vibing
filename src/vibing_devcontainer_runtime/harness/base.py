"""HarnessAdapter: the per-harness contract. The single place that knows a harness's
install command, credential location/format, auth check, and non-interactive invocation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HarnessStatus:
    name: str
    installed: bool
    authenticated: bool


class HarnessAdapter(ABC):
    name: str

    @abstractmethod
    async def is_installed(self) -> bool: ...

    @abstractmethod
    async def install(self) -> None: ...

    @abstractmethod
    async def is_authenticated(self) -> bool: ...

    @abstractmethod
    def write_credentials(self, blob: dict[str, Any]) -> None: ...

    @abstractmethod
    def build_spawn_argv(self, model: str, prompt: str) -> list[str]: ...

    @abstractmethod
    def spawn_env(self) -> dict[str, str]: ...

    @abstractmethod
    def extract_result(self, stdout: str) -> str: ...
