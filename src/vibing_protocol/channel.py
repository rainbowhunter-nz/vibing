"""Runtime-channel wire codec.

The Control Plane and the Devcontainer Runtime cross the same WebSocket, so
they share one codec for the JSON wire format of channel envelopes.
"""

import json
from typing import Any

from pydantic import BaseModel


def encode(envelope: BaseModel) -> str:
    """Serialize a channel envelope to its JSON wire string."""
    return json.dumps(envelope.model_dump())


def decode(raw: str) -> dict[str, Any] | None:
    """Parse a wire string to a message dict, or None if it is not a JSON object."""
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return message if isinstance(message, dict) else None
