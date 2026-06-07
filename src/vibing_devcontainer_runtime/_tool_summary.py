"""Shared tool-input summarizer (transcript.py + stream_normalizer.py coupling point)."""

_SUMMARY_LIMIT = 120


def summarize_tool_input(tool_input: object) -> str:
    """Short rendering of a tool's input (never its result)."""
    if isinstance(tool_input, dict):
        rendered = ", ".join(f"{k}={v}" for k, v in tool_input.items())
    else:
        rendered = str(tool_input)
    return rendered[:_SUMMARY_LIMIT]
