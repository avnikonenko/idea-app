import os
import subprocess
import sys


def test_packaged_application_launch_and_graceful_exit(tmp_path):
    code = '''
from PySide6.QtCore import QTimer
from idea.ui.main_window import MainWindow
from idea.app import main
original = MainWindow.show
def show(window):
    original(window)
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
