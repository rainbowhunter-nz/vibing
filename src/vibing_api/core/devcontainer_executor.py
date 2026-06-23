"""DevcontainerExecutor: the Control Plane's vibing_harness.Executor, backed by
`devcontainer exec` (remoteUser-correct). A PIPE-based runner — distinct from
DevcontainerCliAdapter's temp-file runner, which uses stdin=DEVNULL to dodge the
`devcontainer up` keep-alive pipe-hang — so we can stream install output live and
pipe credentials to stdin. Short-lived `exec` calls stream over pipes safely.

Path args are home-relative; read/write wrap in `bash -c` so $HOME expands in-container."""

import asyncio
import shlex
from collections.abc import AsyncIterator, Callable

from vibing_harness import CommandResult

StreamRunner = Callable[[list[str], bytes | None], AsyncIterator[bytes]]


async def _default_runner(argv: list[str], stdin: bytes | None) -> AsyncIterator[bytes]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None
    if stdin is not None and proc.stdin is not None:
        proc.stdin.write(stdin)
        proc.stdin.close()
    async for chunk in proc.stdout:
        yield chunk
    await proc.wait()


class DevcontainerExecutor:
    def __init__(
        self, local_path: str, *, cli: str = "devcontainer", runner: StreamRunner | None = None
    ) -> None:
        self._local_path = local_path
        self._cli = cli
        self._runner = runner or _default_runner

    def _exec(self, argv: list[str]) -> list[str]:
        return [self._cli, "exec", "--workspace-folder", self._local_path, *argv]

    async def _collect(self, argv: list[str], stdin: bytes | None = None) -> bytes:
        out = bytearray()
        async for chunk in self._runner(self._exec(argv), stdin):
            out.extend(chunk)
        return bytes(out)

    async def _run_with_rc(self, argv: list[str]) -> CommandResult:
        joined = " ".join(shlex.quote(a) for a in argv)
        shell = f"{joined}; printf '\\n__rc=%d__' \"$?\""
        raw = (await self._collect(["bash", "-c", shell])).decode(errors="replace")
        rc = 0
        marker = raw.rfind("__rc=")
        if marker != -1:
            try:
                rc = int(raw[marker + 5 : raw.index("__", marker + 5)])
            except ValueError:
                rc = 0
            raw = raw[:marker].rstrip("\n")
        return CommandResult(returncode=rc, stdout=raw, stderr="")

    async def run(self, argv: list[str]) -> CommandResult:
        return await self._run_with_rc(argv)

    async def read(self, path: str) -> bytes | None:
        result = await self._run_with_rc(["bash", "-c", f'cat "$HOME/{path}"'])
        if result.returncode != 0:
            return None
        return result.stdout.encode()

    async def write(self, path: str, data: bytes, mode: int = 0o600) -> None:
        umask = 0o777 ^ mode
        shell = f'umask {umask:03o}; mkdir -p "$(dirname "$HOME/{path}")"; cat > "$HOME/{path}"'
        await self._collect(["bash", "-c", shell], stdin=data)

    async def stream(self, argv: list[str]) -> AsyncIterator[str]:
        buffer = ""
        async for chunk in self._runner(self._exec(argv), None):
            buffer += chunk.decode(errors="replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                yield line
        if buffer:
            yield buffer
