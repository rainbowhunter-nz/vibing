"""Cursor CLI (`cursor-agent`) descriptor. Auth is an api-key persisted to our own
config file and injected as CURSOR_API_KEY at spawn (the documented automation path)."""

import json

from vibing_harness.base import HarnessDescriptor
from vibing_harness.executor import Executor

_BINARY = "cursor-agent"
_CRED_PATH = ".config/vibing-harness/cursor.json"
_INSTALL = "curl https://cursor.com/install -fsS | bash"


class CursorDescriptor(HarnessDescriptor):
    name = "cursor"

    async def is_installed(self, ex: Executor) -> bool:
        return (await ex.run([_BINARY, "--version"])).returncode == 0

    async def install(self, ex: Executor) -> None:
        await ex.run(["bash", "-c", _INSTALL])

    async def _api_key(self, ex: Executor) -> str:
        raw = await ex.read(_CRED_PATH)
        if raw is None:
            return ""
        return json.loads(raw).get("api_key", "")

    async def is_authenticated(self, ex: Executor) -> bool:
        return bool(await self._api_key(ex))

    async def write_credentials(self, ex: Executor, blob: dict) -> None:
        await ex.write(_CRED_PATH, json.dumps({"api_key": blob["api_key"]}).encode())

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return [_BINARY, "-p", prompt, "--model", model, "--force", "--output-format", "text"]

    async def spawn_env(self, ex: Executor) -> dict[str, str]:
        key = await self._api_key(ex)
        return {"CURSOR_API_KEY": key} if key else {}

    def extract_result(self, stdout: str) -> str:
        return stdout.strip()
