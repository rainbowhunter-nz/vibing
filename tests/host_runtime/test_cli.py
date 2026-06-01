"""Tests for the Host Runtime Worker CLI — no worker loop is actually run."""

import pytest
from typer.testing import CliRunner

import vibing_host_runtime.cli as cli_module
from vibing_host_runtime.cli import cli
from vibing_host_runtime.client import (
    DEFAULT_CONTROL_PLANE_URL,
    DEFAULT_DEVCONTAINER_CLI,
    WorkerConfig,
)


@pytest.fixture
def captured_config(monkeypatch: pytest.MonkeyPatch) -> list[WorkerConfig]:
    """Capture the WorkerConfig the CLI builds without running the worker."""
    configs: list[WorkerConfig] = []
    monkeypatch.setattr(cli_module, "run_worker", configs.append)
    return configs


def test_cli_defaults(captured_config: list[WorkerConfig]) -> None:
    result = CliRunner().invoke(cli, [])
    assert result.exit_code == 0
    [config] = captured_config
    assert (
        config.control_plane_url
        == DEFAULT_CONTROL_PLANE_URL
        == "ws://127.0.0.1:8000/api/v1/runtime/ws"
    )
    assert config.devcontainer_cli == DEFAULT_DEVCONTAINER_CLI == "devcontainer"


def test_cli_overrides(captured_config: list[WorkerConfig]) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "--control-plane-url",
            "ws://host:9/api/v1/runtime/ws",
            "--devcontainer-cli",
            "/opt/devcontainer",
        ],
    )
    assert result.exit_code == 0
    [config] = captured_config
    assert config.control_plane_url == "ws://host:9/api/v1/runtime/ws"
    assert config.devcontainer_cli == "/opt/devcontainer"
