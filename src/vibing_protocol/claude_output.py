"""Parse human-readable text from `claude --output-format json` stdout."""

import json


def extract_claude_result_text(stdout: str) -> str:
    """Return agent reply text from Claude JSON stdout, or the input unchanged."""
    text = stdout.strip()
    if not text:
        return stdout

    data = _last_json_object(text)
    if data is None:
        return stdout

    result = data.get("result")
    if isinstance(result, str):
        return result
    return stdout


def _last_json_object(text: str) -> dict[str, object] | None:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
