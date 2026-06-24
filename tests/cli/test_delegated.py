from typer.testing import CliRunner

from vibing_cli import app
from vibing_cli import delegated

runner = CliRunner()


def test_wait_loops_past_timeout_then_prints_terminal(monkeypatch):
    calls = {"n": 0}

    async def fake_await_once(mcp_url, run_id, timeout_seconds):
        calls["n"] += 1
        if calls["n"] < 3:
            return {"run_id": run_id, "status": "running", "timed_out": True}
        return {"run_id": run_id, "status": "completed", "result": "the answer", "error": {}}

    monkeypatch.setattr(delegated, "_await_once", fake_await_once)
    result = runner.invoke(app, ["delegated", "wait", "run-1"])
    assert result.exit_code == 0
    assert calls["n"] == 3
    assert "completed" in result.stdout
    assert "the answer" in result.stdout


def test_wait_exits_nonzero_when_wait_errors(monkeypatch):
    async def boom(mcp_url, run_id, timeout_seconds):
        raise RuntimeError("server unreachable")

    monkeypatch.setattr(delegated, "_await_once", boom)
    result = runner.invoke(app, ["delegated", "wait", "run-1"])
    assert result.exit_code == 1
    assert "server unreachable" in result.stdout


def test_wait_unwraps_exception_group_to_leaf_message(monkeypatch):
    async def boom(mcp_url, run_id, timeout_seconds):
        raise ExceptionGroup("boom", [RuntimeError("connection refused")])

    monkeypatch.setattr(delegated, "_await_once", boom)
    result = runner.invoke(app, ["delegated", "wait", "run-1"])
    assert result.exit_code == 1
    assert "connection refused" in result.stdout
    assert "sub-exception" not in result.stdout
