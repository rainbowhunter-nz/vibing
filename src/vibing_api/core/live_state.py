"""In-memory live devcontainer state (ADR-0014 live-state model).

Holds four ephemeral maps keyed by devcontainer_id, alongside RuntimeRegistry:
- lifecycle transient (starting/stopping/error) during in-flight operations
- CP-computed harness-status cache (container-scoped; cleared on container stop)
- delegated-runs snapshot cache (container-scoped; rebuilt on runtime reconnect)
- runtime-state transient (launching/error/disconnected)

Never persisted; lost on restart by design.

All maps are intentionally unbounded; entries are cleared on operation
completion, container stop, or next start. An id that errors and is never
retried keeps a small entry until process restart — acceptable because the set
of devcontainer ids is bounded.
"""

from vibing_harness import HarnessStatus
from vibing_protocol import DelegatedRunItem

from vibing_api.core.vocabularies import DevcontainerStatus, RuntimeState


class LiveStateStore:
    def __init__(self) -> None:
        self._transient: dict[str, DevcontainerStatus] = {}
        self._harness: dict[str, list[HarnessStatus]] = {}
        self._runtime_transient: dict[str, RuntimeState] = {}
        self._delegated_runs: dict[str, list[DelegatedRunItem]] = {}

    def set_transient(self, devcontainer_id: str, status: DevcontainerStatus) -> None:
        self._transient[devcontainer_id] = status

    def clear_transient(self, devcontainer_id: str) -> None:
        self._transient.pop(devcontainer_id, None)

    def get_transient(self, devcontainer_id: str) -> DevcontainerStatus | None:
        return self._transient.get(devcontainer_id)

    def set_runtime_transient(self, devcontainer_id: str, state: RuntimeState) -> None:
        self._runtime_transient[devcontainer_id] = state

    def clear_runtime_transient(self, devcontainer_id: str) -> None:
        self._runtime_transient.pop(devcontainer_id, None)

    def get_runtime_transient(self, devcontainer_id: str) -> RuntimeState | None:
        return self._runtime_transient.get(devcontainer_id)

    def set_harness(self, devcontainer_id: str, items: list[HarnessStatus]) -> None:
        self._harness[devcontainer_id] = items

    def evict_harness(self, devcontainer_id: str) -> None:
        self._harness.pop(devcontainer_id, None)

    def get_harness(self, devcontainer_id: str) -> list[HarnessStatus] | None:
        return self._harness.get(devcontainer_id)

    def set_delegated_runs(self, devcontainer_id: str, items: list[DelegatedRunItem]) -> None:
        self._delegated_runs[devcontainer_id] = items

    def evict_delegated_runs(self, devcontainer_id: str) -> None:
        self._delegated_runs.pop(devcontainer_id, None)

    def get_delegated_runs(self, devcontainer_id: str) -> list[DelegatedRunItem] | None:
        return self._delegated_runs.get(devcontainer_id)
