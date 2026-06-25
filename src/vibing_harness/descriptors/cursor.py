"""Cursor CLI (`cursor-agent`) descriptor. Two auth paths, checked in cost order:

1. Interactive subscription login (`cursor-agent login`), read back via
   `cursor-agent status --format json` → `isAuthenticated`. Preferred — flat-rate, cheaper
   than metered api-key usage — and needs no env injection: the CLI uses its own session.
2. Our stored api-key (written by the Control Plane), injected as CURSOR_API_KEY and
   validated via `cursor-agent models`, which honors the key and exits non-zero on a
   missing/invalid one. Used only when not logged in interactively.

`status` reflects only the login session (it ignores CURSOR_API_KEY), so it can't speak for
the api-key path — hence the separate `models` probe for case 2."""

import json

from vibing_harness.base import HarnessDescriptor
from vibing_harness.executor import Executor

_BINARY = "cursor-agent"
_CRED_PATH = ".config/vibing-harness/cursor.json"
_INSTALL = "curl https://cursor.com/install -fsS | bash"


class CursorDescriptor(HarnessDescriptor):
    name = "cursor"
    default_model = "composer-2.5"

    async def is_installed(self, ex: Executor) -> bool:
        return (await ex.run([_BINARY, "--version"])).returncode == 0

    def install_argv(self) -> list[str]:
        return ["bash", "-c", _INSTALL]

    async def install(self, ex: Executor) -> None:
        await ex.run(self.install_argv())

    async def _api_key(self, ex: Executor) -> str:
        raw = await ex.read(_CRED_PATH)
        if raw is None:
            return ""
        return json.loads(raw).get("api_key", "")

    async def _logged_in(self, ex: Executor) -> bool:
        res = await ex.run([_BINARY, "status", "--format", "json"])
        if res.returncode != 0:
            return False
        try:
            return bool(json.loads(res.stdout).get("isAuthenticated"))
        except json.JSONDecodeError:
            return False

    async def is_authenticated(self, ex: Executor) -> bool:
        if await self._logged_in(ex):
            return True
        key = await self._api_key(ex)
        if not key:
            return False
        return (await ex.run([_BINARY, "models"], env={"CURSOR_API_KEY": key})).returncode == 0

    async def write_credentials(self, ex: Executor, blob: dict) -> None:
        await ex.write(_CRED_PATH, json.dumps({"api_key": blob["api_key"]}).encode())

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return [_BINARY, "-p", prompt, "--model", model, "--force", "--output-format", "text"]

    async def spawn_env(self, ex: Executor) -> dict[str, str]:
        if await self._logged_in(ex):
            return {}  # use the subscription session; don't inject the metered key
        key = await self._api_key(ex)
        return {"CURSOR_API_KEY": key} if key else {}

    def extract_result(self, stdout: str) -> str:
        return stdout.strip()
