"""Read-only shortcut reference, available from Idea's Settings menu."""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QDialogButtonBox)

SHORTCUTS = (
    ("New idea", "Ctrl+N", "Main window"),
    ("Search", "Ctrl+F", "Main window"),
    ("Save pending changes", "Ctrl+S", "Main window"),
    ("Archive selected idea", "Ctrl+E", "Main window"),
    ("Pin / unpin selected idea", "Ctrl+P", "Main window"),
    ("Quick capture", "Ctrl+Shift+N", "Main window"),
    ("Quick capture from any app", "Ctrl+Alt+N", "Desktop, when installed"),
    ("Save quick capture", "Ctrl+Enter", "Quick capture"),
    ("Close capture; confirm unsaved content", "Esc", "Quick capture"),
    ("Navigate ideas", "Up / Down", "Idea list focused"),
)


class ShortcutSettings(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        self.resize(720, 480)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(len(SHORTCUTS), 3)
        self.table.setHorizontalHeaderLabels(["Action", "Shortcut", "Where"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        for row, values in enumerate(SHORTCUTS):
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.resizeRowsToContents()
        layout.addWidget(self.table, 1)
        note = QLabel(
            "Ctrl+Alt+N is the default desktop shortcut installed for GNOME. "
            "Change or remove it in GNOME Settings → Keyboard → Custom Shortcuts. "
            "If you change it there, use your chosen key combination. "
            "Other desktops require their own shortcut setup."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
