"""Tests for agent control-plane URL resolution."""

from vibing_host_runtime.agent_url import resolve_agent_control_plane_url


def test_resolve_replaces_host_docker_internal(monkeypatch) -> None:
    monkeypatch.setattr(
        "vibing_host_runtime.agent_url._container_ip",
        lambda: "10.89.0.2",
    )
    url = "ws://host.docker.internal:8080/api/v1/runtime/agent/ws"
    assert (
        resolve_agent_control_plane_url(url)
        == "ws://10.89.0.2:8080/api/v1/runtime/agent/ws"
    )


def test_resolve_replaces_host_containers_internal(monkeypatch) -> None:
    monkeypatch.setattr(
        "vibing_host_runtime.agent_url._container_ip",
        lambda: "10.88.0.1",
    )
    url = "ws://host.containers.internal:8080/api/v1/runtime/agent/ws"
    assert (
        resolve_agent_control_plane_url(url)
        == "ws://10.88.0.1:8080/api/v1/runtime/agent/ws"
    )


def test_resolve_leaves_custom_host_unchanged(monkeypatch) -> None:
    monkeypatch.setattr(
        "vibing_host_runtime.agent_url._container_ip",
        lambda: "10.89.0.2",
    )
    url = "ws://custom-host:9999/api/v1/runtime/agent/ws"
    assert resolve_agent_control_plane_url(url) == url


def test_resolve_keeps_host_alias_when_ip_lookup_fails(monkeypatch) -> None:
    monkeypatch.setattr("vibing_host_runtime.agent_url._container_ip", lambda: None)
    url = "ws://host.docker.internal:8080/api/v1/runtime/agent/ws"
    assert resolve_agent_control_plane_url(url) == url
