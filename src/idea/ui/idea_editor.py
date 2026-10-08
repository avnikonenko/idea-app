from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QPlainTextEdit, QComboBox, QCheckBox, QLabel
from .selectors import ProjectSelector, TagSelector
from ..models import STATUSES
from .dates import readable_time

class IdeaEditor(QWidget):
    edited = Signal()
    metadata_edited = Signal()
    organization_changed = Signal()

    def __init__(self, repo, parent=None, before_change=None):
        super().__init__(parent)
        self.loading = False
        self.idea_id = None
        self.saved_values = None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.project = ProjectSelector(repo, before_change=before_change)
        self.tags = TagSelector(repo, before_change=before_change)
        self.status = QComboBox()
        for status in STATUSES:
            self.status.addItem(status.title(), status)
        self.pinned = QCheckBox("Pinned")
        form.addRow("Project", self.project)
        form.addRow("Tags", self.tags)
        form.addRow("Status", self.status)
        form.addRow("", self.pinned)
        layout.addLayout(form)
        self.content = QPlainTextEdit()
        self.content.setPlaceholderText("Write your idea…")
        layout.addWidget(self.content, 1)
        self.timestamps = QLabel()
        self.timestamps.setWordWrap(True)
        layout.addWidget(self.timestamps)
        self.content.textChanged.connect(self.notify)
        self.project.changed.connect(self.notify_metadata)
        self.tags.changed.connect(self.notify_metadata)
        self.status.currentIndexChanged.connect(self.notify_metadata)
        self.pinned.toggled.connect(self.notify_metadata)
        self.project.organization_changed.connect(self.organization_changed)
        self.tags.organization_changed.connect(self.organization_changed)
        self.setEnabled(False)

    def notify(self, *_):
        if not self.loading and self.idea_id is not None:
            self.edited.emit()

    def notify_metadata(self, *_):
        if not self.loading and self.idea_id is not None:
            self.metadata_edited.emit()

    def load(self, idea):
        projects = self.project.repo.projects() if idea else []
        tags = self.tags.repo.tags() if idea else []
        self.loading = True
        try:
            self.idea_id = idea.id if idea else None
            self.setEnabled(idea is not None)
            self.content.setPlainText(idea.content if idea else "")
            self.project.reload(idea.project_id if idea else None, projects=projects)
            self.tags.reload([t.id for t in idea.tags] if idea else [], available=tags)
            self.status.setCurrentIndex(self.status.findData(idea.status) if idea else 0)
            self.pinned.setChecked(idea.pinned if idea else False)
            self.set_timestamps(idea)
            self.saved_values = self.values() if idea else None
        finally:
            self.loading = False

    def update_state(self, idea):
        # State-only actions must preserve the plain-text cursor and undo stack.
        self.loading = True
        try:
            self.status.setCurrentIndex(self.status.findData(idea.status))
            self.pinned.setChecked(idea.pinned)
            self.set_timestamps(idea)
            self.saved_values = self.values()
        finally:
            self.loading = False

    def set_timestamps(self, idea):
        self.timestamps.setText(f"Created: {readable_time(idea.created_at)}\nModified: {readable_time(idea.updated_at)}" if idea else "")

    def values(self):
        return dict(content=self.content.toPlainText(), project_id=self.project.value(),
                    tags=list(self.tags.selected), status=self.status.currentData(), pinned=self.pinned.isChecked())
