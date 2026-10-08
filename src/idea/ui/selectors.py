from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QComboBox, QPushButton,
    QLineEdit, QCompleter, QToolButton, QInputDialog, QMessageBox, QScrollArea)

class ProjectSelector(QWidget):
    changed = Signal()
    organization_changed = Signal()

    def __init__(self, repo, parent=None, before_change=None, *, allow_create=True):
        super().__init__(parent)
        self.repo, self.before_change = repo, before_change
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo.setMinimumWidth(100)
        layout.addWidget(self.combo, 1)
        if allow_create:
            button = QPushButton("+")
            button.setToolTip("Create project")
            button.clicked.connect(self.create)
            layout.addWidget(button)
        self.combo.activated.connect(lambda *_: self.changed.emit())
        self.combo.lineEdit().editingFinished.connect(self.changed.emit)
        self.reload(None)

    def reload(self, project_id):
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem("Unassigned", None)
        for project in self.repo.projects():
            self.combo.addItem(project.name, project.id)
        self.combo.setCurrentIndex(max(0, self.combo.findData(project_id)))
        self.combo.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.combo.blockSignals(False)

    def value(self):
        current = self.combo.currentIndex()
        if current >= 0 and self.combo.currentText() == self.combo.itemText(current):
            return self.combo.itemData(current)
        index = self.combo.findText(self.combo.currentText(), Qt.MatchFlag.MatchFixedString)
        if index < 0:
            raise ValueError("Select an existing project, or use + to create it.")
        return self.combo.itemData(index)

    def create(self):
        typed = self.combo.currentText()
        known = self.combo.findText(typed, Qt.MatchFlag.MatchFixedString) >= 0
        name, ok = QInputDialog.getText(self, "New project", "Project name:", text="" if known else typed)
        if not ok:
            return
        # Autocomplete text is a search, not an assignment. Flush the actual
        # selected project before creating the requested new one.
        if not known:
            self.combo.setEditText(self.combo.itemText(self.combo.currentIndex()))
        if self.before_change and not self.before_change():
            self.combo.setEditText(typed)
            return
        try:
            identity = self.repo.create_project(name)
            self.reload(identity)
            self.changed.emit()
            self.organization_changed.emit()
        except Exception as exc:
            QMessageBox.warning(self, "Could not create project", str(exc))

class TagSelector(QWidget):
    changed = Signal()
    organization_changed = Signal()

    def __init__(self, repo, parent=None, before_change=None, *, allow_create=True):
        super().__init__(parent)
        self.repo, self.before_change, self.allow_create = repo, before_change, allow_create
        self.selected: list[int] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Find or add a tag…" if allow_create else "Find tag…")
        row.addWidget(self.input)
        add = QPushButton("Add")
        add.clicked.connect(self.add)
        self.input.returnPressed.connect(self.add)
        row.addWidget(add)
        layout.addLayout(row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(44)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.chips = QWidget()
        self.chip_layout = QHBoxLayout(self.chips)
        self.chip_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self.chips)
        layout.addWidget(scroll)
        self.reload([])

    def reload(self, tag_ids):
        self.available = self.repo.tags()
        identities = {t.id for t in self.available}
        self.selected = [t for t in tag_ids if t in identities]
        completer = QCompleter([t.name for t in self.available], self.input)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.input.setCompleter(completer)
        self.render()

    def render(self):
        while self.chip_layout.count():
            item = self.chip_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for tag in self.available:
            if tag.id in self.selected:
                chip = QToolButton()
                chip.setText(tag.name + " ×")
                chip.setToolTip("Remove tag " + tag.name)
                chip.clicked.connect(lambda checked=False, identity=tag.id: self.remove(identity))
                self.chip_layout.addWidget(chip)
        self.chip_layout.addStretch()

    def add(self):
        name = self.input.text().strip()
        if not name:
            return
        if self.before_change and not self.before_change():
            return
        try:
            tag = next((t for t in self.available if t.name.casefold() == name.casefold()), None)
            created = tag is None
            if tag is None:
                if not self.allow_create:
                    raise ValueError("Choose an existing tag.")
                identity = self.repo.create_tag(name)
                self.reload(self.selected)
            else:
                identity = tag.id
            if identity not in self.selected:
                self.selected.append(identity)
                self.render()
                self.changed.emit()
            self.input.clear()
            if created:
                self.organization_changed.emit()
        except Exception as exc:
            QMessageBox.warning(self, "Could not add tag", str(exc))

    def remove(self, identity):
        if self.before_change and not self.before_change():
            return
        self.selected.remove(identity)
        self.render()
        self.changed.emit()
