"""Launches the Devcontainer Runtime Agent inside a running container.

Injects uv + vibing wheel via docker cp, then runs a single devcontainer exec
that installs the runtime with uv and detaches the agent.

Best-effort: any FileNotFoundError OR non-zero exit on ANY step logs a WARNING
and returns without raising; later steps are skipped after a failure.
"""

from pathlib import Path

from logzero import logger

from vibing_host_runtime.agent_url import resolve_agent_control_plane_url
from vibing_host_runtime.devcontainer_cli import Runner, _default_runner

_DEFAULT_UV_BINARY = "/usr/local/bin/uv"
_DEFAULT_WHEEL_DIR = "/opt/vibing/wheels"
_CONTAINER_UV_DEST = "/usr/local/bin/uv"
_CONTAINER_WHEEL_DIR = "/tmp"


class AgentLauncher:
    def __init__(
        self,
        devcontainer_cli: str = "devcontainer",
        agent_control_plane_url: str = "ws://host.docker.internal:8000/api/v1/runtime/agent/ws",
        *,
        engine: str = "docker",
        uv_binary: str = _DEFAULT_UV_BINARY,
        wheel_dir: str = _DEFAULT_WHEEL_DIR,
        runner: Runner | None = None,
    ) -> None:
        self._cli = devcontainer_cli
        self._agent_url = agent_control_plane_url
        self._engine = engine
        self._uv_binary = uv_binary
        self._wheel_dir = wheel_dir
        self._runner = runner or _default_runner

    async def launch(self, devcontainer_id: str, container_id: str, local_path: str) -> None:
        wheel = self._find_wheel()
        if wheel is None:
            logger.warning("Agent injection skipped: no .whl found in %s", self._wheel_dir)
            return

        container_wheel_path = f"{_CONTAINER_WHEEL_DIR}/{wheel.name}"

        if not await self._run(
            [self._engine, "cp", self._uv_binary, f"{container_id}:{_CONTAINER_UV_DEST}"],
            "cp uv binary",
            devcontainer_id,
        ):
            return

        if not await self._run(
            [self._engine, "cp", str(wheel), f"{container_id}:{container_wheel_path}"],
            "cp wheel",
            devcontainer_id,
        ):
            return

        agent_url = resolve_agent_control_plane_url(self._agent_url)
        bash_payload = (
            f"{_CONTAINER_UV_DEST} tool install --python 3.13 --from {container_wheel_path} vibing"
            f' && export PATH="$HOME/.local/bin:$PATH"'
            f" && nohup vibing runtime devcontainer"
            f" --control-plane-url {agent_url}"
            f" --devcontainer-id {devcontainer_id}"
            f" >/tmp/vibing-agent.log 2>&1 &"
        )
        await self._run(
            [
                self._cli,
                "exec",
                "--workspace-folder",
                local_path,
                "--",
                "bash",
                "-lc",
                bash_payload,
            ],
            "devcontainer exec",
            devcontainer_id,
        )

    def _find_wheel(self) -> Path | None:
        wheels = sorted(Path(self._wheel_dir).glob("*.whl"))
        return wheels[0] if wheels else None

    async def _run(self, command: list[str], step: str, devcontainer_id: str) -> bool:
        try:
            result = await self._runner(command)
        except FileNotFoundError:
            logger.warning(
                "Agent injection failed at '%s' for %s: binary not found: %s",
                step,
                devcontainer_id,
                command[0],
            )
            return False
        if result.returncode != 0:
            logger.warning(
                "Agent injection failed at '%s' for %s (exit %d): %s",
                step,
                devcontainer_id,
                result.returncode,
                result.stderr[-2000:],
            )
            return False
        return True
