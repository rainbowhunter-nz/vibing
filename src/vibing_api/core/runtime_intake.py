"""Inbound runtime reports → read model.

The Devcontainer Runtime pushes Delegated Run snapshots up the runtime channel.
Snapshots are written to the read model (ADR-0014, ADR-0016) and publish an SSE invalidation.
"""

from vibing_protocol import DelegatedRunItem

from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.database import get_connection
from vibing_api.repositories.delegated_runs import DelegatedRunRepository


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
