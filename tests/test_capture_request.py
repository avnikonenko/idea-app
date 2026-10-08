from pathlib import Path
import os
import sqlite3
import subprocess
import sys
import time
import pytest
from PySide6.QtNetwork import QLocalSocket
from idea.capture_request import CaptureServer, endpoint, request_capture


def test_request_handles_fragmentation_and_rejects_invalid_commands(tmp_path, qtbot):
    calls = []
    db = tmp_path / "db"
    server = CaptureServer(db, lambda: calls.append("capture"))
    try:
        for pieces, accepted in [([b"cap", b"ture\n"], True), ([b"delete\n"], False), ([b"x" * 40], False)]:
            socket = QLocalSocket()
            socket.connectToServer(endpoint(db))
            assert socket.waitForConnected(500)
            for piece in pieces:
                socket.write(piece)
                socket.flush()
                qtbot.wait(10)
            if accepted:
                qtbot.waitUntil(lambda: len(calls) == 1)
                assert socket.readAll().data() == b"ok\n"
            else:
                qtbot.waitUntil(lambda: socket.state() == QLocalSocket.LocalSocketState.UnconnectedState)
            socket.abort()
        assert calls == ["capture"]
        assert Path(endpoint(db)).stat().st_mode & 0o077 == 0
    finally:
        server.close()
    assert not Path(endpoint(db)).exists()


def test_socket_paths_are_per_database_and_preserve_existing_files(tmp_path, qapp):
    first, second = tmp_path / "first", tmp_path / "second"
    assert endpoint(first) != endpoint(second)
    occupied = Path(endpoint(first))
    occupied.write_text("Preserve me")
    with pytest.raises(OSError, match="occupied"):
        CaptureServer(first, lambda: None)
    assert occupied.read_text() == "Preserve me"


@pytest.mark.parametrize("already_running", [False, True])
def test_capture_cli_starts_or_reuses_application_without_losing_edits(tmp_path, already_running):
    database = tmp_path / "db"
    ready = tmp_path / "ready"
    code = '''
import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from idea.ui.main_window import MainWindow
from idea.app import main
QMessageBox.warning = lambda *args: (_ for _ in ()).throw(AssertionError(str(args[1:])))
original_init = MainWindow.__init__
original_capture = MainWindow.quick_capture
def initialize(window, *args, **kwargs):
    original_init(window, *args, **kwargs)
    window.new_idea()
    window.editor.content.setPlainText("Existing unsaved idea")
    QTimer.singleShot(20, lambda: Path(sys.argv[2]).write_text("ready"))
def capture(window):
    original_capture(window)
    assert window.capture is not None
    window.capture.content.setPlainText("Shortcut capture")
    window.capture.save()
    QTimer.singleShot(50, window.quit_application)
MainWindow.__init__ = initialize
MainWindow.quick_capture = capture
QTimer.singleShot(10000, lambda: QApplication.exit(3))
raise SystemExit(main(["--database", sys.argv[1], "--config", sys.argv[3], "--no-tray"] + ([] if sys.argv[4] == "True" else ["--capture"])))
'''
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    process = subprocess.Popen([sys.executable, "-c", code, str(database), str(ready), str(tmp_path / "config.toml"), str(already_running)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        if already_running:
            deadline = time.monotonic() + 5
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            assert ready.exists()
            bad_config = tmp_path / "bad.toml"
            bad_config.write_text("invalid TOML (")
            request = subprocess.run([sys.executable, "-m", "idea", "--capture", "--database", str(database), "--config", str(bad_config)], env=env, capture_output=True, text=True, timeout=5)
            assert request.returncode == 0, request.stderr
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stderr
        with sqlite3.connect(database) as conn:
            assert {row[0] for row in conn.execute("SELECT content FROM ideas")} == {"Existing unsaved idea", "Shortcut capture"}
        assert not Path(str(database) + ".lock").exists()
        assert not Path(endpoint(database)).exists()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=3)


def test_missing_instance_returns_failure_without_creating_files(tmp_path, qapp):
    database = tmp_path / "missing.db"
    assert not request_capture(database)
    assert list(tmp_path.iterdir()) == []


def test_relative_database_alias_uses_same_endpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert endpoint(Path("notes.db")) == endpoint(tmp_path / "notes.db")
