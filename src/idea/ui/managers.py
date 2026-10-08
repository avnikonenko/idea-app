from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QListWidget, QPushButton, QInputDialog, QMessageBox, QColorDialog, QComboBox)
from ..models import COLORS
from ..repository import valid_color

class OrganizationManager(QDialog):
    changed = Signal()

    def __init__(self, repo, kind: str, parent=None):
        super().__init__(parent)
        self.repo, self.kind = repo, kind
        self.records = []
        self.setWindowTitle(f"Manage {kind}s")
        self.resize(420, 410)
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(f"Search {kind}s…")
        layout.addWidget(self.search)
        self.items = QListWidget()
        layout.addWidget(self.items)
        row = QHBoxLayout()
        for label, function in (("Create", self.create), ("Rename", self.rename), ("Remove" if kind == "group" else "Delete", self.delete)):
            button = QPushButton(label)
            button.clicked.connect(function)
            row.addWidget(button)
        layout.addLayout(row)
        if kind == "project":
            colors = QHBoxLayout()
            self.presets = QComboBox()
            for name, color in COLORS.items():
                self.presets.addItem(name, color)
            colors.addWidget(self.presets)
            preset = QPushButton("Apply color")
            preset.clicked.connect(lambda: self.color(self.presets.currentData()))
            colors.addWidget(preset)
            custom = QPushButton("Custom…")
            custom.clicked.connect(self.custom_color)
            colors.addWidget(custom)
            layout.addLayout(colors)
            hex_button = QPushButton("Enter HEX…")
            hex_button.clicked.connect(self.hex_color)
            layout.addWidget(hex_button)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout.addWidget(close)
        self.search.textChanged.connect(self.reload)
        self.reload()

    def reload(self, *_):
        try:
            records = getattr(self.repo, self.kind + "s")(self.search.text())
        except Exception as exc:
            QMessageBox.warning(self, "Could not load organization", str(exc))
            return
        self.records = records
        self.items.clear()
        for item in self.records:
            self.items.addItem(item.name + (f"   {item.color}" if self.kind == "project" else ""))

    def selected(self):
        index = self.items.currentRow()
        return self.records[index] if 0 <= index < len(self.records) else None

    def run(self, function):
        try:
            function()
            self.reload()
            self.changed.emit()
        except Exception as exc:
            QMessageBox.warning(self, "Could not save change", str(exc))

    def create(self):
        name, ok = QInputDialog.getText(self, f"Create {self.kind}", "Name:")
        if ok:
            self.run(lambda: getattr(self.repo, "create_" + self.kind)(name))

    def rename(self):
        item = self.selected()
        if not item:
            return
        name, ok = QInputDialog.getText(self, f"Rename {self.kind}", "Name:", text=item.name)
        if ok:
            self.run(lambda: self.repo.update_project(item.id, name, item.color) if self.kind == "project" else getattr(self.repo, "update_" + self.kind)(item.id, name))

    def delete(self):
        item = self.selected()
        if not item:
            return
        message = (f"Remove “{item.name}”? All its ideas will return to Inbox. No ideas will be deleted."
                   if self.kind == "group" else f"Delete “{item.name}”? Its ideas will be kept.")
        if QMessageBox.question(self, f"Remove {self.kind}?", message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.run(lambda: getattr(self.repo, "delete_" + self.kind)(item.id))

    def color(self, color):
        item = self.selected()
        if item:
            self.run(lambda: self.repo.update_project(item.id, item.name, valid_color(color)))

    def custom_color(self):
        item = self.selected()
        if item:
            chosen = QColorDialog.getColor(QColor(item.color), self, "Project background")
            if chosen.isValid():
                self.color(chosen.name())

    def hex_color(self):
        item = self.selected()
        if item:
            color, ok = QInputDialog.getText(self, "Project background", "HEX (#RRGGBB):", text=item.color)
            if ok:
                self.color(color)
