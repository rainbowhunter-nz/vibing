"""Live runtime state: WS-connected is the durable truth, launching is transient."""

from vibing_api.core.vocabularies import RuntimeState


def resolve_runtime_state(transient: RuntimeState | None, connected: bool) -> RuntimeState:
    if connected:
        return RuntimeState.CONNECTED
    if transient == RuntimeState.LAUNCHING:
        return RuntimeState.LAUNCHING
    if transient == RuntimeState.ERROR:
        return RuntimeState.ERROR
    return RuntimeState.DISCONNECTED
