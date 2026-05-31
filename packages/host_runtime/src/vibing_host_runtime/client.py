"""Host Runtime Worker configuration and constants.

Transport logic lives in `vibing_runtime_client.RuntimeChannelClient`.
`WorkerConfig` carries host-specific settings (devcontainer CLI path).
"""

from dataclasses import dataclass

DEFAULT_CONTROL_PLANE_URL = "ws://127.0.0.1:8000/api/v1/runtime/ws"
DEFAULT_DEVCONTAINER_CLI = "devcontainer"


@dataclass(frozen=True)
class WorkerConfig:
    control_plane_url: str
    devcontainer_cli: str
