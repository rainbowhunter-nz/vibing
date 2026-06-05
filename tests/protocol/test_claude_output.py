from vibing_protocol.claude_output import extract_claude_result_text


def test_extracts_result_from_claude_json_stdout() -> None:
    stdout = (
        '{"type":"result","subtype":"success","is_error":false,'
        '"result":"Hi! How can I help you today?","stop_reason":"end_turn"}'
    )
    assert extract_claude_result_text(stdout) == "Hi! How can I help you today?"


def test_returns_plain_text_unchanged() -> None:
    assert extract_claude_result_text("All tests passed.") == "All tests passed."


def test_uses_last_json_line_when_stdout_has_prefix_logs() -> None:
    stdout = 'log: working\n{"result":"done"}\n'
    assert extract_claude_result_text(stdout) == "done"


def test_returns_input_when_json_has_no_result_field() -> None:
    stdout = '{"type":"result","subtype":"success"}'
    assert extract_claude_result_text(stdout) == stdout
