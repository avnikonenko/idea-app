import json
import sqlite3
import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox, QInputDialog, QMenu
from idea.config import Config
from idea.database import Database
from idea.repository import Repository
from idea.export import export_json, import_json, export_markdown
from idea.ui.main_window import MainWindow
from idea.ui.managers import OrganizationManager


def test_group_lifecycle_preserves_ideas_and_default_inbox(repo):
    group = repo.create_group("Research")
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_group("RESEARCH")
    with pytest.raises(ValueError):
        repo.create_group("Inbox")
    first = repo.create_idea("Note", group_id=group)
    second = repo.create_idea("Pinned note", pinned=True, group_id=group)
    other = repo.create_idea("Ordinary inbox")
    before = repo.get_idea(first)
    assert [i.id for i in repo.search(status="inbox", ungrouped=True)] == [other]
    repo.update_group(group, "Renamed")
    assert repo.groups("name")[0].name == "Renamed"
    assert repo.get_idea(first).group_name == "Renamed"
    repo.update_idea(first, "Edited", None, "inbox", False, [])
    assert repo.get_idea(first).group_id == group
    repo.delete_group(group)
    assert repo.groups() == []
    assert len(repo.search(status="inbox", ungrouped=True)) == 3
    assert repo.get_idea(first).created_at == before.created_at
    assert repo.get_idea(first).content == "Edited"
    assert repo.get_idea(second).pinned
    assert all(i.group_id is None for i in repo.search())
    assert repo.search("Edited")[0].id == first


def test_group_delete_failure_rolls_back_all_notes(repo):
    group = repo.create_group("Research")
    identity = repo.create_idea("Note", group_id=group)
    before = repo.get_idea(identity)
    repo.conn.execute("CREATE TRIGGER reject_group_delete BEFORE DELETE ON groups BEGIN SELECT RAISE(ABORT, 'read only'); END")
    with pytest.raises(sqlite3.IntegrityError):
        repo.delete_group(group)
    assert repo.get_idea(identity) == before
    assert repo.groups()[0].id == group


def test_group_filter_combines_project_tags_search_and_pinned(repo):
    group = repo.create_group("Work")
    project = repo.create_project("Research")
    tag = repo.create_tag("Check")
    identity = repo.create_idea("Molecule docking", project, pinned=True, tags=[tag], group_id=group)
    repo.create_idea("Molecule docking", group_id=group)
    repo.create_idea("Molecule docking", project, pinned=True, tags=[tag])
    assert [i.id for i in repo.search("dock", group_id=group, project_id=project, tag_ids=[tag], pinned=True)] == [identity]
    repo.update_idea(identity, "Archived", project, "archived", True, [tag])
    assert repo.get_idea(identity).group_id is None
    assert repo.get_idea(identity).status == "archived"
    with pytest.raises(ValueError):
        repo.create_idea("invalid", status="active", group_id=group)
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_idea("invalid", group_id=99999)
    assert repo.search("invalid") == []


def test_schema_one_upgrade_backs_up_and_preserves_notes(tmp_path):
    path = tmp_path / "old.db"
    db = Database(path, automatic_backup=False)
    repo = Repository(db)
    identity = repo.create_idea("Existing Unicode 🧠", status="active")
    before = repo.get_idea(identity)
    db.connection.executescript("DROP INDEX ideas_group_sort; ALTER TABLE ideas DROP COLUMN group_id; DROP TABLE groups; PRAGMA user_version=1;")
    db.close()
    db = Database(path)
    try:
        assert db.connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert Repository(db).get_idea(identity) == before
        backup = next((tmp_path / "backups").glob("*.db"))
        with sqlite3.connect(backup) as old:
            assert old.execute("PRAGMA user_version").fetchone()[0] == 1
            assert old.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert Repository(db).search("Unicode")[0].id == identity
    finally:
        db.close()


def test_group_json_markdown_and_legacy_import(repo, tmp_path):
    group = repo.create_group("研究")
    repo.create_idea("Grouped note", group_id=group)
    repo.create_group("Empty group")
    source = tmp_path / "export.json"
    export_json(repo, source)
    db = Database(tmp_path / "restored.db", automatic_backup=False)
    target = Repository(db)
    try:
        assert import_json(target, source) == 1
        assert target.search()[0].group_name == "研究"
        assert {g.name for g in target.groups()} == {"研究", "Empty group"}
        assert import_json(target, source) == 1
        assert len(target.groups()) == 2
        markdown = tmp_path / "markdown"
        export_markdown(target, markdown)
        assert '"group": "研究"' in next(markdown.iterdir()).read_text()
        payload = json.loads(source.read_text())
        payload["version"] = 1
        del payload["groups"]
        for idea in payload["ideas"]:
            del idea["group_id"]
        legacy = tmp_path / "legacy.json"
        legacy.write_text(json.dumps(payload))
        assert import_json(target, legacy) == 1
        assert len(target.search(ungrouped=True)) == 1
    finally:
        db.close()


@pytest.mark.parametrize("mutation", [
    lambda p: p["ideas"][0].update(group_id=999),
    lambda p: p["ideas"][0].update(group_id=True),
    lambda p: p["ideas"][0].update(status="active"),
    lambda p: p["ideas"][0].pop("group_id"),
    lambda p: p["groups"][0].update(name="Inbox"),
    lambda p: p.pop("groups"),
])
def test_invalid_group_import_leaves_data_unchanged(repo, tmp_path, mutation):
    group = repo.create_group("Research")
    repo.create_idea("Note", group_id=group)
    source = tmp_path / "export.json"
    export_json(repo, source)
    payload = json.loads(source.read_text())
    mutation(payload)
    source.write_text(json.dumps(payload))
    before = (repo.search(), repo.groups())
    with pytest.raises(ValueError):
        import_json(repo, source)
    assert (repo.search(), repo.groups()) == before


@pytest.fixture
def group_window(repo, qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: None)
    repo.create_idea("Inbox note")
    window = MainWindow(repo, Config())
    qtbot.addWidget(window)
    window.show()
    yield window
    window.dirty = False


def select_group(window, identity):
    row = next(n for n in range(window.views.count()) if window.views.item(n).data(Qt.ItemDataRole.UserRole) == identity)
    window.views.setCurrentRow(row)


def test_gui_create_assign_rename_remove_group(group_window, repo, qtbot, monkeypatch):
    window = group_window
    manager = OrganizationManager(repo, "group", window)
    qtbot.addWidget(manager)
    manager.changed.connect(window.after_management)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Work", True))
    manager.create()
    group = repo.groups()[0].id
    identity = window.editor.idea_id
    window.editor.content.insertPlainText("Edited ")
    window.editor.status.setCurrentIndex(window.editor.status.findData(group))
    assert repo.get_idea(identity).group_id == group
    assert window.model.ideas == []
    select_group(window, group)
    assert window.editor.idea_id == identity
    manager.items.setCurrentRow(0)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Renamed", True))
    manager.rename()
    assert window.views.currentItem().text() == "Renamed"
    assert window.editor.status.currentText() == "Renamed"
    repo.create_idea("Another", group_id=group)
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    manager.items.setCurrentRow(0)
    manager.delete()
    assert window.views.currentRow() == 1
    assert len(window.model.ideas) == 2
    assert repo.get_idea(identity).content == "Edited Inbox note"
    assert all(i.group_id is None for i in repo.search())


def test_context_move_and_remove_are_bound_to_original_idea(group_window, repo, monkeypatch):
    import idea.ui.main_window as main_module
    window = group_window
    identity = window.editor.idea_id
    group = repo.create_group("Work")
    window.organization_changed()
    def choose_menu(parent):
        menu = QMenu(parent)
        def invoke():
            try:
                submenu = next(a.menu() for a in menu.actions() if a.text() == "Move to group")
                next(a for a in submenu.actions() if a.text() == "Work").trigger()
            finally:
                menu.close()
        QTimer.singleShot(0, invoke)
        return menu
    monkeypatch.setattr(main_module, "QMenu", choose_menu)
    window.context_menu(window.list.visualRect(window.list.currentIndex()).center())
    assert repo.get_idea(identity).group_id == group
    select_group(window, group)
    window.editor.content.insertPlainText("Pending ")
    window.move_idea(identity, "inbox")
    assert repo.get_idea(identity).group_id is None
    assert repo.get_idea(identity).content == "Pending Inbox note"
    assert window.model.ideas == []
    window.views.setCurrentRow(1)
    assert window.editor.idea_id == identity


def test_group_removal_save_failure_keeps_unsaved_edits(group_window, repo, monkeypatch):
    window = group_window
    identity = window.editor.idea_id
    window.editor.content.insertPlainText("Pending ")
    monkeypatch.setattr(repo, "update_idea", lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("disk full")))
    window.move_idea(identity, "active")
    assert window.dirty
    assert window.editor.content.toPlainText() == "Pending Inbox note"
    assert repo.get_idea(identity).status == "inbox"
