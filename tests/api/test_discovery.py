from vibing_api.core.discovery import discovered_id, scan


def _make_dc(parent, name, with_dotdir=True):
    d = parent / name
    d.mkdir()
    if with_dotdir:
        (d / ".devcontainer").mkdir()
    return d


def test_scan_none_dir_is_empty() -> None:
    assert scan(None) == []


def test_scan_missing_dir_is_empty(tmp_path) -> None:
    assert scan(str(tmp_path / "missing")) == []


def test_scan_finds_only_dirs_with_dotdevcontainer(tmp_path) -> None:
    _make_dc(tmp_path, "alpha")
    _make_dc(tmp_path, "beta")
    _make_dc(tmp_path, "plain", with_dotdir=False)
    (tmp_path / "afile").write_text("x")

    found = {d.name: d for d in scan(str(tmp_path))}
    assert set(found) == {"alpha", "beta"}
    assert found["alpha"].local_path == str(tmp_path / "alpha")


def test_scan_is_not_recursive(tmp_path) -> None:
    outer = _make_dc(tmp_path, "outer")
    _make_dc(outer, "inner")  # nested; must be ignored
    assert {d.name for d in scan(str(tmp_path))} == {"outer"}


def test_id_is_stable_for_path() -> None:
    assert discovered_id("/a/b") == discovered_id("/a/b")
    assert discovered_id("/a/b") != discovered_id("/a/c")
