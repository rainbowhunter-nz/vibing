"""Unified read over manual (DB) + discovered (folder) devcontainers.

Discovered records are virtual. Dedup by local_path: a manual record hides a
discovered one at the same path. Backs get(id) for every lifecycle route so
discovered ids resolve instead of 404ing.
"""

from collections.abc import Callable
from dataclasses import dataclass

from vibing_api.api.schemas.devcontainers import DevcontainerSource
from vibing_api.core.discovery import DiscoveredDevcontainer
from vibing_api.repositories.devcontainers import DevcontainerRecord


@dataclass(frozen=True)
class ResolvedDevcontainer:
    id: str
    name: str
    local_path: str
    source: DevcontainerSource
    created_at: str | None
    updated_at: str | None


class DevcontainerCatalog:
    def __init__(
        self,
        list_records: Callable[[], list[DevcontainerRecord]],
        get_record: Callable[[str], DevcontainerRecord | None],
        scanner: Callable[[], list[DiscoveredDevcontainer]],
    ) -> None:
        self._list_records = list_records
        self._get_record = get_record
        self._scanner = scanner

    def list(self) -> list[ResolvedDevcontainer]:
        manual = [self._from_record(r) for r in self._list_records()]
        taken = {r.local_path for r in manual}
        discovered = [
            self._from_discovered(d) for d in self._scanner() if d.local_path not in taken
        ]
        return manual + discovered

    def get(self, devcontainer_id: str) -> ResolvedDevcontainer | None:
        record = self._get_record(devcontainer_id)
        if record is not None:
            return self._from_record(record)
        for d in self._scanner():
            if d.id == devcontainer_id:
                return self._from_discovered(d)
        return None

    @staticmethod
    def _from_record(r: DevcontainerRecord) -> ResolvedDevcontainer:
        return ResolvedDevcontainer(
            r.id, r.name, r.local_path, DevcontainerSource.MANUAL, r.created_at, r.updated_at
        )

    @staticmethod
    def _from_discovered(d: DiscoveredDevcontainer) -> ResolvedDevcontainer:
        return ResolvedDevcontainer(
            d.id, d.name, d.local_path, DevcontainerSource.DISCOVERED, None, None
        )
