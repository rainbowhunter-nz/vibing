"""Tests for AgentLauncher — fake runner, no real CLI/Docker."""

import asyncio

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


# --- AC2: exact command built and awaited ---


def test_launch_builds_exact_command() -> None:
    runner = FakeRunner(_ok())
    launcher = AgentLauncher(
        devcontainer_cli="devcontainer",
        agent_control_plane_url="ws://host.docker.internal:8000/api/v1/runtime/agent/ws",
        runner=runner,
    )
    asyncio.run(launcher.launch("dc-42", "/home/user/myproject"))

    assert len(runner.calls) == 1
    cmd = runner.calls[0]
    assert cmd[0] == "devcontainer"
    assert cmd[1] == "exec"
    assert "--workspace-folder" in cmd
    assert "/home/user/myproject" == cmd[cmd.index("--workspace-folder") + 1]
    assert "--" in cmd
    # bash -lc payload must be a single argument containing the nohup invocation
    bash_payload_idx = cmd.index("--") + 2  # after ['--', 'bash', '-lc']
    assert cmd[cmd.index("--") + 1] == "bash"
    assert cmd[cmd.index("--") + 2] == "-lc"
    payload = cmd[bash_payload_idx + 1]  # single string after bash -lc
    assert "nohup" in payload
    assert "vibing-devcontainer-runtime" in payload
    assert "serve" in payload
    assert "--control-plane-url" in payload
    assert "ws://host.docker.internal:8000/api/v1/runtime/agent/ws" in payload
    assert "--devcontainer-id" in payload
    assert "dc-42" in payload
    assert "/tmp/vibing-agent.log" in payload


def test_launch_uses_custom_cli_binary() -> None:
    runner = FakeRunner(_ok())
    launcher = AgentLauncher(
        devcontainer_cli="/opt/bin/devcontainer",
        agent_control_plane_url="ws://host.docker.internal:8000/api/v1/runtime/agent/ws",
        runner=runner,
    )
    asyncio.run(launcher.launch("dc-1", "/some/path"))
    assert runner.calls[0][0] == "/opt/bin/devcontainer"


# --- AC3: failure → does not raise ---


def test_launch_nonzero_does_not_raise() -> None:
    runner = FakeRunner(_fail())
    launcher = AgentLauncher(
        devcontainer_cli="devcontainer",
        agent_control_plane_url="ws://host.docker.internal:8000/api/v1/runtime/agent/ws",
        runner=runner,
    )
    asyncio.run(launcher.launch("dc-1", "/path"))  # must not raise
    assert runner.calls  # runner was invoked (failure path was reached)


def test_launch_file_not_found_does_not_raise() -> None:
    runner = FakeRunner(raises=FileNotFoundError("devcontainer"))
    launcher = AgentLauncher(
        devcontainer_cli="devcontainer",
        agent_control_plane_url="ws://host.docker.internal:8000/api/v1/runtime/agent/ws",
        runner=runner,
    )
    asyncio.run(launcher.launch("dc-1", "/path"))  # must not raise
    assert runner.calls  # runner was invoked (FileNotFoundError path was hit)
