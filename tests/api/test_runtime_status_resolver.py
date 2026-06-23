from vibing_api.core.runtime_status_resolver import resolve_runtime_state
from vibing_api.core.vocabularies import RuntimeState


def test_connected_wins_over_launching() -> None:
    assert resolve_runtime_state(RuntimeState.LAUNCHING, True) == RuntimeState.CONNECTED


def test_connected_when_registry_connected() -> None:
    assert resolve_runtime_state(None, True) == RuntimeState.CONNECTED


def test_launching_when_transient_and_not_connected() -> None:
    assert resolve_runtime_state(RuntimeState.LAUNCHING, False) == RuntimeState.LAUNCHING


def test_disconnected_by_default() -> None:
    assert resolve_runtime_state(None, False) == RuntimeState.DISCONNECTED


def test_error_when_transient_error_and_not_connected() -> None:
    assert resolve_runtime_state(RuntimeState.ERROR, False) == RuntimeState.ERROR


def test_connected_wins_over_error() -> None:
    assert resolve_runtime_state(RuntimeState.ERROR, True) == RuntimeState.CONNECTED
