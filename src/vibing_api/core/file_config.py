"""Optional YAML config file (sibling of vibing.db, or VIBING_CONFIG_FILE).

Currently exposes only `devcontainers_dir` used by folder discovery. Absent
file or key → None → discovery off.
"""

import os
from pathlib import Path

import yaml

from vibing_api.core.config import settings


def config_file_path() -> Path:
    override = os.environ.get("VIBING_CONFIG_FILE")
    if override:
        return Path(override)
    db = settings.database_url.removeprefix("sqlite:///")
    return Path(db).parent / "vibing.yaml"


def load_devcontainers_dir() -> str | None:
    path = config_file_path()
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text()) or {}
    value = data.get("devcontainers_dir") if isinstance(data, dict) else None
    return str(value) if value else None
