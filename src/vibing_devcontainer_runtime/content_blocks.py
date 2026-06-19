"""Decode Claude's content blocks into intermediate items — the one place pinned to
Claude's content-block shape (`text` / `tool_use`).

transcript.py and stream_normalizer.py each project these items into their own envelope
(TranscriptBlock / TurnDelta), so the durable transcript and the live Session Stream
decode tool cards identically and cannot drift.
"""

from dataclasses import dataclass

_SUMMARY_LIMIT = 120


@dataclass(frozen=True)
class TextItem:
    text: str


@dataclass(frozen=True)
class ToolItem:
    name: str
    summary: str


ContentItem = TextItem | ToolItem


def _summarize(tool_input: object) -> str:
    """Short rendering of a tool's input (never its result)."""
    if isinstance(tool_input, dict):
        rendered = ", ".join(f"{k}={v}" for k, v in tool_input.items())
    else:
        rendered = str(tool_input)
    return rendered[:_SUMMARY_LIMIT]


def item_from_block(block: object) -> ContentItem | None:
    """Decode a single content block; None for empty text, unknown, or malformed blocks."""
    if not isinstance(block, dict):
        return None
    if block.get("type") == "text":
        text = block.get("text")
        return TextItem(text=text) if isinstance(text, str) and text else None
    if block.get("type") == "tool_use":
        name = block.get("name")
        if isinstance(name, str):
            return ToolItem(name=name, summary=_summarize(block.get("input")))
    return None


def parse_content(content: object) -> list[ContentItem]:
    """Walk Claude content (a string or a list of blocks) into items, in arrival order."""
    if isinstance(content, str):
        return [TextItem(text=content)] if content else []
    if not isinstance(content, list):
        return []
    return [item for block in content if (item := item_from_block(block)) is not None]
