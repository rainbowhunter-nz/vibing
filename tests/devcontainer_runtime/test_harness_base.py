import pytest

from vibing_devcontainer_runtime.harness.base import HarnessAdapter, HarnessStatus


def test_harness_status_fields():
    s = HarnessStatus(name="codex", installed=True, authenticated=False)
    assert (s.name, s.installed, s.authenticated) == ("codex", True, False)


def test_adapter_is_abstract():
    with pytest.raises(TypeError):
        HarnessAdapter()  # type: ignore[abstract]
