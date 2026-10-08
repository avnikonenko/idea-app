import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("install_shortcut", Path(__file__).parents[1] / "tools/install_shortcut.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.fixture
def settings(monkeypatch):
    values = {(installer.MEDIA, "custom-keybindings"): ["/existing/"]}
    writes = []
    def read(schema, key):
        return values.get((schema, key), "")
    def write(schema, key, value):
        writes.append((schema, key, value))
        values[schema, key] = value
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    monkeypatch.setattr(installer, "read", read)
    monkeypatch.setattr(installer, "write", write)
    monkeypatch.setattr(installer, "builtin_conflicts", lambda: None)
    return values, writes, write


def test_shortcut_install_is_additive_and_idempotent(settings):
    values, writes, _ = settings
    command = installer.install()
    assert command.endswith(" --capture")
    assert values[installer.ENTRY, "binding"] == "<Control><Alt>n"
    assert values[installer.MEDIA, "custom-keybindings"] == ["/existing/", installer.ENTRY_PATH]
    before = dict(values)
    assert installer.install() == command
    assert values == before


@pytest.mark.parametrize("conflict", ["custom", "own", "builtin"])
def test_existing_shortcuts_are_preserved(settings, monkeypatch, conflict):
    values, writes, _ = settings
    if conflict == "custom":
        values[installer.MEDIA + ".custom-keybinding:/existing/", "binding"] = "<Alt><Primary>N"
    elif conflict == "own":
        values[installer.ENTRY, "command"] = "customized"
    else:
        monkeypatch.setattr(installer, "builtin_conflicts", lambda: (_ for _ in ()).throw(ValueError("already assigned")))
    before = dict(values)
    with pytest.raises(ValueError):
        installer.install()
    assert values == before
    assert writes == []


def test_install_failure_restores_original_settings(settings, monkeypatch):
    values, writes, original_write = settings
    before = dict(values)
    failed = False
    def write(schema, key, value):
        nonlocal failed
        if key == "binding" and not failed:
            failed = True
            raise OSError("simulated settings failure")
        original_write(schema, key, value)
    monkeypatch.setattr(installer, "write", write)
    with pytest.raises(OSError):
        installer.install()
    assert values[installer.MEDIA, "custom-keybindings"] == before[installer.MEDIA, "custom-keybindings"]
    assert all(values[installer.ENTRY, key] == "" for key in ("name", "binding", "command"))


def test_other_desktops_fail_before_mutating_settings(settings, monkeypatch):
    values, writes, _ = settings
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    with pytest.raises(ValueError, match="supports GNOME"):
        installer.install()
    assert not writes
