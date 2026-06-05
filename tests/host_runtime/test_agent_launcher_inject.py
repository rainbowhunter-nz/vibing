"""Tests for AgentLauncher injection via docker cp + devcontainer exec (VIB-98)."""

import asyncio
from pathlib import Path

from vibing_host_runtime.agent_launcher import AgentLauncher
from vibing_host_runtime.devcontainer_cli import RunResult


class FakeRunner:
    def __init__(
        self,
        results: list[RunResult] | None = None,
        raises_on: int | None = None,
        raises: Exception | None = None,
    ) -> None:
        """results: per-call return values (cycled); raises_on: 0-indexed call index that raises."""
        self._results = results or [RunResult(returncode=0, stdout="", stderr="")]
        self._raises_on = raises_on
        self._raises = raises
        self.calls: list[list[str]] = []

    async def __call__(self, command: list[str]) -> RunResult:
        idx = len(self.calls)
        self.calls.append(command)
        if self._raises_on is not None and idx == self._raises_on:
            raise self._raises or FileNotFoundError("not found")
        result_idx = min(idx, len(self._results) - 1)
        return self._results[result_idx]


def _ok() -> RunResult:
    return RunResult(returncode=0, stdout="", stderr="")


def _fail() -> RunResult:
    return RunResult(returncode=1, stdout="", stderr="error")


def _launcher(
    runner: FakeRunner,
    wheel_dir: str = "/opt/vibing/wheels",
    uv_binary: str = "/usr/local/bin/uv",
    engine: str = "docker",
) -> AgentLauncher:
    return AgentLauncher(
        devcontainer_cli="devcontainer",
        agent_control_plane_url="ws://host.docker.internal:8000/api/v1/runtime/agent/ws",
        engine=engine,
        uv_binary=uv_binary,
        wheel_dir=wheel_dir,
        runner=runner,
    )


# --- AC1: docker cp uv + wheel happen before exec ---


def test_cp_uv_binary_is_first_command(tmp_path: Path) -> None:
    wheel = tmp_path / "vibing-1.0-py3-none-any.whl"
    wheel.touch()
    runner = FakeRunner([_ok(), _ok(), _ok()])
    lnch = _launcher(runner, wheel_dir=str(tmp_path))
    asyncio.run(lnch.launch("dc-1", "ctr-abc", "/workspace"))

    assert runner.calls[0][0] == "docker"
    assert runner.calls[0][1] == "cp"
    assert runner.calls[0][2] == "/usr/local/bin/uv"
    assert runner.calls[0][3] == "ctr-abc:/usr/local/bin/uv"


def test_cp_wheel_is_second_command(tmp_path: Path) -> None:
    wheel = tmp_path / "vibing-1.0-py3-none-any.whl"
    wheel.touch()
    runner = FakeRunner([_ok(), _ok(), _ok()])
    lnch = _launcher(runner, wheel_dir=str(tmp_path))
    asyncio.run(lnch.launch("dc-1", "ctr-abc", "/workspace"))

    assert runner.calls[1][0] == "docker"
    assert runner.calls[1][1] == "cp"
    assert str(wheel) == runner.calls[1][2]
    assert runner.calls[1][3].startswith("ctr-abc:/tmp/")
    assert runner.calls[1][3].endswith(".whl")


def test_exec_is_third_command(tmp_path: Path) -> None:
    wheel = tmp_path / "vibing-1.0-py3-none-any.whl"
    wheel.touch()
    runner = FakeRunner([_ok(), _ok(), _ok()])
    lnch = _launcher(runner, wheel_dir=str(tmp_path))
    asyncio.run(lnch.launch("dc-42", "ctr-abc", "/home/user/project"))

    assert len(runner.calls) == 3
    cmd = runner.calls[2]
    assert cmd[0] == "devcontainer"
    assert cmd[1] == "exec"
    assert "--workspace-folder" in cmd
    idx = cmd.index("--workspace-folder")
    assert cmd[idx + 1] == "/home/user/project"
    assert "--" in cmd
    sep = cmd.index("--")
    assert cmd[sep + 1] == "bash"
    assert cmd[sep + 2] == "-lc"
    payload = cmd[sep + 3]
    assert "uv" in payload
    assert "nohup" in payload
    assert "vibing runtime devcontainer" in payload
    assert "--devcontainer-id dc-42" in payload
    assert "ws://host.docker.internal:8000/api/v1/runtime/agent/ws" in payload
    assert "/tmp/vibing-agent.log" in payload


def test_exec_payload_installs_then_launches(tmp_path: Path) -> None:
    wheel = tmp_path / "vibing-1.0-py3-none-any.whl"
    wheel.touch()
    runner = FakeRunner([_ok(), _ok(), _ok()])
    lnch = _launcher(runner, wheel_dir=str(tmp_path))
    asyncio.run(lnch.launch("dc-42", "ctr-abc", "/workspace"))

    payload = runner.calls[2][runner.calls[2].index("--") + 3]
    # install must use uv tool install --from <wheel> vibing (not uv pip install)
    assert "uv tool install" in payload
    assert "--from /tmp/vibing-1.0-py3-none-any.whl vibing" in payload
    # install must appear before nohup launch
    assert payload.index("uv tool install") < payload.index("nohup")
    # nohup must appear before vibing runtime devcontainer
    assert payload.index("nohup") < payload.index("vibing runtime devcontainer")


# --- custom engine ---


def test_custom_engine_used_for_cp(tmp_path: Path) -> None:
    wheel = tmp_path / "vibing-1.0-py3-none-any.whl"
    wheel.touch()
    runner = FakeRunner([_ok(), _ok(), _ok()])
    lnch = _launcher(runner, engine="podman", wheel_dir=str(tmp_path))
    asyncio.run(lnch.launch("dc-1", "ctr-abc", "/workspace"))

    assert runner.calls[0][0] == "podman"
    assert runner.calls[1][0] == "podman"


# --- AC4: best-effort failures ---


def test_cp_uv_nonzero_stops_and_no_raise(tmp_path: Path) -> None:
    wheel = tmp_path / "vibing-1.0-py3-none-any.whl"
    wheel.touch()
    runner = FakeRunner([_fail()])
    lnch = _launcher(runner, wheel_dir=str(tmp_path))
    asyncio.run(lnch.launch("dc-1", "ctr-abc", "/workspace"))  # must not raise

    assert len(runner.calls) == 1  # stopped after first failure, no further steps


def test_cp_uv_file_not_found_stops_no_raise(tmp_path: Path) -> None:
    wheel = tmp_path / "vibing-1.0-py3-none-any.whl"
    wheel.touch()
    runner = FakeRunner(raises_on=0, raises=FileNotFoundError("docker"))
    lnch = _launcher(runner, wheel_dir=str(tmp_path))
    asyncio.run(lnch.launch("dc-1", "ctr-abc", "/workspace"))  # must not raise

    assert len(runner.calls) == 1  # runner was invoked, then aborted


def test_cp_wheel_nonzero_stops_no_raise(tmp_path: Path) -> None:
    wheel = tmp_path / "vibing-1.0-py3-none-any.whl"
    wheel.touch()
    runner = FakeRunner([_ok(), _fail()])
    lnch = _launcher(runner, wheel_dir=str(tmp_path))
    asyncio.run(lnch.launch("dc-1", "ctr-abc", "/workspace"))  # must not raise

    assert len(runner.calls) == 2  # stopped after wheel cp, exec never ran


def test_exec_nonzero_no_raise(tmp_path: Path) -> None:
    wheel = tmp_path / "vibing-1.0-py3-none-any.whl"
    wheel.touch()
    runner = FakeRunner([_ok(), _ok(), _fail()])
    lnch = _launcher(runner, wheel_dir=str(tmp_path))
    asyncio.run(lnch.launch("dc-1", "ctr-abc", "/workspace"))  # must not raise

    assert len(runner.calls) == 3  # all three ran


def test_no_wheel_found_no_raise_no_runner(tmp_path: Path) -> None:
    """No .whl in wheel_dir → return without running any commands."""
    runner = FakeRunner([_ok(), _ok(), _ok()])
    lnch = _launcher(runner, wheel_dir=str(tmp_path))
    asyncio.run(lnch.launch("dc-1", "ctr-abc", "/workspace"))  # must not raise

    assert len(runner.calls) == 0
