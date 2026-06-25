"""Codex CLI (`codex`) descriptor. Credential path is home-relative; the executor
resolves it against the harness env's $HOME."""

import json

from vibing_harness.base import HarnessDescriptor
from vibing_harness.executor import Executor

_BINARY = "codex"
_CRED_PATH = ".codex/auth.json"


class CodexDescriptor(HarnessDescriptor):
    name = "codex"
    default_model = "gpt-5.5"

    async def is_installed(self, ex: Executor) -> bool:
        return (await ex.run([_BINARY, "--version"])).returncode == 0

    def install_argv(self) -> list[str]:
        return ["npm", "install", "-g", "@openai/codex"]

    async def install(self, ex: Executor) -> None:
        await ex.run(self.install_argv())

    async def is_authenticated(self, ex: Executor) -> bool:
        return (await ex.run([_BINARY, "login", "status"])).returncode == 0

    async def write_credentials(self, ex: Executor, blob: dict) -> None:
        await ex.write(_CRED_PATH, json.dumps(blob["auth_json"]).encode())

    def build_spawn_argv(self, model: str, prompt: str) -> list[str]:
        return [
            _BINARY,
            "exec",
            "--model",
            model,
            "--dangerously-bypass-approvals-and-sandbox",
            prompt,
        ]

    async def spawn_env(self, ex: Executor) -> dict[str, str]:
        return {}

    def extract_result(self, stdout: str) -> str:
        return stdout.strip()
