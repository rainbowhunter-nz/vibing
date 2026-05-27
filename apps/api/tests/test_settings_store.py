import json
from pathlib import Path

from vibing_api.core import settings_store


def test_load_returns_default_when_file_missing(settings_file: Path) -> None:
    assert not settings_file.exists()
    stored = settings_store.load()
    assert stored.workspace_storage_location == str(settings_file.parent / "workspaces")


def test_update_writes_file_and_load_reads_it(settings_file: Path) -> None:
    settings_store.update("/tmp/ws-a")
    assert json.loads(settings_file.read_text())["workspace_storage_location"] == "/tmp/ws-a"
    assert settings_store.load().workspace_storage_location == "/tmp/ws-a"


def test_load_ignores_unknown_keys(settings_file: Path) -> None:
    settings_file.write_text(
        json.dumps({"workspace_storage_location": "/tmp/ws-b", "bogus": 1})
    )
    assert settings_store.load().workspace_storage_location == "/tmp/ws-b"


def test_load_falls_back_to_default_on_malformed_file(settings_file: Path) -> None:
    settings_file.write_text("not json{")
    assert settings_store.load().workspace_storage_location == str(
        settings_file.parent / "workspaces"
    )
