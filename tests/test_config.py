import pytest
from idea.config import Config, data_path, config_path

def test_config_atomic_roundtrip_and_xdg(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    assert Config.load(path).theme == "dark"
    config = Config("dark", [150, 200, 500], 850, 600)
    config.save(path)
    assert Config.load(path) == config
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert data_path() == tmp_path / "data/idea/ideas.db"
    assert config_path() == tmp_path / "config/idea/config.toml"
    path.write_text('theme = "invalid"')
    with pytest.raises(ValueError):
        Config.load(path)


@pytest.mark.parametrize("value", ["", "relative/path"])
def test_invalid_or_empty_xdg_variables_use_stable_defaults(monkeypatch, value, caplog):
    from pathlib import Path
    monkeypatch.setenv("XDG_DATA_HOME", value)
    monkeypatch.setenv("XDG_CONFIG_HOME", value)
    assert data_path() == Path.home() / ".local/share/idea/ideas.db"
    assert config_path() == Path.home() / ".config/idea/config.toml"
    if value:
        assert "XDG_DATA_HOME" in caplog.text and "XDG_CONFIG_HOME" in caplog.text


@pytest.mark.parametrize("text", ["", "width = 900\nheight = 600\n"])
def test_preferences_without_theme_default_to_dark(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text)
    assert Config().theme == Config.load(path).theme == "dark"


def test_explicit_light_preference_is_preserved(tmp_path):
    path = tmp_path / "config.toml"
    config = Config(theme="light")
    config.save(path)
    assert Config.load(path) == config
