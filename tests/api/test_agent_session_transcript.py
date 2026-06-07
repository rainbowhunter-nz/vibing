"""Route tests for GET .../agent-sessions/{id}/transcript (VIB-104, ADR-0009).

A full TestClient round-trip is impractical (the GET blocks the test thread while the
same thread would need to pump the ws reply), so we stub app.state.agent_manager with a
fake whose request_transcript / is_connected drive each failure-contract branch.
"""

import asyncio
from typing import Any

from fastapi.testclient import TestClient

TRANSCRIPT_URL = "/api/v1/devcontainers/{dc}/agent-sessions/{sess}/transcript"


def _create_dc(client: TestClient, status: str = "running") -> str:
    resp = client.post("/api/v1/devcontainers", json={"name": "dc", "local_path": "/work"})
    assert resp.status_code == 201
    dc_id: str = resp.json()["id"]
    if status != "created":
        patched = client.patch(f"/api/v1/devcontainers/{dc_id}", json={"status": status})
        assert patched.status_code == 200
    return dc_id


def _create_session(client: TestClient, dc_id: str) -> str:
    from vibing_api.core.database import get_connection
    from vibing_api.repositories.agent_sessions import AgentSessionRepository

    with get_connection() as conn:
        session = AgentSessionRepository(conn).create(dc_id, prompt="hi")
        conn.commit()
    return session.id


class _FakeAgentManager:
    def __init__(
        self,
        *,
        connected: bool = True,
        turns: list[Any] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._connected = connected
        self._turns = turns or []
        self._raises = raises
        self.requested: list[tuple[str, str]] = []

    def is_connected(self, key: str) -> bool:
        return self._connected

    async def request_transcript(
        self, devcontainer_id: str, agent_session_id: str, timeout: float
    ) -> list[Any]:
        self.requested.append((devcontainer_id, agent_session_id))
        if self._raises is not None:
            raise self._raises
        return self._turns


def _url(dc: str, sess: str) -> str:
    return TRANSCRIPT_URL.format(dc=dc, sess=sess)


# --- existence guards ---


def test_devcontainer_not_found(client: TestClient) -> None:
    resp = client.get(_url("ghost", "sess"))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DEVCONTAINER_NOT_FOUND"


def test_session_not_found(client: TestClient) -> None:
    dc_id = _create_dc(client)
    resp = client.get(_url(dc_id, "ghost"))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "AGENT_SESSION_NOT_FOUND"


# --- happy path: turns ---


def test_happy_path_returns_turns(client: TestClient) -> None:
    dc_id = _create_dc(client)
    sess_id = _create_session(client, dc_id)
    # ADR-0010: turns carry a stable id (Claude uuid) the reducer keys on.
    turns = [{"id": "u-1", "role": "user", "blocks": [{"kind": "text", "text": "hi"}], "at": "t"}]
    client.app.state.agent_manager = _FakeAgentManager(connected=True, turns=turns)

    resp = client.get(_url(dc_id, sess_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "has_turns"
    assert body["turns"] == turns
    assert body["turns"][0]["id"] == "u-1"
    assert body["summary_text"] is None


# --- empty: no conversation yet (NOT an error) ---


def test_empty_turns_is_not_an_error(client: TestClient) -> None:
    dc_id = _create_dc(client)
    sess_id = _create_session(client, dc_id)
    client.app.state.agent_manager = _FakeAgentManager(connected=True, turns=[])

    resp = client.get(_url(dc_id, sess_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "empty"
    assert body["turns"] == []


# --- fallback: stopped / no agent connected ---


def test_stopped_devcontainer_falls_back_to_summary(client: TestClient) -> None:
    dc_id = _create_dc(client, status="stopped")
    sess_id = _create_session(client, dc_id)
    fake = _FakeAgentManager(connected=True, turns=[{"role": "user", "blocks": [], "at": "t"}])
    client.app.state.agent_manager = fake

    resp = client.get(_url(dc_id, sess_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "summary_fallback"
    assert body["turns"] == []
    assert fake.requested == []  # never sent a request


def test_no_agent_connected_falls_back_to_summary(client: TestClient) -> None:
    dc_id = _create_dc(client, status="running")
    sess_id = _create_session(client, dc_id)
    fake = _FakeAgentManager(connected=False)
    client.app.state.agent_manager = fake

    resp = client.get(_url(dc_id, sess_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "summary_fallback"
    assert fake.requested == []


# --- error: timeout ---


def test_timeout_returns_error_state(client: TestClient) -> None:
    dc_id = _create_dc(client, status="running")
    sess_id = _create_session(client, dc_id)
    client.app.state.agent_manager = _FakeAgentManager(
        connected=True, raises=asyncio.TimeoutError()
    )

    resp = client.get(_url(dc_id, sess_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "error"
    assert body["turns"] == []


# --- ADR-0002 invariant: transcript fetch never touches runtime_events ---


def test_transcript_fetch_does_not_persist_runtime_events(client: TestClient) -> None:
    from vibing_api.core.database import get_connection
    from vibing_api.repositories.runtime_events import RuntimeEventRepository

    dc_id = _create_dc(client, status="running")
    sess_id = _create_session(client, dc_id)
    turns = [{"role": "user", "blocks": [{"kind": "text", "text": "hi"}], "at": "t"}]
    client.app.state.agent_manager = _FakeAgentManager(connected=True, turns=turns)

    with get_connection() as conn:
        before = len(RuntimeEventRepository(conn).list_by_devcontainer(dc_id))

    resp = client.get(_url(dc_id, sess_id))
    assert resp.status_code == 200
    assert resp.json()["state"] == "has_turns"

    with get_connection() as conn:
        after = len(RuntimeEventRepository(conn).list_by_devcontainer(dc_id))
    assert after == before  # no runtime_events written by the transcript path
