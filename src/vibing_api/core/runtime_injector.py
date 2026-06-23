"""Injects the Devcontainer Runtime into a running container, and controls it.

Two-phase inject: `_bootstrap` (docker cp uv + wheel, synchronous `uv tool install`
teed to the unified log, then `vibing runtime preflight` HTTP probe) gates `_spawn`
(detached `nohup` launch recording the PID). Each phase is a separate `devcontainer
exec`; the same resolved control-plane URL is passed to both preflight and launch.
Bootstrap failures (install OR preflight) surface via the exec exit code at inject
time and live in `/tmp/vibing-runtime.log`. `stop_runtime` kills via the PID file;
`stream_log` tail-follows the unified log — both via `<engine> exec`.

inject()/inject_by_path() return True when both phases succeed, False otherwise.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from logzero import logger

from vibing_api.core.runtime_injector_url import resolve_runtime_control_plane_url
from vibing_api.core.devcontainer_cli import Runner, _default_runner

_DEFAULT_UV_BINARY = "/usr/local/bin/uv"
_DEFAULT_WHEEL_DIR = "/opt/vibing/wheels"
_CONTAINER_UV_DEST = "/usr/local/bin/uv"
_CONTAINER_WHEEL_DIR = "/tmp"

CONTAINER_LOG_PATH = "/tmp/vibing-runtime.log"
CONTAINER_PID_PATH = "/tmp/vibing-runtime.pid"


async def _default_log_streamer(engine: str, container_id: str) -> AsyncIterator[bytes]:
    command = [engine, "exec", container_id, "tail", "-n", "+1", "-f", CONTAINER_LOG_PATH]
    logger.info("exec (stream): %s", " ".join(command))
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert proc.stdout is not None
    try:
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                break
            yield chunk
    finally:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()


class RuntimeInjector:
    def __init__(
        self,
        devcontainer_cli: str = "devcontainer",
        runtime_control_plane_url: str = "ws://host.docker.internal:8080/api/v1/runtime/agent/ws",
        *,
        engine: str = "docker",
        uv_binary: str = _DEFAULT_UV_BINARY,
        wheel_dir: str = _DEFAULT_WHEEL_DIR,
        runner: Runner | None = None,
        log_streamer: Callable[[str, str], AsyncIterator[bytes]] | None = None,
    ) -> None:
        self._cli = devcontainer_cli
        self._runtime_url = runtime_control_plane_url
        self._engine = engine
        self._uv_binary = uv_binary
        self._wheel_dir = wheel_dir
        self._runner = runner or _default_runner
        self._log_streamer = log_streamer or _default_log_streamer

    async def inject(self, devcontainer_id: str, container_id: str, local_path: str) -> bool:
        logger.info("runtime injection: %s into container %s", devcontainer_id, container_id)
        agent_url = resolve_runtime_control_plane_url(self._runtime_url)
        if not await self._bootstrap(devcontainer_id, container_id, local_path, agent_url):
            return False
        return await self._spawn(devcontainer_id, local_path, agent_url)

    async def _bootstrap(
        self, devcontainer_id: str, container_id: str, local_path: str, agent_url: str
    ) -> bool:
        wheel = self._find_wheel()
        if wheel is None:
            logger.warning("Runtime injection skipped: no .whl found in %s", self._wheel_dir)
            return False

        container_wheel_path = f"{_CONTAINER_WHEEL_DIR}/{wheel.name}"

        if not await self._run(
            [self._engine, "cp", self._uv_binary, f"{container_id}:{_CONTAINER_UV_DEST}"],
            "cp uv binary",
            devcontainer_id,
        ):
            return False

        if not await self._run(
            [self._engine, "cp", str(wheel), f"{container_id}:{container_wheel_path}"],
            "cp wheel",
            devcontainer_id,
        ):
            return False

        payload = (
            "set -e -o pipefail\n"
            f"{_CONTAINER_UV_DEST} tool install --python 3.13 --from {container_wheel_path} vibing"
            f" 2>&1 | tee {CONTAINER_LOG_PATH}\n"
            'export PATH="$HOME/.local/bin:$PATH"\n'
            f"vibing runtime preflight --control-plane-url {agent_url}"
            f" 2>&1 | tee -a {CONTAINER_LOG_PATH}\n"
        )
        return await self._exec(local_path, payload, "bootstrap", devcontainer_id)

    async def _spawn(self, devcontainer_id: str, local_path: str, agent_url: str) -> bool:
        payload = (
            'export PATH="$HOME/.local/bin:$PATH"\n'
            f"nohup vibing runtime devcontainer"
            f" --control-plane-url {agent_url}"
            f" --devcontainer-id {devcontainer_id}"
            f" >>{CONTAINER_LOG_PATH} 2>&1 &\n"
            f"echo $! >{CONTAINER_PID_PATH}\n"
        )
        if await self._exec(local_path, payload, "spawn", devcontainer_id):
            logger.info("runtime injection launched: %s (waiting for WS connect)", devcontainer_id)
            return True
        return False

    async def _exec(self, local_path: str, payload: str, step: str, context: str) -> bool:
        return await self._run(
            [self._cli, "exec", "--workspace-folder", local_path, "--", "bash", "-lc", payload],
            f"devcontainer exec ({step})",
            context,
        )

    async def resolve_container_id(self, local_path: str) -> str | None:
        label = f"label=devcontainer.local_folder={local_path}"
        try:
            result = await self._runner([self._engine, "ps", "-q", "--filter", label])
        except FileNotFoundError:
            return None
        if result.returncode != 0:
            return None
        ids = result.stdout.split()
        return ids[0] if ids else None

    async def inject_by_path(self, devcontainer_id: str, local_path: str) -> bool:
        container_id = await self.resolve_container_id(local_path)
        if container_id is None:
            logger.warning("inject: no running container for %s (%s)", devcontainer_id, local_path)
            return False
        return await self.inject(devcontainer_id, container_id, local_path)

    async def stop_runtime(self, local_path: str) -> bool:
        container_id = await self.resolve_container_id(local_path)
        if container_id is None:
            return False
        kill = f'kill "$(cat {CONTAINER_PID_PATH})" 2>/dev/null || true'
        return await self._run(
            [self._engine, "exec", container_id, "bash", "-lc", kill],
            "stop runtime",
            local_path,
        )

    async def stream_log(self, local_path: str) -> AsyncIterator[bytes]:
        container_id = await self.resolve_container_id(local_path)
        if container_id is None:
            return
        async for chunk in self._log_streamer(self._engine, container_id):
            yield chunk

    def _find_wheel(self) -> Path | None:
        wheels = sorted(Path(self._wheel_dir).glob("*.whl"))
        return wheels[0] if wheels else None

    async def _run(self, command: list[str], step: str, context: str) -> bool:
        try:
            result = await self._runner(command)
        except FileNotFoundError:
            logger.warning(
                "Runtime injection failed at '%s' for %s: binary not found: %s",
                step,
                context,
                command[0],
            )
            return False
        if result.returncode != 0:
            logger.warning(
                "Runtime injection failed at '%s' for %s (exit %d):\nstdout: %s\nstderr: %s",
                step,
                context,
                result.returncode,
                result.stdout[-2000:],
                result.stderr[-2000:],
            )
            return False
        return True
