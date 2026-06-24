"""Inbound runtime reports → in-memory read model.

The Devcontainer Runtime pushes Delegated Run snapshots up the runtime channel.
Snapshots are kept in LiveStateStore (container-scoped, never persisted; rebuilt
when the runtime reconnects — ADR-0016) and publish an SSE invalidation.
"""

from vibing_protocol import DelegatedRunItem

from vibing_api.core.broadcaster import Broadcaster, SseEvent
from vibing_api.core.live_state import LiveStateStore


def record_delegated_runs(
    live_state: LiveStateStore,
    devcontainer_id: str,
    items: list[DelegatedRunItem],
    broadcaster: Broadcaster | None = None,
) -> None:
    live_state.set_delegated_runs(devcontainer_id, items)
    if broadcaster is not None:
        broadcaster.publish(SseEvent(scope="delegated_runs", ids=[devcontainer_id]))
