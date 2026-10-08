import sqlite3
import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
from idea.config import Config
from idea.ui.main_window import MainWindow
from idea.ui.tray import IdeaTray


@pytest.fixture
def tray_window(repo, qtbot, monkeypatch):
    # The tests exercise lifecycle without registering a real desktop icon.
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    monkeypatch.setattr(QSystemTrayIcon, "show", lambda self: self.setProperty("test_visible", True))
    monkeypatch.setattr(QSystemTrayIcon, "hide", lambda self: self.setProperty("test_visible", False))
    monkeypatch.setattr(QSystemTrayIcon, "isVisible", lambda self: bool(self.property("test_visible")))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: None)
    previous = QApplication.instance().quitOnLastWindowClosed()
    window = MainWindow(repo, Config())
    qtbot.addWidget(window)
    window.tray = IdeaTray(window)
    window.show()
    yield window
    window.dirty = False
    if window.capture is not None:
        window.capture.content.clear()
        window.capture.tags.selected.clear()
        window.capture.project.reload(None)
        window.capture.reject()
    window.quitting = True
    window.tray.hide()
    window.close()
    QApplication.instance().setQuitOnLastWindowClosed(previous)


def test_panel_add_note_uses_capture_and_same_database(tray_window, repo):
    window = tray_window
    window.tray.add_action.trigger()
    capture = window.capture
    assert capture is not None and capture.isVisible()
    capture.content.setPlainText("Panel capture 🧠")
    capture.save()
    assert window.capture is None
    assert repo.search()[0].content == "Panel capture 🧠"
    assert window.tray.available()


def test_close_hides_window_and_saves_edits(tray_window, repo):
    window = tray_window
    window.new_idea()
    identity = window.editor.idea_id
    window.editor.content.setPlainText("Save before hiding")
    assert not window.close()  # Closing is intentionally intercepted to retain the tray.
    assert not window.isVisible() and window.tray.available()
    assert repo.get_idea(identity).content == "Save before hiding"
    assert not window.search_timer.isActive()
    assert not QApplication.instance().quitOnLastWindowClosed()
    window.tray.open_action.trigger()
    assert window.isVisible()


def test_capture_after_hidden_editor_leaves_panel_running(tray_window, repo):
    window = tray_window
    window.close()
    window.tray.activated(QSystemTrayIcon.ActivationReason.Trigger)
    capture = window.capture
    assert capture is not None and capture.isVisible() and not window.isVisible()
    capture.content.setPlainText("Capture while editor is hidden")
    capture.save()
    assert window.tray.available() and not window.isVisible()
    assert repo.search()[0].content == "Capture while editor is hidden"


def test_quit_preserves_failed_save_and_then_exits(tray_window, repo, monkeypatch):
    window = tray_window
    window.new_idea()
    identity = window.editor.idea_id
    window.editor.content.setPlainText("Must survive failed quit")
    original = repo.update_idea
    monkeypatch.setattr(repo, "update_idea", lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("disk full")))
    quit_calls = []
    monkeypatch.setattr(QApplication.instance(), "quit", lambda: quit_calls.append(True))
    assert not window.quit_application()
    assert window.isVisible() and window.tray.available() and window.dirty
    assert window.editor.content.toPlainText() == "Must survive failed quit"
    assert quit_calls == []
    monkeypatch.setattr(repo, "update_idea", original)
    assert window.quit_application()
    assert repo.get_idea(identity).content == "Must survive failed quit"
    assert not window.tray.available() and quit_calls == [True]


def test_quit_cannot_discard_capture_without_confirmation(tray_window, monkeypatch):
    window = tray_window
    window.quick_capture()
    window.capture.content.setPlainText("Pending capture")
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Cancel)
    assert not window.quit_application()
    assert window.capture.content.toPlainText() == "Pending capture"
    assert window.tray.available()


def test_no_panel_falls_back_to_normal_close(tray_window, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    assert tray_window.close()
    assert not tray_window.isVisible()


def test_panel_click_reuses_capture(tray_window):
    window = tray_window
    window.tray.activated(QSystemTrayIcon.ActivationReason.Trigger)
    first = window.capture
    window.tray.activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert window.capture is first
    window.tray.activated(QSystemTrayIcon.ActivationReason.Context)
    assert window.capture is first
