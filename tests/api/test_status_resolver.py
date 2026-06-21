from vibing_api.core.status_resolver import resolve_status
from vibing_api.core.vocabularies import DevcontainerStatus


def test_transient_wins_over_docker() -> None:
    assert resolve_status(DevcontainerStatus.STARTING, {"/a"}, "/a") == DevcontainerStatus.STARTING


def test_running_when_folder_present() -> None:
    assert resolve_status(None, {"/a", "/b"}, "/a") == DevcontainerStatus.RUNNING


def test_stopped_when_folder_absent() -> None:
    assert resolve_status(None, {"/b"}, "/a") == DevcontainerStatus.STOPPED
