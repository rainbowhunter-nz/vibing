from vibing_api.core import file_config


def test_returns_none_when_file_absent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIBING_CONFIG_FILE", str(tmp_path / "nope.yaml"))
    assert file_config.load_devcontainers_dir() is None


def test_reads_devcontainers_dir(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "vibing.yaml"
    cfg.write_text("devcontainers_dir: /srv/devcontainers\n")
    monkeypatch.setenv("VIBING_CONFIG_FILE", str(cfg))
    assert file_config.load_devcontainers_dir() == "/srv/devcontainers"


def test_missing_key_returns_none(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "vibing.yaml"
    cfg.write_text("other: 1\n")
    monkeypatch.setenv("VIBING_CONFIG_FILE", str(cfg))
    assert file_config.load_devcontainers_dir() is None


def test_default_path_is_sibling_of_db(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("VIBING_CONFIG_FILE", raising=False)
    monkeypatch.setattr(file_config.settings, "database_url", f"sqlite:///{tmp_path / 'vibing.db'}")
    assert file_config.config_file_path() == tmp_path / "vibing.yaml"
