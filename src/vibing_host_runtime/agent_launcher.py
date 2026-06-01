"""Launches the Devcontainer Runtime Agent inside a running container via `devcontainer exec`.

Best-effort: non-zero exit or missing binary logs a WARNING and returns without raising.
"""

from logzero import logger

from vibing_host_runtime.devcontainer_cli import Runner, _default_runner


class AgentLauncher:
    def __init__(
        self,
        devcontainer_cli: str = "devcontainer",
        agent_control_plane_url: str = "ws://host.docker.internal:8000/api/v1/runtime/agent/ws",
        *,
        runner: Runner | None = None,
    ) -> None:
        self._cli = devcontainer_cli
        self._agent_url = agent_control_plane_url
        self._runner = runner or _default_runner

    async def launch(self, devcontainer_id: str, local_path: str) -> None:
        bash_payload = (
            f"nohup vibing devcontainer-runtime"
            f" --control-plane-url {self._agent_url}"
            f" --devcontainer-id {devcontainer_id}"
            f" >/tmp/vibing-agent.log 2>&1 &"
        )
        command = [
            self._cli,
            "exec",
            "--workspace-folder",
            local_path,
            "--",
            "bash",
            "-lc",
            bash_payload,
        ]
        try:
            result = await self._runner(command)
        except FileNotFoundError:
            logger.warning("Agent launch failed: devcontainer CLI not found: %s", self._cli)
            return
        if result.returncode != 0:
            logger.warning(
                "Agent launch failed (exit %d) for devcontainer %s: %s",
                result.returncode,
                devcontainer_id,
                result.stderr[-2000:],
            )
