from vibing_api.core.vocabularies import DevcontainerStatus


def test_created_status_removed() -> None:
    assert not hasattr(DevcontainerStatus, "CREATED")
    assert {s.value for s in DevcontainerStatus} == {
        "starting",
        "running",
        "stopping",
        "stopped",
        "error",
    }
