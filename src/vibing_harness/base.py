"""HarnessDescriptor: per-harness knowledge as behaviour over an injected Executor.
The single home for a harness's binary, install/check/auth commands, credential path
and format, spawn argv/env, and result extraction. No execution context of its own."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from vibing_harness.executor import Executor


@dataclass(frozen=True)
class HarnessStatus:
    name: str
    installed: bool
    authenticated: bool
    default_model: str = ""


class HarnessDescriptor(ABC):
    name: str
    default_model: str = ""  # recommended model when the caller doesn't pick one

    @abstractmethod
    async def is_installed(self, ex: Executor) -> bool: ...

    @abstractmethod
    def install_argv(self) -> list[str]: ...

    @abstractmethod
    async def install(self, ex: Executor) -> None: ...

    @abstractmethod
    async def is_authenticated(self, ex: Executor) -> bool: ...

    @abstractmethod
    async def write_credentials(self, ex: Executor, blob: dict) -> None: ...

    @abstractmethod
    def build_spawn_argv(self, model: str, prompt: str) -> list[str]: ...

    @abstractmethod
    async def spawn_env(self, ex: Executor) -> dict[str, str]: ...

    @abstractmethod
    def extract_result(self, stdout: str) -> str: ...

    async def status(self, ex: Executor) -> HarnessStatus:
        installed = await self.is_installed(ex)
        authenticated = await self.is_authenticated(ex) if installed else False
        return HarnessStatus(
            name=self.name,
            installed=installed,
            authenticated=authenticated,
            default_model=self.default_model,
        )
