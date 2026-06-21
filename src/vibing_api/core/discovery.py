"""Folder discovery of devcontainers (virtual, never persisted).

Non-recursive scan of a configured directory: each immediate subdirectory that
contains a `.devcontainer/` folder is one devcontainer. Stable uuid5 id keyed on
the absolute local_path so start/stop/inject/harness/runtime-WS all agree.
"""

import uuid
from dataclasses import dataclass
from pathlib import Path

_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


@dataclass(frozen=True)
class DiscoveredDevcontainer:
    id: str
    name: str
    local_path: str


def discovered_id(local_path: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, local_path))


def scan(devcontainers_dir: str | None) -> list[DiscoveredDevcontainer]:
    if not devcontainers_dir:
        return []
    root = Path(devcontainers_dir)
    if not root.is_dir():
        return []
    out: list[DiscoveredDevcontainer] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or not (child / ".devcontainer").is_dir():
            continue
        path = str(child)
        out.append(DiscoveredDevcontainer(discovered_id(path), child.name, path))
    return out
