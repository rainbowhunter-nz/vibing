"""CursorAdapter: Cursor CLI (`cursor-agent`). See ADR-0011/0012/0013.

On-disk credential storage is uncertain (likely OS keyring); the documented automation
path is the CURSOR_API_KEY env var, so the blob is an API key persisted to our own config
file and injected as env at spawn.
"""

import json
from pathlib import Path
from typing import Any

from vibing_devcontainer_runtime.harness.base import HarnessAdapter
from vibing_devcontainer_runtime.harness.process import HarnessProcessFactory, run_to_completion

_BINARY = "cursor-agent"
_INSTALL = "curl https://cursor.com/install -fsS | bash"


class CursorAdapter(HarnessAdapter):
    name = "cursor"

    def __init__(self, factory: HarnessProcessFactory, home: Path) -> None:
        self._factory = factory
        self._home = home

    @property
    def _key_path(self) -> Path:
        return self._home / ".config" / "vibing-harness" / "cursor.json"

    def _api_key(self) -> str:
        if not self._key_path.exists():
            return ""
        return json.loads(self._key_path.read_text()).get("api_key", "")

    async def is_installed(self) -> bool:
        result = await run_to_completion(self._factory, [_BINARY, "--version"])
        return result.returncode == 0

    async def install(self) -> None:
        await run_to_completion(self._factory, ["bash", "-c", _INSTALL])

    async def is_authenticated(self) -> bool:
        return bool(self._api_key())

    def write_credentials(self, blob: dict[str, Any]) -> None:
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        self._key_path.write_text(json.dumps({"api_key": blob["api_key"]}))
        self._key_path.chmod(0o600)

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return [_BINARY, "-p", prompt, "--model", model, "--force", "--output-format", "text"]

    def spawn_env(self) -> dict[str, str]:
        key = self._api_key()
        return {"CURSOR_API_KEY": key} if key else {}

    def extract_result(self, stdout: str) -> str:
        return stdout.strip()
