"""JSON-file persistence for user-facing settings.

Distinct from the env-driven `Settings` (process config). Only the editable
preference (workspace storage location) is persisted here.
"""

import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel

from vibing_api.core.config import settings


class StoredSettings(BaseModel):
    workspace_storage_location: str


def _path() -> Path:
    return Path(settings.settings_file)


def default_storage_location() -> str:
    return str(_path().parent / "workspaces")


def load() -> StoredSettings:
    path = _path()
    data: dict[str, object] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            loaded = None
        if isinstance(loaded, dict):
            data = loaded
    raw = data.get("workspace_storage_location")
    location = raw if isinstance(raw, str) and raw.strip() else default_storage_location()
    return StoredSettings(workspace_storage_location=location)


def update(workspace_storage_location: str) -> StoredSettings:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"workspace_storage_location": workspace_storage_location}
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    return StoredSettings(workspace_storage_location=workspace_storage_location)
