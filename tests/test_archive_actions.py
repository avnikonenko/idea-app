from idea.ui.dates import readable_time
import sqlite3
import pytest
from PySide6.QtWidgets import QMessageBox, QMenu
from PySide6.QtCore import QTimer
import idea.ui.main_window as main_window_module
from idea.config import Config
from idea.ui.main_window import MainWindow

@pytest.fixture
def archive_window(repo, qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: None)
    project = repo.create_project("Research")
    tag = repo.create_tag("Follow-up")
    identity = repo.create_idea("Archived content", project, "archived", True, [tag])
    window = MainWindow(repo, Config())
    qtbot.addWidget(window)
    window.show()
    window.views.setCurrentRow(5)
    yield window, identity
    window.dirty = False


def test_restore_to_inbox_preserves_organization_and_creation(archive_window, repo):
    window, identity = archive_window
    before = repo.get_idea(identity)
    window.editor.content.setPlainText("Edited before restore")
    window.restore_archived(identity)
    restored = repo.get_idea(identity)
    assert restored.status == "inbox" and restored.content == "Edited before restore"
    assert (restored.project_id, restored.tags, restored.pinned, restored.created_at) == (before.project_id, before.tags, before.pinned, before.created_at)
    assert restored.updated_at > before.updated_at
    assert window.model.ideas == [] and window.editor.idea_id is None
    window.views.setCurrentRow(1)
    assert window.editor.idea_id == identity


def test_permanent_delete_cancel_then_confirm_and_fts_cleanup(archive_window, repo, monkeypatch):
    window, identity = archive_window
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No)
    window.delete_archived(identity)
    assert repo.get_idea(identity).status == "archived"
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    window.delete_archived(identity)
    assert repo.search("Archived") == []
    assert repo.conn.execute("SELECT COUNT(*) FROM idea_tags WHERE idea_id=?", (identity,)).fetchone()[0] == 0
    assert window.editor.idea_id is None and window.model.ideas == []
    assert repo.projects() and repo.tags()


def test_active_idea_cannot_be_permanently_deleted(archive_window, repo, monkeypatch):
    window, _ = archive_window
    identity = repo.create_idea("Active idea", status="active")
    monkeypatch.setattr(QMessageBox, "question", lambda *a: pytest.fail("Must not ask to delete active idea"))
    window.delete_archived(identity)
    assert repo.get_idea(identity).content == "Active idea"


def test_archive_details_show_creation_and_modified(archive_window, repo, monkeypatch):
    window, identity = archive_window
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a: messages.append(a[2]))
    window.editor.content.setPlainText("Save before details")
    window.show_details(identity)
    idea = repo.get_idea(identity)
    assert messages == [f"Created: {readable_time(idea.created_at)}\nLast modified: {readable_time(idea.updated_at)}"]
    assert idea.content == "Save before details"


def test_archived_context_menu_dispatches_restore(archive_window, repo, monkeypatch):
    window, identity = archive_window
    def choose(menu, *_):
        actions = {action.text(): action for action in menu.actions()}
        assert {"Restore to Inbox", "Delete permanently…", "Details…"} <= actions.keys()
        assert "Archive" not in actions
        actions["Restore to Inbox"].trigger()
    def menu_factory(parent):
        menu = QMenu(parent)
        def invoke():
            try:
                choose(menu)
            finally:
                menu.close()
        QTimer.singleShot(0, invoke)
        return menu
    monkeypatch.setattr(main_window_module, "QMenu", menu_factory)
    window.context_menu(window.list.visualRect(window.list.currentIndex()).center())
    assert repo.get_idea(identity).status == "inbox"


def test_delete_failure_keeps_idea_and_editor(archive_window, repo, monkeypatch):
    window, identity = archive_window
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(repo, "delete_idea", lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError("readonly")))
    window.delete_archived(identity)
    assert repo.get_idea(identity).status == "archived"
    assert window.editor.idea_id == identity


def test_failed_flush_blocks_restore_and_delete(archive_window, repo, monkeypatch):
    window, identity = archive_window
    window.editor.content.setPlainText("Unsaved text")
    monkeypatch.setattr(repo, "update_idea", lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("disk full")))
    monkeypatch.setattr(QMessageBox, "question", lambda *a: pytest.fail("Do not proceed after failed save"))
    window.restore_archived(identity)
    window.delete_archived(identity)
    assert repo.get_idea(identity).status == "archived"
    assert window.editor.content.toPlainText() == "Unsaved text" and window.dirty


def test_readable_timestamp_uses_local_calendar_time(monkeypatch):
    import os
    import time
    previous = os.environ.get("TZ")
    try:
        monkeypatch.setenv("TZ", "Europe/Prague")
        time.tzset()
        assert readable_time("2026-10-08T08:15:30.123456+00:00") == "08.10.2026, 10:15:30 CEST"
        assert readable_time("2026-01-08T08:15:30+00:00") == "08.01.2026, 09:15:30 CET"
    finally:
        if previous is None:
            monkeypatch.delenv("TZ")
        else:
            monkeypatch.setenv("TZ", previous)
        time.tzset()
