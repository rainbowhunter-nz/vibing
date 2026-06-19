"""CodexAdapter: OpenAI Codex CLI (`codex`). See ADR-0011/0012/0013."""

import json
from pathlib import Path
from typing import Any

from vibing_devcontainer_runtime.harness.base import HarnessAdapter
from vibing_devcontainer_runtime.harness.process import HarnessProcessFactory, run_to_completion

_BINARY = "codex"


class CodexAdapter(HarnessAdapter):
    name = "codex"

    def __init__(self, factory: HarnessProcessFactory, home: Path) -> None:
        self._factory = factory
        self._home = home

    @property
    def _auth_path(self) -> Path:
        return self._home / ".codex" / "auth.json"

    async def is_installed(self) -> bool:
        result = await run_to_completion(self._factory, [_BINARY, "--version"])
        return result.returncode == 0

    async def install(self) -> None:
        await run_to_completion(self._factory, ["npm", "install", "-g", "@openai/codex"])

    async def is_authenticated(self) -> bool:
        result = await run_to_completion(self._factory, [_BINARY, "login", "status"])
        return result.returncode == 0

    def write_credentials(self, blob: dict[str, Any]) -> None:
        self._auth_path.parent.mkdir(parents=True, exist_ok=True)
        self._auth_path.write_text(json.dumps(blob["auth_json"]))
        self._auth_path.chmod(0o600)

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return [
            _BINARY,
            "exec",
            "--model",
            model,
            "--dangerously-bypass-approvals-and-sandbox",
            prompt,
        ]

    def spawn_env(self) -> dict[str, str]:
        return {}

    def extract_result(self, stdout: str) -> str:
        return stdout.strip()
