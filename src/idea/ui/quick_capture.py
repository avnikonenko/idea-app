from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QPlainTextEdit,
    QDialogButtonBox, QMessageBox)
from .selectors import ProjectSelector, TagSelector

class QuickCapture(QDialog):
    saved = Signal(int)
    organization_changed = Signal()

    def __init__(self, repo, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("New idea")
        self.resize(460, 350)
        layout = QVBoxLayout(self)
        self.content = QPlainTextEdit()
        self.content.setPlaceholderText("Write your idea…")
        layout.addWidget(self.content, 1)
        form = QFormLayout()
        self.project = ProjectSelector(repo)
        self.tags = TagSelector(repo)
        self.project.organization_changed.connect(self.organization_changed)
        self.tags.organization_changed.connect(self.organization_changed)
        form.addRow("Project", self.project)
        form.addRow("Tags", self.tags)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        # Return is for multiline editing; only explicit Ctrl+Enter saves.
        for button in buttons.buttons():
            button.setAutoDefault(False)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self.save)
        keypad = QShortcut(QKeySequence("Ctrl+Enter"), self)
        keypad.activated.connect(self.save)

    def showEvent(self, event):
        super().showEvent(event)
        self.content.setFocus(Qt.FocusReason.OtherFocusReason)

    def save(self):
        if not self.content.toPlainText().strip():
            QMessageBox.warning(self, "Empty idea", "Write some content before saving.")
            return
        try:
            identity = self.repo.create_idea(self.content.toPlainText(), self.project.value(), tags=self.tags.selected)
        except Exception as exc:
            QMessageBox.warning(self, "Idea was not saved", str(exc))
            return
        self.saved.emit(identity)
        self.accept()

    def can_discard(self):
        if self.content.toPlainText() or self.tags.selected or self.project.combo.currentIndex() != 0:
            return QMessageBox.question(self, "Discard capture?", "This capture has not been saved. Discard it?", QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Discard
        return True

    def reject(self):
        if self.can_discard():
            super().reject()

    def closeEvent(self, event):
        if self.can_discard():
            QDialog.reject(self)
            event.accept()
        else:
            event.ignore()
