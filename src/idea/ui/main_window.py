from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QItemSelectionModel, QSignalBlocker
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QLineEdit, QPushButton, QListView, QListWidget, QLabel, QMenu,
    QMessageBox, QFileDialog, QApplication, QAbstractItemView, QCheckBox)
from ..config import Config
from ..export import export_json, import_json, export_markdown
from .idea_editor import IdeaEditor
from .idea_list import IdeaListModel, IdeaDelegate
from .selectors import ProjectSelector, TagSelector
from .managers import OrganizationManager
from .quick_capture import QuickCapture
from .styles import apply_theme
from .dates import readable_time
from .shortcut_settings import ShortcutSettings

class MainWindow(QMainWindow):
    SAVE_DELAY_MS = 350

    def __init__(self, repo, config: Config, config_path: Path | None = None):
        super().__init__()
        self.repo, self.config, self.config_path = repo, config, config_path
        self.dirty = False
        self.reporting_save_error = False
        self.refreshing = False
        self.capture = None
        self.tray = None
        self.quitting = False
        self.shown_once = False
        self.setWindowTitle("Idea")
        self.resize(config.width, config.height)
        self.setMinimumSize(700, 480)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.flush)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(180)
        self.search_timer.timeout.connect(self.refresh)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        top = QHBoxLayout()
        title = QLabel("IDEA")
        title.setStyleSheet("font-weight: bold; font-size: 18px;")
        top.addWidget(title)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search ideas, projects and tags…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda *_: self.search_timer.start())
        top.addWidget(self.search, 1)
        new = QPushButton("+ New idea")
        new.clicked.connect(self.new_idea)
        top.addWidget(new)
        capture = QPushButton("Quick capture")
        capture.clicked.connect(self.quick_capture)
        top.addWidget(capture)
        layout.addLayout(top)
        self.splitter = QSplitter()
        layout.addWidget(self.splitter, 1)
        sidebar = QWidget()
        sidebar.setMinimumWidth(145)
        side = QVBoxLayout(sidebar)
        self.views = QListWidget()
        self.views.addItems(["All ideas", "Inbox", "Pinned", "Active", "Someday", "Archive"])
        for row, key in enumerate(("all", "inbox", "pinned", "active", "someday", "archived")):
            self.views.item(row).setData(Qt.ItemDataRole.UserRole, key)
        for group in repo.groups():
            self.views.addItem(group.name)
            self.views.item(self.views.count() - 1).setData(Qt.ItemDataRole.UserRole, group.id)
        self.views.setCurrentRow(1)
        self.views.setMaximumHeight(190)
        self.views.currentRowChanged.connect(self.filter_changed)
        side.addWidget(self.views)
        groups = QPushButton("Manage groups")
        groups.clicked.connect(lambda: self.manage("group"))
        side.addWidget(groups)
        self.pinned_filter = QCheckBox("Pinned only")
        self.pinned_filter.toggled.connect(self.filter_changed)
        side.addWidget(self.pinned_filter)
        side.addWidget(QLabel("PROJECT"))
        self.project_filter = ProjectSelector(repo, allow_create=False)
        self.project_filter.combo.setItemText(0, "All projects")
        self.project_filter.changed.connect(self.filter_changed)
        side.addWidget(self.project_filter)
        projects = QPushButton("Manage projects")
        projects.clicked.connect(lambda: self.manage("project"))
        side.addWidget(projects)
        side.addWidget(QLabel("TAGS · match all"))
        self.tag_filter = TagSelector(repo, allow_create=False)
        self.tag_filter.changed.connect(self.filter_changed)
        side.addWidget(self.tag_filter)
        tags = QPushButton("Manage tags")
        tags.clicked.connect(lambda: self.manage("tag"))
        side.addWidget(tags)
        side.addStretch()
        self.splitter.addWidget(sidebar)
        self.list = QListView()
        self.list.setMinimumWidth(170)
        self.list.setUniformItemSizes(True)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setMouseTracking(True)
        self.model = IdeaListModel(self.list)
        self.delegate = IdeaDelegate(self.list)
        self.delegate.dark = config.theme == "dark"
        self.list.setModel(self.model)
        self.list.setItemDelegate(self.delegate)
        self.list.selectionModel().currentChanged.connect(self.selection_changed)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.context_menu)
        self.splitter.addWidget(self.list)
        self.editor = IdeaEditor(repo, before_change=lambda: self.flush(refresh=False))
        self.editor.setMinimumWidth(280)
        self.editor.edited.connect(self.mark_dirty)
        self.editor.metadata_edited.connect(self.save_metadata)
        self.editor.organization_changed.connect(self.organization_changed)
        self.splitter.addWidget(self.editor)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes(config.splitter)
        self.splitter.setStretchFactor(2, 1)
        self.setup_actions()
        apply_theme(QApplication.instance(), config.theme)
        self.refresh()

    def setup_actions(self):
        for sequence, callback in (("Ctrl+N", self.new_idea), ("Ctrl+F", self.focus_search),
                                   ("Ctrl+S", self.flush), ("Ctrl+E", self.archive),
                                   ("Ctrl+P", self.pin), ("Ctrl+Shift+N", self.quick_capture)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
        file = self.menuBar().addMenu("File")
        for name, callback in (("Export JSON…", self.json_export), ("Export Markdown…", self.markdown_export),
                               ("Import JSON…", self.json_import), ("Back up now…", self.backup)):
            action = QAction(name, self)
            action.triggered.connect(callback)
            file.addAction(action)
        file.addSeparator()
        quit_action = QAction("Quit Idea", self)
        quit_action.triggered.connect(self.quit_application)
        file.addAction(quit_action)
        theme = self.menuBar().addMenu("Theme")
        for name in ("light", "dark"):
            action = QAction(name.title(), self)
            action.triggered.connect(lambda checked=False, value=name: self.set_theme(value))
            theme.addAction(action)

        settings = self.menuBar().addMenu("Settings")
        shortcuts = QAction("Keyboard shortcuts…", self)
        shortcuts.triggered.connect(self.show_shortcuts)
        settings.addAction(shortcuts)

    def show_shortcuts(self):
        dialog = ShortcutSettings(self)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()

    def error(self, message, exc):
        QMessageBox.warning(self, message, str(exc))

    def mark_dirty(self):
        self.dirty = True
        self.statusBar().showMessage("Unsaved changes")
        self.save_timer.start(self.SAVE_DELAY_MS)

    def save_metadata(self):
        self.mark_dirty()
        self.flush()

    def flush(self, *, refresh=True) -> bool:
        self.save_timer.stop()
        if self.reporting_save_error:
            return False
        if not self.dirty or self.editor.idea_id is None:
            return True
        try:
            identity = self.editor.idea_id
            values = self.editor.values()
            if values == self.editor.saved_values:
                self.dirty = False
                self.statusBar().showMessage("Saved", 2000)
                return True
            self.repo.update_idea(identity, **values)
            saved = self.repo.get_idea(identity)
        except Exception as exc:
            self.statusBar().showMessage("Save failed — edits retained; Ctrl+S to retry")
            self.reporting_save_error = True
            try:
                self.error("Changes could not be saved; your edits remain in the editor", exc)
            finally:
                self.reporting_save_error = False
            return False
        self.dirty = False
        self.editor.saved_values = values
        self.editor.set_timestamps(saved)
        self.statusBar().showMessage("Saved", 2000)
        if refresh:
            self.refresh(flush=False)
        return True

    def filter_changed(self, *_):
        self.refresh()

    def filter_values(self):
        item = self.views.currentItem()
        view = item.data(Qt.ItemDataRole.UserRole) if item else "inbox"
        status = view if view in ("inbox", "active", "someday", "archived") else None
        return dict(query=self.search.text(), project_id=self.project_filter.value(),
                    tag_ids=self.tag_filter.selected, status=status, pinned=True if view == "pinned" or self.pinned_filter.isChecked() else None,
                    group_id=view if type(view) is int else None, ungrouped=view == "inbox")

    def refresh(self, *, flush=True, preferred=None):
        if self.refreshing:
            return
        if flush and not self.flush(refresh=False):
            return
        selected = preferred if preferred is not None else self.editor.idea_id
        scroll = self.list.verticalScrollBar().value()
        try:
            ideas = self.repo.search(**self.filter_values())
            identities = [i.id for i in ideas]
            target = selected if selected in identities else (identities[0] if identities else None)
            loaded = self.repo.get_idea(target) if target is not None and target != self.editor.idea_id else None
        except Exception as exc:
            self.error("Could not load ideas", exc)
            return
        self.refreshing = True
        try:
            if target != self.editor.idea_id:
                self.editor.load(loaded)
                self.dirty = False
            self.model.replace(ideas)
            if target is not None:
                self.list.setCurrentIndex(self.model.index(identities.index(target)))
            self.list.verticalScrollBar().setValue(scroll)
            self.statusBar().showMessage(f"{len(ideas)} ideas" + (" · unsaved edits" if self.dirty else ""))
        except Exception as exc:
            self.error("Could not load idea organization", exc)
        finally:
            self.refreshing = False

    def selection_changed(self, current, previous):
        if self.refreshing or not current.isValid():
            return
        target = current.data(Qt.ItemDataRole.UserRole).id
        if target == self.editor.idea_id:
            return
        # Flush may reset the model and reorder rows; select again by stable ID.
        if not self.flush():
            self.select_id(self.editor.idea_id)
            return
        try:
            loaded = self.repo.get_idea(target)
            self.editor.load(loaded)
        except Exception as exc:
            self.error("Could not open idea", exc)
            self.select_id(self.editor.idea_id)
            return
        self.select_id(target)

    def select_id(self, identity):
        self.refreshing = True
        try:
            for row, idea in enumerate(self.model.ideas):
                if idea.id == identity:
                    self.list.setCurrentIndex(self.model.index(row))
                    break
        finally:
            self.refreshing = False

    def clear_filters(self):
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.views.blockSignals(True)
        self.views.setCurrentRow(1)
        self.views.blockSignals(False)
        self.pinned_filter.blockSignals(True)
        self.pinned_filter.setChecked(False)
        self.pinned_filter.blockSignals(False)
        self.project_filter.reload(None)
        self.project_filter.combo.setItemText(0, "All projects")
        self.tag_filter.reload([])

    def new_idea(self):
        if not self.flush():
            return
        try:
            identity = self.repo.create_idea()
            self.clear_filters()
            self.refresh(preferred=identity)
            self.editor.content.setFocus()
        except Exception as exc:
            self.error("Could not create idea", exc)

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def change_idea_state(self, identity: int | None, *, archive=False, toggle_pin=False):
        # A save can remove the edited idea from the active search/filter. Keep
        # the action bound to the original ID, not the next selected row.
        if identity is None or not self.flush(refresh=False):
            return
        try:
            idea = self.repo.get_idea(identity)
            self.repo.update_idea(identity, idea.content, idea.project_id,
                                  "archived" if archive else idea.status,
                                  not idea.pinned if toggle_pin else idea.pinned,
                                  [tag.id for tag in idea.tags])
            if self.editor.idea_id == identity:
                self.editor.update_state(self.repo.get_idea(identity))
            self.refresh()
        except Exception as exc:
            self.error("Could not update idea", exc)

    def archive(self, *, identity=None):
        self.change_idea_state(self.editor.idea_id if identity is None else identity, archive=True)

    def pin(self, *, identity=None):
        self.change_idea_state(self.editor.idea_id if identity is None else identity, toggle_pin=True)

    def move_idea(self, identity: int, destination, *, unpin=False):
        if not self.flush(refresh=False):
            return
        try:
            idea = self.repo.get_idea(identity)
            status = "inbox" if type(destination) is int else destination
            self.repo.update_idea(identity, idea.content, idea.project_id, status,
                                  False if unpin else idea.pinned, [tag.id for tag in idea.tags],
                                  group_id=destination if type(destination) is int else None)
            if self.editor.idea_id == identity:
                self.editor.update_state(self.repo.get_idea(identity))
            self.refresh()
        except Exception as exc:
            self.error("Could not move idea", exc)

    def restore_archived(self, identity: int):
        if not self.flush():
            return
        try:
            idea = self.repo.get_idea(identity)
            if idea.status != "archived":
                raise ValueError("Only archived ideas can be restored from Archive.")
            self.repo.update_idea(identity, idea.content, idea.project_id, "inbox",
                                  idea.pinned, [tag.id for tag in idea.tags])
            if self.editor.idea_id == identity:
                self.editor.update_state(self.repo.get_idea(identity))
            self.refresh()
            self.statusBar().showMessage("Idea restored to Inbox", 3000)
        except Exception as exc:
            self.error("Could not restore idea", exc)

    def delete_archived(self, identity: int):
        if not self.flush():
            return
        try:
            idea = self.repo.get_idea(identity)
            if idea.status != "archived":
                raise ValueError("Only archived ideas can be permanently deleted.")
            answer = QMessageBox.question(
                self, "Delete archived idea permanently?",
                "Permanently delete this archived idea? This cannot be undone in Idea.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.repo.delete_idea(identity)
            if self.editor.idea_id == identity:
                self.editor.load(None)
            self.refresh()
            self.statusBar().showMessage("Archived idea deleted", 3000)
        except Exception as exc:
            self.error("Could not delete idea", exc)

    def show_details(self, identity: int):
        if not self.flush():
            return
        try:
            idea = self.repo.get_idea(identity)
            created = readable_time(idea.created_at)
            modified = readable_time(idea.updated_at)
            QMessageBox.information(self, "Idea details",
                                    f"Created: {created}\nLast modified: {modified}")
        except Exception as exc:
            self.error("Could not show idea details", exc)

    def context_menu(self, position):
        index = self.list.indexAt(position)
        if not index.isValid():
            return
        identity = index.data(Qt.ItemDataRole.UserRole).id
        self.list.setCurrentIndex(index)
        # A failed save may have restored the previous selection.
        if self.editor.idea_id != identity:
            return
        try:
            idea = self.repo.get_idea(identity)
        except Exception as exc:
            self.error("Could not load idea actions", exc)
            return
        try:
            groups = self.repo.groups()
        except Exception as exc:
            self.error("Could not load groups", exc)
            return
        menu = QMenu(self)
        menu.addAction("Pin / unpin", lambda: self.pin(identity=identity))
        if idea.status == "archived":
            menu.addAction("Restore to Inbox", lambda: self.restore_archived(identity))
            menu.addAction("Delete permanently…", lambda: self.delete_archived(identity))
        else:
            menu.addAction("Archive", lambda: self.archive(identity=identity))
        destinations = menu.addMenu("Move to group")
        for name, destination in [("Inbox", "inbox"), ("Active", "active"), ("Someday", "someday")] + [(group.name, group.id) for group in groups]:
            destinations.addAction(name, lambda checked=False, target=destination: self.move_idea(identity, target))
        if idea.group_id is not None or idea.status != "inbox" or self.views.currentRow() == 2:
            unpin = self.views.currentRow() == 2
            menu.addAction("Remove from group → Inbox", lambda: self.move_idea(identity, "inbox", unpin=unpin))
        menu.addSeparator()
        menu.addAction("Details…", lambda: self.show_details(identity))
        try:
            menu.exec(self.list.viewport().mapToGlobal(position))
        finally:
            menu.deleteLater()

    def reload_views(self, groups):
        item = self.views.currentItem()
        selected = item.data(Qt.ItemDataRole.UserRole) if item else "inbox"
        with QSignalBlocker(self.views):
            self.views.clear()
            for name, key in (("All ideas", "all"), ("Inbox", "inbox"), ("Pinned", "pinned"), ("Active", "active"), ("Someday", "someday"), ("Archive", "archived")):
                self.views.addItem(name)
                self.views.item(self.views.count() - 1).setData(Qt.ItemDataRole.UserRole, key)
            for group in groups:
                self.views.addItem(group.name)
                self.views.item(self.views.count() - 1).setData(Qt.ItemDataRole.UserRole, group.id)
            row = next((n for n in range(self.views.count()) if self.views.item(n).data(Qt.ItemDataRole.UserRole) == selected), 1)
            self.views.setCurrentRow(row)

    def organization_changed(self):
        try:
            projects, tags, groups = self.repo.projects(), self.repo.tags(), self.repo.groups()
            try:
                project = self.project_filter.value()
            except ValueError:
                project = None
            self.project_filter.reload(project, projects=projects)
            self.project_filter.combo.setItemText(0, "All projects")
            self.tag_filter.reload(self.tag_filter.selected, available=tags)
            self.reload_views(groups)
            self.editor.reload_groups(groups=groups)
            # Refresh choices after capture creates organization, without resetting
            # the editor text/cursor or its pending changes.
            editor_project = self.editor.project.combo.currentData()
            raw_project = self.editor.project.combo.currentText()
            try:
                editor_project = self.editor.project.value()
                unfinished_project = False
            except ValueError:
                unfinished_project = True
            self.editor.project.reload(editor_project, projects=projects)
            if unfinished_project:
                self.editor.project.combo.setEditText(raw_project)
            self.editor.tags.reload(self.editor.tags.selected, available=tags)
            self.refresh()
            self.list.viewport().update()
        except Exception as exc:
            self.error("Could not reload projects and tags", exc)

    def manage(self, kind):
        if not self.flush():
            return
        dialog = OrganizationManager(self.repo, kind, self)
        dialog.changed.connect(self.after_management)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()

    def after_management(self):
        # Management runs after a flush; reload associations changed by deletion.
        try:
            if self.editor.idea_id is not None:
                self.editor.load(self.repo.get_idea(self.editor.idea_id))
            self.organization_changed()
        except Exception as exc:
            self.error("Changes saved, but idea organization could not be reloaded", exc)

    def quick_capture(self):
        if self.capture is not None and self.capture.isVisible():
            self.capture.raise_()
            self.capture.activateWindow()
            return
        if not self.flush():
            return
        self.capture = QuickCapture(self.repo, self)
        self.capture.finished.connect(self.capture_finished)
        self.capture.setWindowModality(Qt.WindowModality.WindowModal)
        self.capture.saved.connect(self.capture_saved)
        # Do not reload the editor while it contains pending edits.
        self.capture.organization_changed.connect(self.organization_changed)
        self.capture.show()

    def capture_finished(self, *_):
        if self.capture is not None:
            self.capture.deleteLater()
            self.capture = None

    def capture_saved(self, identity):
        if self.flush():
            self.clear_filters()
            self.refresh(preferred=identity)

    def set_theme(self, name):
        self.config.theme = name
        self.delegate.dark = name == "dark"
        apply_theme(QApplication.instance(), name)
        self.list.viewport().update()

    def json_export(self):
        if not self.flush():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export JSON (choose a new file)", "ideas.json", "JSON (*.json)")
        if path:
            self.perform("Export failed", lambda: export_json(self.repo, Path(path)))

    def markdown_export(self):
        if not self.flush():
            return
        parent = QFileDialog.getExistingDirectory(self, "Choose parent directory for a new Markdown export folder")
        if parent:
            from datetime import datetime, timezone
            folder = Path(parent) / ("idea-export-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
            self.perform("Export failed", lambda: export_markdown(self.repo, folder))

    def json_import(self):
        if not self.flush():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import Idea JSON", "", "JSON (*.json)")
        if not path:
            return
        if QMessageBox.question(self, "Import ideas?", "Imports create new idea IDs. Reimporting the same file creates duplicates. Existing ideas are never overwritten. Continue?") != QMessageBox.StandardButton.Yes:
            return
        try:
            count = import_json(self.repo, Path(path))
            self.after_management()
            QMessageBox.information(self, "Import complete", f"Imported {count} ideas.")
        except Exception as exc:
            self.error("Import failed; no ideas were imported", exc)

    def backup(self):
        if not self.flush():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Backup (choose a new file)", "ideas-backup.db", "SQLite (*.db)")
        if path:
            self.perform("Backup failed", lambda: self.repo.db.backup(Path(path)))

    def perform(self, message, function):
        try:
            function()
            self.statusBar().showMessage("Completed", 5000)
        except Exception as exc:
            self.error(message, exc)

    def showEvent(self, event):
        self.shown_once = True
        super().showEvent(event)

    def open_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if self.capture is not None and self.capture.isVisible():
            self.capture.raise_()
            self.capture.activateWindow()

    def quit_application(self) -> bool:
        self.quitting = True
        if not self.close():
            self.quitting = False
            self.open_window()
            return False
        if self.tray is not None:
            self.tray.hide()
        QApplication.instance().quit()
        return True

    def closeEvent(self, event):
        if self.capture is not None and self.capture.isVisible():
            if not self.capture.can_discard():
                event.ignore()
                return
            self.capture.done(0)
        if not self.flush():
            event.ignore()
            return
        if self.config_path:
            if self.shown_once:
                self.config.splitter = self.splitter.sizes()
                self.config.width, self.config.height = self.width(), self.height()
            try:
                self.config.save(self.config_path)
            except Exception as exc:
                self.error("Ideas saved, but window preferences could not be saved", exc)
        self.save_timer.stop()
        self.search_timer.stop()
        if not self.quitting and self.tray is not None and self.tray.available():
            # A hidden editor must not cause quick-capture closure to quit Idea.
            QApplication.instance().setQuitOnLastWindowClosed(False)
            self.hide()
            event.ignore()
        else:
            QApplication.instance().setQuitOnLastWindowClosed(True)
            if self.tray is not None:
                self.tray.hide()
            event.accept()
            if not self.quitting and self.tray is not None and not self.isVisible():
                QApplication.instance().quit()
