"""Tests for the agent-side Claude JSONL -> normalized turns parser (VIB-104, ADR-0009)."""

import asyncio
from pathlib import Path

import pytest
from vibing_protocol import TextBlock, ToolUseBlock

from vibing_devcontainer_runtime.transcript import TranscriptReader

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def reader() -> TranscriptReader:
    return TranscriptReader(projects_base=FIXTURES, cwd="/test/cwd")


def test_parses_text_and_collapsed_tool_markers(reader: TranscriptReader) -> None:
    turns = asyncio.run(reader.read("sess-1"))

    # user text, assistant text+tool_use, assistant text. tool_result/system/summary skipped.
    assert [t.role for t in turns] == ["user", "assistant", "assistant"]

    assert turns[0].blocks == [TextBlock(text="hello agent")]
    assert turns[0].at == "2026-06-06T00:00:01Z"

    assert turns[1].blocks[0] == TextBlock(text="Sure, let me look.")
    tool = turns[1].blocks[1]
    assert isinstance(tool, ToolUseBlock)
    assert tool.name == "Read"
    assert "/work/main.py" in tool.summary  # short rendering of input, not the result

    assert turns[2].blocks == [TextBlock(text="Done.")]


def test_missing_file_returns_empty(reader: TranscriptReader) -> None:
    assert asyncio.run(reader.read("does-not-exist")) == []


def test_encodes_cwd_to_claude_convention() -> None:
    reader = TranscriptReader(projects_base=Path("/base"), cwd="/workspaces/vibing")
    assert reader._session_path("abc") == Path("/base/-workspaces-vibing/abc.jsonl")
