import sqlite3
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox
from idea.config import Config
from idea.ui.main_window import MainWindow
from idea.ui.quick_capture import QuickCapture

@pytest.fixture
def window(repo, qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: None)
    repo.create_idea("First")
    win = MainWindow(repo, Config())
    qtbot.addWidget(win)
    win.show()
    yield win
    win.dirty = False


def test_debounced_autosave(window, repo, qtbot):
    identity = window.editor.idea_id
    window.editor.content.setPlainText("Unsaved Unicode 🧠")
    assert repo.get_idea(identity).content == "First"
    qtbot.waitUntil(lambda: repo.get_idea(identity).content == "Unsaved Unicode 🧠", timeout=2000)
    assert not window.dirty


def test_switch_flushes_and_keeps_selection(window, repo):
    first = window.editor.idea_id
    other = repo.create_idea("Other")
    window.refresh()
    window.editor.content.setPlainText("Saved when switching")
    target = next(n for n, idea in enumerate(window.model.ideas) if idea.id == other)
    window.list.setCurrentIndex(window.model.index(target))
    assert repo.get_idea(first).content == "Saved when switching"
    assert window.editor.idea_id == other
    assert window.list.currentIndex().data(Qt.ItemDataRole.UserRole).id == other


def test_failed_save_blocks_switch_and_shutdown(window, repo, monkeypatch):
    identity = window.editor.idea_id
    other = repo.create_idea("Other")
    window.refresh()
    window.editor.content.setPlainText("Do not lose me")
    original = repo.update_idea
    def fail(*a, **k):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(repo, "update_idea", fail)
    target = next(n for n, idea in enumerate(window.model.ideas) if idea.id == other)
    window.list.setCurrentIndex(window.model.index(target))
    assert window.editor.idea_id == identity
    assert window.editor.content.toPlainText() == "Do not lose me"
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted() and window.dirty
    monkeypatch.setattr(repo, "update_idea", original)
    window.closeEvent(event)
    assert event.isAccepted()
    assert repo.get_idea(identity).content == "Do not lose me"


def test_shutdown_flush_and_config(window, repo, tmp_path):
    identity = window.editor.idea_id
    window.config_path = tmp_path / "settings.toml"
    window.editor.content.setPlainText("Save on close")
    assert window.close()
    assert repo.get_idea(identity).content == "Save on close"
    assert Config.load(window.config_path).splitter == window.splitter.sizes()


def test_metadata_and_colors(window, repo):
    identity = window.editor.idea_id
    project = repo.create_project("Mint", "#E2F3E8")
    a, b = repo.create_tag("A"), repo.create_tag("B")
    window.editor.project.reload(project)
    window.editor.project.changed.emit()
    window.editor.tags.reload([a, b])
    window.editor.tags.changed.emit()
    assert window.flush()
    assert repo.get_idea(identity).project_id == project
    assert len(repo.get_idea(identity).tags) == 2
    repo.update_project(project, "Mint", "#E3F0FA")
    window.after_management()
    assert window.model.ideas[0].project_color == "#E3F0FA"
    window.set_theme("dark")
    assert window.delegate.dark
    window.pin()
    assert repo.get_idea(identity).pinned
    window.archive()
    assert repo.get_idea(identity).status == "archived"


def test_quick_capture_save_and_discard_protection(repo, qtbot, monkeypatch):
    capture = QuickCapture(repo)
    qtbot.addWidget(capture)
    capture.show()
    capture.activateWindow()
    qtbot.waitUntil(capture.isActiveWindow)
    assert capture.content.hasFocus() or capture.content.focusWidget() == capture.content
    capture.content.setPlainText("Capture 🧠\nSecond line")
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Cancel)
    capture.reject()
    assert capture.isVisible()
    qtbot.keyClick(capture.content, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert not capture.isVisible()
    assert repo.search()[0].content == "Capture 🧠\nSecond line"
    assert repo.search()[0].status == "inbox"


def test_editor_shortcuts_preserve_text_navigation(window, qtbot):
    content = window.editor.content
    content.setFocus()
    content.setPlainText("alpha\nbeta")
    cursor = content.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    content.setTextCursor(cursor)
    qtbot.keyClick(content, Qt.Key.Key_Up)
    assert content.textCursor().blockNumber() == 0
    qtbot.keyClick(content, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert content.textCursor().selectedText() == "alpha\u2029beta"


def test_tag_chips_add_remove(window, repo):
    selector = window.editor.tags
    selector.input.setText("Fresh tag")
    selector.add()
    assert len(selector.selected) == 1
    assert window.flush()
    identity = selector.selected[0]
    assert repo.get_idea(window.editor.idea_id).tags[0].name == "Fresh tag"
    selector.remove(identity)
    assert window.flush()
    assert repo.get_idea(window.editor.idea_id).tags == ()


def test_search_failure_retains_pending_edits(window, repo, monkeypatch):
    identity = window.editor.idea_id
    window.editor.content.setPlainText("Pending")
    monkeypatch.setattr(repo, "update_idea", lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("readonly")))
    window.search.setText("No matching result")
    window.refresh()
    assert window.editor.idea_id == identity
    assert window.editor.content.toPlainText() == "Pending"
    assert window.dirty


def test_create_project_from_autocomplete_search_flushes_content(window, repo, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    identity = window.editor.idea_id
    window.editor.content.setPlainText("Keep this content")
    selector = window.editor.project
    selector.combo.setEditText("New project")
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("New project", True))
    selector.create()
    assert repo.get_idea(identity).content == "Keep this content"
    assert window.flush()
    assert repo.get_idea(identity).project_name == "New project"


def test_combined_status_pinned_tag_project_filters(window, repo):
    project = repo.create_project("Filtered")
    tag = repo.create_tag("Specific")
    match = repo.create_idea("match", project, "active", True, [tag])
    repo.create_idea("not pinned", project, "active", False, [tag])
    repo.create_idea("wrong status", project, "inbox", True, [tag])
    window.project_filter.reload(project)
    window.tag_filter.reload([tag])
    window.pinned_filter.setChecked(True)
    window.views.setCurrentRow(3)
    assert [i.id for i in window.model.ideas] == [match]


def test_failed_capture_save_retains_text(repo, qtbot, monkeypatch):
    capture = QuickCapture(repo)
    qtbot.addWidget(capture)
    capture.show()
    capture.content.setPlainText("Pending capture")
    monkeypatch.setattr(repo, "create_idea", lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("disk full")))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: None)
    capture.save()
    assert capture.isVisible() and capture.content.toPlainText() == "Pending capture"
    capture.content.clear()


def test_capture_window_close_emits_finished(repo, qtbot, monkeypatch):
    capture = QuickCapture(repo)
    qtbot.addWidget(capture)
    capture.show()
    capture.content.setPlainText("Discard this")
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Discard)
    with qtbot.waitSignal(capture.finished):
        assert capture.close()


def test_metadata_flushes_text_immediately_and_focus_does_not_touch_timestamp(window, repo):
    identity = window.editor.idea_id
    timestamp = repo.get_idea(identity).updated_at
    window.editor.project.changed.emit()
    assert repo.get_idea(identity).updated_at == timestamp
    window.editor.content.setPlainText("Pending text")
    window.editor.pinned.setChecked(True)
    assert repo.get_idea(identity).content == "Pending text"
    assert repo.get_idea(identity).pinned and not window.dirty


def test_close_stops_pending_search_timer(window):
    window.search.setText("pending search")
    assert window.search_timer.isActive()
    assert window.close()
    assert not window.search_timer.isActive()
    assert not window.save_timer.isActive()


def filtered_pending_edit(window, repo):
    other = repo.create_idea("Keep second")
    intended = repo.create_idea("Keep first")
    window.search.setText("Keep")
    window.refresh()
    assert window.editor.idea_id == intended
    window.editor.content.setPlainText("Content no longer matching search")
    return intended, other


@pytest.mark.parametrize("action", ["archive", "pin"])
def test_actions_stay_bound_to_original_idea_after_flush(window, repo, action):
    intended, other = filtered_pending_edit(window, repo)
    getattr(window, action)()
    assert repo.get_idea(intended).content == "Content no longer matching search"
    if action == "archive":
        assert repo.get_idea(intended).status == "archived"
        assert repo.get_idea(other).status == "inbox"
    else:
        assert repo.get_idea(intended).pinned
        assert not repo.get_idea(other).pinned


@pytest.mark.parametrize("tag_name", ["Reading", "New filtered tag"])
def test_tag_assignment_stays_bound_after_pending_content_changes(window, repo, tag_name):
    intended, other = filtered_pending_edit(window, repo)
    window.editor.tags.input.setText(tag_name)
    window.editor.tags.add()
    assert tag_name in [t.name for t in repo.get_idea(intended).tags]
    assert tag_name not in [t.name for t in repo.get_idea(other).tags]


def test_tag_removal_stays_bound_after_pending_content_changes(window, repo):
    intended, other = filtered_pending_edit(window, repo)
    tag = repo.tags()[0].id
    repo.update_idea(intended, "Keep first", None, "inbox", False, [tag])
    window.dirty = False
    window.editor.load(repo.get_idea(intended))
    window.editor.content.setPlainText("No longer matching search")
    window.editor.tags.remove(tag)
    assert repo.get_idea(intended).tags == ()
    assert repo.get_idea(other).content == "Keep second"


def test_project_creation_stays_bound_after_pending_content_changes(window, repo, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    intended, other = filtered_pending_edit(window, repo)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("New filtered project", True))
    window.editor.project.create()
    assert repo.get_idea(intended).project_name == "New filtered project"
    assert repo.get_idea(other).project_id is None


@pytest.mark.parametrize("name", ["Unassigned", "All projects"])
def test_project_names_matching_selector_labels_keep_ids(window, repo, name):
    project = repo.create_project(name)
    identity = repo.create_idea("Original", project)
    window.refresh()
    window.editor.content.setPlainText("Edited")
    assert window.flush()
    assert repo.get_idea(identity).project_id == project
    window.project_filter.reload(project)
    window.project_filter.combo.setItemText(0, "All projects")
    assert window.project_filter.value() == project
    window.refresh()
    assert [idea.id for idea in window.model.ideas] == [identity]


def test_closed_context_menus_are_released(window, repo, monkeypatch, qtbot):
    from PySide6.QtCore import QTimer, QCoreApplication, QEvent
    from PySide6.QtWidgets import QMenu
    import idea.ui.main_window as main_module
    baseline = len(window.findChildren(QMenu))
    def make_menu(parent):
        menu = QMenu(parent)
        QTimer.singleShot(0, menu.close)
        return menu
    monkeypatch.setattr(main_module, "QMenu", make_menu)
    for _ in range(5):
        window.context_menu(window.list.visualRect(window.list.currentIndex()).center())
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert len(window.findChildren(QMenu)) == baseline
