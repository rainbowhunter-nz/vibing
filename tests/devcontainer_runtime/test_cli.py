"""Tests for the Devcontainer Runtime CLI — no real connection is made."""

import pytest
from typer.testing import CliRunner

from vibing_devcontainer_runtime import cli as cli_module
from vibing_devcontainer_runtime.cli import DEFAULT_CONTROL_PLANE_URL, cli
from vibing_protocol import RegisterEnvelope


def test_cli_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_serve(url: str, dc_id: str, mcp_host: str, mcp_port: int, workspace: str) -> None:
        calls.append((url, dc_id, mcp_host, str(mcp_port), workspace))

    monkeypatch.setattr(cli_module, "_serve_blocking", fake_serve)
    result = CliRunner().invoke(cli, ["--devcontainer-id", "dc-test"])
    assert result.exit_code == 0, result.output
    assert calls == [(DEFAULT_CONTROL_PLANE_URL, "dc-test", "127.0.0.1", "8848", ".")]
    assert DEFAULT_CONTROL_PLANE_URL == "ws://host.docker.internal:8080/api/v1/runtime/agent/ws"


def test_cli_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_serve(url: str, dc_id: str, mcp_host: str, mcp_port: int, workspace: str) -> None:
        calls.append((url, dc_id, mcp_host, str(mcp_port), workspace))

    monkeypatch.setattr(cli_module, "_serve_blocking", fake_serve)
    result = CliRunner().invoke(
        cli,
        [
            "--control-plane-url",
            "ws://host:9/api/v1/runtime/agent/ws",
            "--devcontainer-id",
            "my-container",
            "--mcp-host",
            "0.0.0.0",
            "--mcp-port",
            "9999",
            "--workspace",
            "/custom/ws",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == [
        ("ws://host:9/api/v1/runtime/agent/ws", "my-container", "0.0.0.0", "9999", "/custom/ws")
    ]


def test_cli_missing_devcontainer_id_fails() -> None:
    """--devcontainer-id is required; CLI should error without it."""
    result = CliRunner().invoke(cli, [])
    assert result.exit_code != 0


def test_register_envelope_shape() -> None:
    """RegisterEnvelope with devcontainer_id serializes correctly."""
    env = RegisterEnvelope(devcontainer_id="dc-abc")
    d = env.model_dump()
    assert d["devcontainer_id"] == "dc-abc"
    assert d["type"] == "runtime_registered"


def test_serve_builds_managers_and_runs_both(monkeypatch: pytest.MonkeyPatch) -> None:
    """_serve_blocking wires RuntimeChannelClient + MCP; reports delegated runs on connect."""
    built: dict[str, object] = {}

    class FakeClient:
        def __init__(
            self,
            url: str,
            register: object,
            on_registered: object = None,
        ) -> None:
            built["on_registered"] = on_registered

        async def run(self) -> None:
            built["client_ran"] = True
            if built.get("on_registered") is not None:
                await built["on_registered"]()  # type: ignore[operator]

        async def send_envelope(self, envelope: object) -> None:
            built["sent_envelopes"] = built.get("sent_envelopes", 0) + 1  # type: ignore[operator]

    async def fake_serve_http(self: object) -> None:
        built["mcp_ran"] = True

    monkeypatch.setattr(cli_module, "RuntimeChannelClient", FakeClient)
    monkeypatch.setattr(
        cli_module.FastMCP, "run_streamable_http_async", fake_serve_http, raising=True
    )

    cli_module._serve_blocking("ws://x", "dc-1", "127.0.0.1", 8848, ".")

    assert built["client_ran"] is True
    assert built["mcp_ran"] is True
    # on_registered hook was wired
    assert built["on_registered"] is not None
    # calling on_registered invoked send_envelope (initial delegated runs report)
    assert built.get("sent_envelopes", 0) >= 1
