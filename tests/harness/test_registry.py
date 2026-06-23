from vibing_harness import descriptors


def test_registry_has_codex_and_cursor():
    d = descriptors()
    assert set(d) == {"codex", "cursor"}
    assert d["codex"].name == "codex"
    assert d["cursor"].name == "cursor"
