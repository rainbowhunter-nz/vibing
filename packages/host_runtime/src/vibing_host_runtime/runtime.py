"""Host-side runtime skeleton.

The Host Runtime Worker owns devcontainer-lifecycle operations (eventually:
Dev Container CLI, Docker/Podman). This module only defines the interface
and a skeleton implementation. No Docker, Podman, or Dev Container CLI calls.
"""

from typing import Protocol

from vibing_protocol import Command, RuntimeEvent

HOST_COMMAND_TYPES: frozenset[str] = frozenset(
    {
        "start_devcontainer",
        "stop_devcontainer",
        "restart_devcontainer",
    }
)


class HostRuntime(Protocol):
    """Receive a host-side command, emit zero or more runtime events."""

    def handle(self, command: Command) -> list[RuntimeEvent]: ...


class HostRuntimeWorker:
    """Host runtime worker. Implementation pending — no runtime infra yet."""

    def handle(self, command: Command) -> list[RuntimeEvent]:
        raise NotImplementedError
