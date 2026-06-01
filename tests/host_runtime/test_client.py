"""Tests for WorkerConfig — transport tests live in tests/runtime_client."""

from vibing_host_runtime.client import (
    DEFAULT_CONTROL_PLANE_URL,
    DEFAULT_DEVCONTAINER_CLI,
    WorkerConfig,
)


def test_worker_config_fields() -> None:
    config = WorkerConfig(
        control_plane_url=DEFAULT_CONTROL_PLANE_URL,
        devcontainer_cli=DEFAULT_DEVCONTAINER_CLI,
    )
    assert config.control_plane_url == "ws://127.0.0.1:8000/api/v1/runtime/ws"
    assert config.devcontainer_cli == "devcontainer"
