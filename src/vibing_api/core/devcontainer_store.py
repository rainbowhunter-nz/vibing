"""DB-only devcontainer resolver (replaces the manual+discovered catalog).

After startup sync, every devcontainer is a real row; resolution is a plain DB read.
"""

from collections.abc import Callable

from vibing_api.repositories.devcontainers import DevcontainerRecord


class DevcontainerStore:
    def __init__(
        self,
        list_records: Callable[[], list[DevcontainerRecord]],
        get_record: Callable[[str], DevcontainerRecord | None],
    ) -> None:
        self._list_records = list_records
        self._get_record = get_record

    def list(self) -> list[DevcontainerRecord]:
        return self._list_records()

    def get(self, devcontainer_id: str) -> DevcontainerRecord | None:
        return self._get_record(devcontainer_id)
