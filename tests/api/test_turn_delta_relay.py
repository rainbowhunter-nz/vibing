"""The agent WS routes turn_delta envelopes to the per-session SSE registry (ADR-0010).

The agent registers on /runtime/agent/ws, then sends a turn_delta; a subscriber on the
matching session sees the serialized delta. The global broadcaster is untouched
(invalidation-only invariant, ADR-0005/0006).
"""

from fastapi.testclient import TestClient

AGENT_WS_URL = "/api/v1/runtime/agent/ws"


def _agent_register(dc_id: str) -> dict:
    return {
        "type": "runtime_registered",
        "source": "devcontainer_runtime_agent",
        "devcontainer_id": dc_id,
    }


def test_turn_delta_is_relayed_to_session_subscribers(client: TestClient) -> None:
    registry = client.app.state.session_streams
    q = registry.subscribe("sess-1")

    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_agent_register("dc-1"))
        assert ws.receive_json() == {"type": "registered"}
        ws.send_json(
            {
                "type": "turn_delta",
                "devcontainer_id": "dc-1",
                "agent_session_id": "sess-1",
                "delta": {"kind": "text", "turn_id": "u-1", "role": "assistant", "text": "Hi"},
            }
        )
        # Drain the queue (publish is synchronous on the WS intake thread).
        import json
        import time

        deadline = time.monotonic() + 2.0
        data = None
        while time.monotonic() < deadline:
            try:
                data = q.get_nowait()
                break
            except Exception:
                time.sleep(0.01)
        assert data is not None
        assert json.loads(data) == {
            "kind": "text",
            "turn_id": "u-1",
            "role": "assistant",
            "text": "Hi",
        }


def test_malformed_turn_delta_is_ignored(client: TestClient) -> None:
    registry = client.app.state.session_streams
    q = registry.subscribe("sess-1")

    with client.websocket_connect(AGENT_WS_URL) as ws:
        ws.send_json(_agent_register("dc-1"))
        assert ws.receive_json() == {"type": "registered"}
        # Missing required fields -> validation fails -> ignored (no publish).
        ws.send_json({"type": "turn_delta", "delta": {"kind": "text"}})
        # A well-formed one afterwards still works, proving the connection survived.
        ws.send_json(
            {
                "type": "turn_delta",
                "devcontainer_id": "dc-1",
                "agent_session_id": "sess-1",
                "delta": {"kind": "run_started"},
            }
        )
        import json
        import time

        deadline = time.monotonic() + 2.0
        data = None
        while time.monotonic() < deadline:
            try:
                data = q.get_nowait()
                break
            except Exception:
                time.sleep(0.01)
        assert data is not None
        assert json.loads(data) == {"kind": "run_started"}
