"""Command type vocabulary.

Commands represent user intent or control-plane requests sent toward the
runtime. They are defined here as a vocabulary only - dispatch, execution,
and Docker/Podman wiring are out of scope.
"""

from typing import Literal, get_args

CommandType = Literal[
    "start_workspace",
    "stop_workspace",
    "restart_workspace",
    "start_claude_session",
    "stop_claude_session",
    "send_user_input",
    "resolve_approval",
]

COMMAND_TYPES: frozenset[str] = frozenset(get_args(CommandType))
