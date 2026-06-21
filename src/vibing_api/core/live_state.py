"""In-memory live devcontainer state (ADR-0014 live-state model).

Holds two ephemeral maps keyed by devcontainer_id, alongside RuntimeRegistry:
- lifecycle transient (starting/stopping/error) during in-flight operations
- last harness-status the runtime pushed (evicted on disconnect → unknown)

Never persisted; lost on restart by design.
"""

from vibing_protocol import HarnessStatusItem

from vibing_api.core.vocabularies import DevcontainerStatus


class LiveStateStore:
    def __init__(self) -> None:
        self._transient: dict[str, DevcontainerStatus] = {}
        self._harness: dict[str, list[HarnessStatusItem]] = {}

    def set_transient(self, devcontainer_id: str, status: DevcontainerStatus) -> None:
        self._transient[devcontainer_id] = status

    def clear_transient(self, devcontainer_id: str) -> None:
        self._transient.pop(devcontainer_id, None)

    def get_transient(self, devcontainer_id: str) -> DevcontainerStatus | None:
        return self._transient.get(devcontainer_id)

    def set_harness(self, devcontainer_id: str, items: list[HarnessStatusItem]) -> None:
        self._harness[devcontainer_id] = items

    def evict_harness(self, devcontainer_id: str) -> None:
        self._harness.pop(devcontainer_id, None)

    def get_harness(self, devcontainer_id: str) -> list[HarnessStatusItem] | None:
        return self._harness.get(devcontainer_id)
