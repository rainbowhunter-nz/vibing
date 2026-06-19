from vibing_devcontainer_runtime.harness.codex import CodexAdapter
from vibing_devcontainer_runtime.harness.cursor import CursorAdapter
from vibing_devcontainer_runtime.harness.registry import build_adapters


def test_registry_has_codex_and_cursor(tmp_path):
    def factory(argv, cwd, env):  # not invoked here
        raise AssertionError

    adapters = build_adapters(factory, tmp_path)
    assert set(adapters) == {"codex", "cursor"}
    assert isinstance(adapters["codex"], CodexAdapter)
    assert isinstance(adapters["cursor"], CursorAdapter)


def test_registry_defaults_to_real_factory_and_home():
    adapters = build_adapters()
    assert set(adapters) == {"codex", "cursor"}
