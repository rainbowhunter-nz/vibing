"""Tests for the Dev Container CLI adapter — fake runner, no real CLI/Docker/Podman."""

import asyncio
import json
from pathlib import Path

from vibing_host_runtime.devcontainer_cli import (
    DevcontainerCliAdapter,
    DevcontainerFailure,
    DevcontainerSuccess,
    RunResult,
)


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


def _ok(stdout: str = "") -> RunResult:
    return RunResult(returncode=0, stdout=stdout, stderr="")


def test_start_maps_to_devcontainer_up(tmp_path: Path) -> None:
    runner = FakeRunner(_ok())
    adapter = DevcontainerCliAdapter(cli="devcontainer", runner=runner)
    asyncio.run(adapter.start(str(tmp_path)))
    assert runner.calls == [["devcontainer", "up", "--workspace-folder", str(tmp_path)]]


def test_stop_resolves_container_by_label_and_stops_via_engine(tmp_path: Path) -> None:
    runner = FakeRunner(_ok("c1\n"))
    adapter = DevcontainerCliAdapter(engine="docker", runner=runner)
    asyncio.run(adapter.stop(str(tmp_path)))
    assert runner.calls == [
        ["docker", "ps", "-q", "--filter", f"label=devcontainer.local_folder={tmp_path}"],
        ["docker", "stop", "c1"],
    ]


def test_stop_no_running_container_succeeds_without_stopping(tmp_path: Path) -> None:
    runner = FakeRunner(_ok(""))
    adapter = DevcontainerCliAdapter(engine="docker", runner=runner)
    result = asyncio.run(adapter.stop(str(tmp_path)))
    assert isinstance(result, DevcontainerSuccess)
    assert len(runner.calls) == 1  # only the ps lookup, no stop


def test_custom_cli_binary_is_used(tmp_path: Path) -> None:
    runner = FakeRunner(_ok())
    adapter = DevcontainerCliAdapter(cli="/opt/devcontainer", runner=runner)
    asyncio.run(adapter.start(str(tmp_path)))
    assert runner.calls[0][0] == "/opt/devcontainer"


def test_start_success_parses_payload(tmp_path: Path) -> None:
    stdout = json.dumps(
        {
            "outcome": "success",
            "containerId": "abc123",
            "remoteUser": "vscode",
            "remoteWorkspaceFolder": "/workspaces/repo",
        }
    )
    adapter = DevcontainerCliAdapter(runner=FakeRunner(_ok(stdout)))
    result = asyncio.run(adapter.start(str(tmp_path)))
    assert isinstance(result, DevcontainerSuccess)
    assert result.operation == "start"
    assert result.payload == {
        "container_id": "abc123",
        "remote_user": "vscode",
        "remote_workspace_folder": "/workspaces/repo",
    }


def test_start_success_with_logs_before_json(tmp_path: Path) -> None:
    stdout = 'log: building\nlog: starting\n{"outcome":"success","containerId":"c1"}\n'
    adapter = DevcontainerCliAdapter(runner=FakeRunner(_ok(stdout)))
    result = asyncio.run(adapter.start(str(tmp_path)))
    assert isinstance(result, DevcontainerSuccess)
    assert result.payload == {"container_id": "c1"}


def test_start_success_unparseable_output_yields_empty_payload(tmp_path: Path) -> None:
    adapter = DevcontainerCliAdapter(runner=FakeRunner(_ok("not json")))
    result = asyncio.run(adapter.start(str(tmp_path)))
    assert isinstance(result, DevcontainerSuccess)
    assert result.payload == {}


def test_stop_success_has_no_payload(tmp_path: Path) -> None:
    adapter = DevcontainerCliAdapter(runner=FakeRunner(_ok("ignored")))
    result = asyncio.run(adapter.stop(str(tmp_path)))
    assert isinstance(result, DevcontainerSuccess)
    assert result.operation == "stop"
    assert result.payload == {}


def test_failed_cli_returns_bounded_failure_details(tmp_path: Path) -> None:
    stderr = "\n".join(f"error line {i}" for i in range(500))
    runner = FakeRunner(RunResult(returncode=2, stdout="", stderr=stderr))
    adapter = DevcontainerCliAdapter(runner=runner)
    result = asyncio.run(adapter.start(str(tmp_path)))
    assert isinstance(result, DevcontainerFailure)
    assert result.operation == "start"
    assert result.command == ["devcontainer", "up", "--workspace-folder", str(tmp_path)]
    assert result.exit_code == 2
    assert result.stderr_tail
    assert len(result.stderr_tail) <= 4000
    assert "error line 499" in result.stderr_tail  # keeps the tail, not the head


def test_missing_cli_returns_failure_without_crashing(tmp_path: Path) -> None:
    runner = FakeRunner(raises=FileNotFoundError("devcontainer"))
    adapter = DevcontainerCliAdapter(cli="devcontainer", runner=runner)
    result = asyncio.run(adapter.start(str(tmp_path)))
    assert isinstance(result, DevcontainerFailure)
    assert result.exit_code is None
    assert "not found" in result.message.lower()


def test_missing_local_path_fails_without_invoking_cli(tmp_path: Path) -> None:
    runner = FakeRunner(_ok())
    adapter = DevcontainerCliAdapter(runner=runner)
    result = asyncio.run(adapter.start(str(tmp_path / "does-not-exist")))
    assert isinstance(result, DevcontainerFailure)
    assert result.exit_code is None
    assert runner.calls == []


def test_local_path_that_is_a_file_fails_without_invoking_cli(tmp_path: Path) -> None:
    file_path = tmp_path / "afile"
    file_path.write_text("x")
    runner = FakeRunner(_ok())
    adapter = DevcontainerCliAdapter(runner=runner)
    result = asyncio.run(adapter.start(str(file_path)))
    assert isinstance(result, DevcontainerFailure)
    assert runner.calls == []
