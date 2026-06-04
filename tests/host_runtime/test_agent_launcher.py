"""Tests for AgentLauncher exec command structure — fake runner, no real CLI/Docker."""

import asyncio
from pathlib import Path

from vibing_host_runtime.agent_launcher import AgentLauncher
from vibing_host_runtime.devcontainer_cli import RunResult


class FakeRunner:
    def __init__(self, result: RunResult | None = None, raises: Exception | None = None) -> None:
        self._result = result
        self._raises = raises
        self.calls: list[list[str]] = []

    async def __call__(self, command: list[str]) -> RunResult:
        self.calls.append(command)
        if self._raises is not None:
            raise self._raises
        assert self._result is not None
        return self._result


def _ok() -> RunResult:
    return RunResult(returncode=0, stdout="", stderr="")


def _fail() -> RunResult:
    return RunResult(returncode=1, stdout="", stderr="agent failed")


# --- exec command structure ---


def test_launch_builds_exact_exec_command(tmp_path: Path) -> None:
    """Third runner call must be the devcontainer exec with correct bash payload."""
    wheel = tmp_path / "vibing-1.0-py3-none-any.whl"
    wheel.touch()
    runner = FakeRunner(_ok())
    launcher = AgentLauncher(
        devcontainer_cli="devcontainer",
        agent_control_plane_url="ws://host.docker.internal:8000/api/v1/runtime/agent/ws",
        wheel_dir=str(tmp_path),
        runner=runner,
    )
    asyncio.run(launcher.launch("dc-42", "ctr-abc", "/home/user/myproject"))

    assert len(runner.calls) == 3
    cmd = runner.calls[2]  # exec is the third call
    assert cmd[0] == "devcontainer"
    assert cmd[1] == "exec"
    assert "--workspace-folder" in cmd
    assert "/home/user/myproject" == cmd[cmd.index("--workspace-folder") + 1]
    assert "--" in cmd
    sep = cmd.index("--")
    assert cmd[sep + 1] == "bash"
    assert cmd[sep + 2] == "-lc"
    payload = cmd[sep + 3]
    assert "nohup" in payload
    assert "vibing devcontainer-runtime" in payload
    assert "--control-plane-url" in payload
    assert "ws://host.docker.internal:8000/api/v1/runtime/agent/ws" in payload
    assert "--devcontainer-id" in payload
    assert "dc-42" in payload
    assert "/tmp/vibing-agent.log" in payload


def test_launch_uses_custom_cli_binary(tmp_path: Path) -> None:
    wheel = tmp_path / "vibing-1.0-py3-none-any.whl"
    wheel.touch()
    runner = FakeRunner(_ok())
    launcher = AgentLauncher(
        devcontainer_cli="/opt/bin/devcontainer",
        agent_control_plane_url="ws://host.docker.internal:8000/api/v1/runtime/agent/ws",
        wheel_dir=str(tmp_path),
        runner=runner,
    )
    asyncio.run(launcher.launch("dc-1", "ctr-abc", "/some/path"))
    assert runner.calls[2][0] == "/opt/bin/devcontainer"


# --- best-effort: no wheel → no runner calls ---


def test_launch_no_wheel_does_not_raise(tmp_path: Path) -> None:
    runner = FakeRunner(_ok())
    launcher = AgentLauncher(
        devcontainer_cli="devcontainer",
        agent_control_plane_url="ws://host.docker.internal:8000/api/v1/runtime/agent/ws",
        wheel_dir=str(tmp_path),
        runner=runner,
    )
    asyncio.run(launcher.launch("dc-1", "ctr-abc", "/path"))  # must not raise
    assert runner.calls == []  # no commands run when no wheel


# --- best-effort: cp uv failure → no further steps ---


def test_launch_cp_nonzero_does_not_raise(tmp_path: Path) -> None:
    wheel = tmp_path / "vibing-1.0-py3-none-any.whl"
    wheel.touch()
    runner = FakeRunner(_fail())
    launcher = AgentLauncher(
        devcontainer_cli="devcontainer",
        agent_control_plane_url="ws://host.docker.internal:8000/api/v1/runtime/agent/ws",
        wheel_dir=str(tmp_path),
        runner=runner,
    )
    asyncio.run(launcher.launch("dc-1", "ctr-abc", "/path"))  # must not raise
    assert len(runner.calls) == 1  # stopped after first cp failure


def test_launch_file_not_found_does_not_raise(tmp_path: Path) -> None:
    wheel = tmp_path / "vibing-1.0-py3-none-any.whl"
    wheel.touch()
    runner = FakeRunner(raises=FileNotFoundError("docker"))
    launcher = AgentLauncher(
        devcontainer_cli="devcontainer",
        agent_control_plane_url="ws://host.docker.internal:8000/api/v1/runtime/agent/ws",
        wheel_dir=str(tmp_path),
        runner=runner,
    )
    asyncio.run(launcher.launch("dc-1", "ctr-abc", "/path"))  # must not raise
    assert runner.calls  # runner was invoked (FileNotFoundError path was hit)
