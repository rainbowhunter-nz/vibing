"""Tests for the --agent-control-plane-url CLI flag (VIB-34)."""

import pytest
from typer.testing import CliRunner

import vibing_host_runtime.cli as cli_module
from vibing_host_runtime.cli import cli
from vibing_host_runtime.client import DEFAULT_AGENT_CONTROL_PLANE_URL, WorkerConfig


@pytest.fixture
def captured_config(monkeypatch: pytest.MonkeyPatch) -> list[WorkerConfig]:
    configs: list[WorkerConfig] = []
    monkeypatch.setattr(cli_module, "run_worker", configs.append)
    return configs


def test_cli_agent_control_plane_url_default(captured_config: list[WorkerConfig]) -> None:
    result = CliRunner().invoke(cli, [])
    assert result.exit_code == 0
    [config] = captured_config
    assert (
        config.agent_control_plane_url
        == DEFAULT_AGENT_CONTROL_PLANE_URL
        == "ws://host.docker.internal:8000/api/v1/runtime/agent/ws"
    )


def test_cli_agent_control_plane_url_override(captured_config: list[WorkerConfig]) -> None:
    result = CliRunner().invoke(
        cli,
        ["--agent-control-plane-url", "ws://custom-host:9999/api/v1/runtime/agent/ws"],
    )
    assert result.exit_code == 0
    [config] = captured_config
    assert config.agent_control_plane_url == "ws://custom-host:9999/api/v1/runtime/agent/ws"
