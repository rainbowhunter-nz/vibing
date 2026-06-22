"""Tests for the in-container preflight reachability probe."""

import urllib.error

import pytest
from typer.testing import CliRunner

from vibing_cli import app
from vibing_devcontainer_runtime import preflight as pf


def test_health_url_swaps_scheme_and_path() -> None:
    assert (
        pf.health_url_from_ws("ws://10.0.0.5:8080/api/v1/runtime/agent/ws")
        == "http://10.0.0.5:8080/api/v1/health"
    )


def test_health_url_handles_wss_and_preserves_port() -> None:
    assert (
        pf.health_url_from_ws("wss://cp.example:9443/api/v1/runtime/agent/ws")
        == "https://cp.example:9443/api/v1/health"
    )


class _Resp:
    status = 200

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def test_check_reachable_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pf, "urlopen", lambda url, timeout: _Resp())
    ok, message = pf.check_reachable("ws://cp:8080/api/v1/runtime/agent/ws")
    assert ok is True
    assert "http://cp:8080/api/v1/health" in message


def test_check_reachable_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, timeout: float) -> object:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(pf, "urlopen", boom)
    ok, message = pf.check_reachable("ws://cp:8080/api/v1/runtime/agent/ws")
    assert ok is False
    assert message.startswith("PREFLIGHT FAILED:")
    assert "http://cp:8080/api/v1/health" in message


def test_cli_preflight_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pf, "check_reachable", lambda url: (True, "ok"))
    ok_result = CliRunner().invoke(
        app, ["runtime", "preflight", "--control-plane-url", "ws://cp:8080/api/v1/runtime/agent/ws"]
    )
    assert ok_result.exit_code == 0, ok_result.output

    monkeypatch.setattr(pf, "check_reachable", lambda url: (False, "PREFLIGHT FAILED: nope"))
    bad_result = CliRunner().invoke(
        app, ["runtime", "preflight", "--control-plane-url", "ws://cp:8080/api/v1/runtime/agent/ws"]
    )
    assert bad_result.exit_code == 1
