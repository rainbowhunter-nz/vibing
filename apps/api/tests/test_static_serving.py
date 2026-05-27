from vibing_api.core.config import settings


def test_static_dir_defaults_to_none() -> None:
    assert settings.static_dir is None
