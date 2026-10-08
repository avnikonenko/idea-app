from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QItemSelectionModel
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

class MainWindow(QMainWindow):
    SAVE_DELAY_MS = 350

    def __init__(self, repo, config: Config, config_path: Path | None = None):
        super().__init__()
        self.repo, self.config, self.config_path = repo, config, config_path
        self.dirty = False
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
        self.views.setCurrentRow(1)
        self.views.setMaximumHeight(190)
        self.views.currentRowChanged.connect(self.filter_changed)
        side.addWidget(self.views)
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
        self.editor = IdeaEditor(repo, before_change=self.flush)
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

    def error(self, message, exc):
        QMessageBox.warning(self, message, str(exc))

    def mark_dirty(self):
        self.dirty = True
        self.statusBar().showMessage("Unsaved changes")
        self.save_timer.start(self.SAVE_DELAY_MS)

    def save_metadata(self):
        self.mark_dirty()
        self.flush()

    def flush(self) -> bool:
        self.save_timer.stop()
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
            self.error("Changes could not be saved; your edits remain in the editor", exc)
            return False
        self.dirty = False
        self.editor.saved_values = values
        self.editor.set_timestamps(saved)
        self.statusBar().showMessage("Saved", 2000)
        self.refresh(flush=False)
        return True

    def filter_changed(self, *_):
        self.refresh()

    def filter_values(self):
        index = self.views.currentRow()
        status = {1: "inbox", 3: "active", 4: "someday", 5: "archived"}.get(index)
        return dict(query=self.search.text(), project_id=self.project_filter.value(),
                    tag_ids=self.tag_filter.selected, status=status, pinned=True if index == 2 or self.pinned_filter.isChecked() else None)

    def refresh(self, *, flush=True, preferred=None):
        if self.refreshing:
            return
        if flush and not self.flush():
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
            self.model.replace(ideas)
            if target is not None:
                self.list.setCurrentIndex(self.model.index(identities.index(target)))
            if target != self.editor.idea_id:
                self.editor.load(loaded)
                self.dirty = False
            self.list.verticalScrollBar().setValue(scroll)
            self.statusBar().showMessage(f"{len(ideas)} ideas" + (" · unsaved edits" if self.dirty else ""))
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
        except Exception as exc:
            self.error("Could not open idea", exc)
            self.select_id(self.editor.idea_id)
            return
        self.editor.load(loaded)
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

    def archive(self):
        if self.editor.idea_id is not None and self.flush():
            self.editor.status.setCurrentIndex(self.editor.status.findData("archived"))
            self.flush()

    def pin(self):
        if self.editor.idea_id is not None and self.flush():
            self.editor.pinned.setChecked(not self.editor.pinned.isChecked())
            self.flush()

    def context_menu(self, position):
        index = self.list.indexAt(position)
        if not index.isValid():
            return
        identity = index.data(Qt.ItemDataRole.UserRole).id
        self.list.setCurrentIndex(index)
        # A failed save may have restored the previous selection.
        if self.editor.idea_id != identity:
            return
        menu = QMenu(self)
        menu.addAction("Pin / unpin", self.pin)
        menu.addAction("Archive", self.archive)
        menu.exec(self.list.viewport().mapToGlobal(position))

    def organization_changed(self):
        try:
            project = self.project_filter.value()
        except ValueError:
            project = None
        self.project_filter.reload(project)
        self.project_filter.combo.setItemText(0, "All projects")
        self.tag_filter.reload(self.tag_filter.selected)
        self.refresh()
        self.list.viewport().update()

    def manage(self, kind):
        if not self.flush():
            return
        dialog = OrganizationManager(self.repo, kind, self)
        dialog.changed.connect(self.after_management)
        dialog.exec()

    def after_management(self):
        # Management runs after a flush; reload associations changed by deletion.
        if self.editor.idea_id is not None:
            self.editor.load(self.repo.get_idea(self.editor.idea_id))
        self.organization_changed()

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
            event.accept()
