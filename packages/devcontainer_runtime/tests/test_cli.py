"""Tests for the Devcontainer Runtime Agent CLI — no real connection is made."""

import pytest
from typer.testing import CliRunner

import vibing_devcontainer_runtime.cli as cli_module
from vibing_devcontainer_runtime.cli import DEFAULT_CONTROL_PLANE_URL, cli
from vibing_protocol import RegisterEnvelope
from vibing_runtime_client import RuntimeChannelClient


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> list[RuntimeChannelClient]:
    """Capture the RuntimeChannelClient the CLI builds without running it."""
    clients: list[RuntimeChannelClient] = []

    def fake_asyncio_run(coro: object) -> None:
        pass

    monkeypatch.setattr(cli_module.asyncio, "run", fake_asyncio_run)

    class CapturingClient(RuntimeChannelClient):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]
            clients.append(self)  # type: ignore[arg-type]

    monkeypatch.setattr(cli_module, "RuntimeChannelClient", CapturingClient)
    return clients  # type: ignore[return-value]


def test_cli_defaults(captured: list[RuntimeChannelClient]) -> None:
    result = CliRunner().invoke(cli, ["--devcontainer-id", "dc-test"])
    assert result.exit_code == 0, result.output
    [client] = captured
    assert client._url == DEFAULT_CONTROL_PLANE_URL
    assert DEFAULT_CONTROL_PLANE_URL == "ws://host.docker.internal:8000/api/v1/runtime/agent/ws"
    assert client._register.source == "devcontainer_runtime_agent"
    assert client._register.devcontainer_id == "dc-test"


def test_cli_overrides(captured: list[RuntimeChannelClient]) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "--control-plane-url",
            "ws://host:9/api/v1/runtime/agent/ws",
            "--devcontainer-id",
            "my-container",
        ],
    )
    assert result.exit_code == 0, result.output
    [client] = captured
    assert client._url == "ws://host:9/api/v1/runtime/agent/ws"
    assert client._register.devcontainer_id == "my-container"


def test_cli_missing_devcontainer_id_fails() -> None:
    """--devcontainer-id is required; CLI should error without it."""
    result = CliRunner().invoke(cli, [])
    assert result.exit_code != 0


def test_register_envelope_shape() -> None:
    """RegisterEnvelope with devcontainer_id serializes correctly."""
    env = RegisterEnvelope(source="devcontainer_runtime_agent", devcontainer_id="dc-abc")
    d = env.model_dump()
    assert d["source"] == "devcontainer_runtime_agent"
    assert d["devcontainer_id"] == "dc-abc"
    assert d["type"] == "runtime_registered"


def test_host_register_envelope_unaffected() -> None:
    """Host RegisterEnvelope still works without devcontainer_id."""
    env = RegisterEnvelope(source="host_runtime_worker")
    d = env.model_dump()
    assert d["devcontainer_id"] is None
    assert d["source"] == "host_runtime_worker"
