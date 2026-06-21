"""Inbound runtime reports → live state / read model.

The Devcontainer Runtime pushes Harness Status and Delegated Run snapshots up
the runtime channel. Harness status is cached in-memory in LiveStateStore (no
DB write); delegated-run snapshots are written to the read model (ADR-0014,
ADR-0016). Both paths publish an SSE invalidation.
"""

from vibing_protocol import DelegatedRunItem, HarnessStatusItem

from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.database import get_connection
from vibing_api.core.live_state import LiveStateStore
from vibing_api.repositories.delegated_runs import DelegatedRunRepository


def record_harness_status(
    live: LiveStateStore,
    devcontainer_id: str,
    items: list[HarnessStatusItem],
    broadcaster: Broadcaster | None = None,
) -> None:
    live.set_harness(devcontainer_id, items)
    if broadcaster is not None:
        broadcaster.publish(SseEvent(scope="harnesses", ids=[devcontainer_id]))


def persist_delegated_runs(
    devcontainer_id: str,
    items: list[DelegatedRunItem],
    broadcaster: Broadcaster | None = None,
) -> None:
    with get_connection() as conn:
        DelegatedRunRepository(conn).replace(devcontainer_id, items)
        conn.commit()
    if broadcaster is not None:
        broadcaster.publish(SseEvent(scope="delegated_runs", ids=[devcontainer_id]))
