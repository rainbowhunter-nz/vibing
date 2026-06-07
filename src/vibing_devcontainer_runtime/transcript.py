"""Parses Claude Code's on-disk JSONL conversation into normalized turns (ADR-0009).

This is the ONLY place pinned to Claude's internal file format. Consumers see the stable
Vibing shape (TranscriptTurn). A missing file is not an error -> empty list; malformed
lines are skipped defensively.
"""

import json
from pathlib import Path

from logzero import logger
from vibing_protocol import TextBlock, ToolUseBlock, TranscriptBlock, TranscriptTurn

from ._tool_summary import summarize_tool_input

_TURN_ROLES = {"user", "assistant"}


def _encode_cwd(cwd: str) -> str:
    """Claude's project-dir convention: path separators become hyphens (/a/b -> -a-b)."""
    return cwd.replace("/", "-")


def _blocks_from_content(content: object) -> list[TranscriptBlock]:
    if isinstance(content, str):
        return [TextBlock(text=content)] if content else []
    if not isinstance(content, list):
        return []
    blocks: list[TranscriptBlock] = []
    for raw in content:
        if not isinstance(raw, dict):
            continue
        if raw.get("type") == "text":
            text = raw.get("text")
            if isinstance(text, str) and text:
                blocks.append(TextBlock(text=text))
        elif raw.get("type") == "tool_use":
            name = raw.get("name")
            if isinstance(name, str):
                blocks.append(
                    ToolUseBlock(name=name, summary=summarize_tool_input(raw.get("input")))
                )
    return blocks


def _turn_id(obj: dict, message: dict) -> str:
    """Claude's stable per-message uuid (ADR-0010): top-level `uuid`, else message `id`."""
    uuid = obj.get("uuid")
    if isinstance(uuid, str) and uuid:
        return uuid
    msg_id = message.get("id")
    return msg_id if isinstance(msg_id, str) else ""


def _turn_from_line(line: str) -> TranscriptTurn | None:
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or obj.get("type") not in _TURN_ROLES:
        return None
    message = obj.get("message")
    if not isinstance(message, dict):
        return None
    role = message.get("role")
    if role not in _TURN_ROLES:
        return None
    blocks = _blocks_from_content(message.get("content"))
    if not blocks:
        return None  # tool_result-only / empty lines carry no conversation
    return TranscriptTurn(
        id=_turn_id(obj, message), role=role, blocks=blocks, at=obj.get("timestamp") or ""
    )


class TranscriptReader:
    """Reads `<projects_base>/<encoded-cwd>/<session_id>.jsonl` into normalized turns."""

    def __init__(self, projects_base: Path | None = None, cwd: str | None = None) -> None:
        self._projects_base = projects_base or Path.home() / ".claude" / "projects"
        self._cwd = cwd or str(Path.cwd())

    def _session_path(self, agent_session_id: str) -> Path:
        return self._projects_base / _encode_cwd(self._cwd) / f"{agent_session_id}.jsonl"

    async def read(self, agent_session_id: str) -> list[TranscriptTurn]:
        path = self._session_path(agent_session_id)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.info("No transcript file for session %s at %s", agent_session_id, path)
            return []
        turns: list[TranscriptTurn] = []
        for line in raw.splitlines():
            turn = _turn_from_line(line)
            if turn is not None:
                turns.append(turn)
        return turns
