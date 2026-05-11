import pytest


@pytest.fixture(autouse=True)
def isolated_worlds_dir(tmp_path, monkeypatch):
    root = tmp_path / "worlds_root"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("WORLDS_DIR", str(root))
    from worldforger.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
