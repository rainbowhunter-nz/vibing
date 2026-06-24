"""Reconcile the devcontainers table with the filesystem at startup.

The filesystem is the source of truth for existence: upsert every scanned folder,
then evict any row whose path is no longer a devcontainer folder (manual rows
included). New folders surface after restart or via POST.
"""

from pathlib import Path

from vibing_api.core.database import get_connection
from vibing_api.core.discovery import is_devcontainer_folder, scan
from vibing_api.core.live_state import LiveStateStore
from vibing_api.repositories.devcontainers import DevcontainerRepository


def sync_devcontainers(devcontainers_dir: str | None, live_state: LiveStateStore) -> None:
    with get_connection() as conn:
        repo = DevcontainerRepository(conn)
        for found in scan(devcontainers_dir):
            repo.upsert(found.name, found.local_path)
        for record in repo.list():
            if not is_devcontainer_folder(Path(record.local_path)):
                repo.delete(record.id)
                live_state.clear_transient(record.id)
                live_state.clear_runtime_transient(record.id)
                live_state.evict_harness(record.id)
                live_state.evict_delegated_runs(record.id)
        conn.commit()
