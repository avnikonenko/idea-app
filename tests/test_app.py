import os
import subprocess
import sys


def test_packaged_application_launch_and_graceful_exit(tmp_path):
    code = '''
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from idea.ui.main_window import MainWindow
from idea.app import main
original = MainWindow.show
def show(window):
    original(window)
    assert QApplication.desktopFileName() == "idea-inbox"
    assert not window.windowIcon().isNull()
    window.new_idea()
    window.editor.content.setPlainText("Persist across launch")
    QTimer.singleShot(50, window.close)
MainWindow.show = show
raise SystemExit(main())
'''
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "XDG_DATA_HOME": str(tmp_path / "data"), "XDG_CONFIG_HOME": str(tmp_path / "config")}
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    import sqlite3
    with sqlite3.connect(tmp_path / "data/idea/ideas.db") as conn:
        assert conn.execute("SELECT content FROM ideas").fetchone()[0] == "Persist across launch"
    assert (tmp_path / "config/idea/config.toml").exists()
    assert not (tmp_path / "data/idea/ideas.db.lock").exists()


import pytest

@pytest.mark.parametrize("mode,available,visible", [
    ("--tray", True, False), ("--tray", False, True), ("--no-tray", True, True),
])
def test_startup_modes_capture_and_safe_exit(tmp_path, mode, available, visible):
    code = '''
import sys, traceback
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from idea.ui.main_window import MainWindow
from idea.app import main
QSystemTrayIcon.isSystemTrayAvailable = lambda: sys.argv[2] == "True"
original = MainWindow.__init__
def initialize(window, *args, **kwargs):
    original(window, *args, **kwargs)
    def run():
        try:
            assert window.isVisible() == (sys.argv[3] == "True")
            if sys.argv[1] == "--no-tray":
                assert window.tray is None
            window.quick_capture()
            assert window.capture.isVisible()
            window.capture.content.setPlainText("Panel mode capture")
            window.capture.save()
            assert window.quit_application()
        except Exception:
            traceback.print_exc()
            QApplication.exit(2)
    QTimer.singleShot(50, run)
MainWindow.__init__ = initialize
raise SystemExit(main([sys.argv[1]]))
'''
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "XDG_DATA_HOME": str(tmp_path / "data"), "XDG_CONFIG_HOME": str(tmp_path / "config")}
    config = tmp_path / "config/idea/config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('theme = "light"\nsplitter = [150, 250, 500]\nwidth = 900\nheight = 600\n')
    result = subprocess.run([sys.executable, "-c", code, mode, str(available), str(visible)], env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    import sqlite3
    from idea.config import Config
    with sqlite3.connect(tmp_path / "data/idea/ideas.db") as conn:
        assert conn.execute("SELECT content FROM ideas").fetchone()[0] == "Panel mode capture"
    assert not (tmp_path / "data/idea/ideas.db.lock").exists()
    if not visible:
        assert Config.load(config).splitter == [150, 250, 500]
        assert Config.load(config).width == 900
