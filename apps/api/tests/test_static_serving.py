from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.config import settings
from vibing_api.main import create_app


def test_static_dir_defaults_to_none() -> None:
    assert settings.static_dir is None
