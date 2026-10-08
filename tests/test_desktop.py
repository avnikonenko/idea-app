import importlib.util
from pathlib import Path
import subprocess
import shutil
import pytest

spec = importlib.util.spec_from_file_location("install_desktop", Path(__file__).parents[1] / "tools/install_desktop.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_desktop_install_is_valid_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    paths = installer.install()
    assert len(paths) == 3
    original = {path: path.read_bytes() for path in paths}
    assert installer.install() == paths
    assert {path: path.read_bytes() for path in paths} == original
    validator = shutil.which("desktop-file-validate")
    if validator:
        subprocess.run([validator, *map(str, paths[1:])], check=True, capture_output=True)
    assert "Terminal=false" in paths[-1].read_text()
    assert "OnlyShowIn" not in paths[-1].read_text()


def test_existing_files_are_preserved_before_any_install(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    existing = tmp_path / "config/autostart/idea-inbox.desktop"
    existing.parent.mkdir(parents=True)
    existing.write_text("Existing settings")
    with pytest.raises(FileExistsError):
        installer.install()
    assert existing.read_text() == "Existing settings"
    assert not (tmp_path / "data").exists()


def test_desktop_exec_quoting():
    assert installer.desktop_exec(Path('/tmp/path with spaces/idea')) == '"/tmp/path with spaces/idea"'
    with pytest.raises(ValueError):
        installer.desktop_exec(Path('/tmp/not=valid'))


def test_previous_autostart_is_upgraded_but_custom_flags_are_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    paths = installer.install()
    autostart = paths[-1]
    assert ' --tray\n' in autostart.read_text()
    old = autostart.read_text().replace(' --tray\n', '\n')
    autostart.write_text(old)
    installer.install()
    assert ' --tray\n' in autostart.read_text()
    custom = autostart.read_text() + 'Hidden=true\n'
    autostart.write_text(custom)
    with pytest.raises(FileExistsError):
        installer.install()
    assert autostart.read_text() == custom


def test_empty_xdg_environment_uses_default_user_directories(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", "")
    monkeypatch.setenv("XDG_CONFIG_HOME", "")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    paths = installer.install()
    assert paths[0] == tmp_path / ".local/share/icons/hicolor/scalable/apps/idea-inbox.svg"
    assert paths[-1] == tmp_path / ".config/autostart/idea-inbox.desktop"
