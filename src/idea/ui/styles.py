from PySide6.QtGui import QColor, QPalette


def apply_theme(app, theme: str) -> None:
    dark = theme == "dark"
    palette = QPalette()
    values = {
        QPalette.ColorRole.Window: "#202226" if dark else "#FAFAFC",
        QPalette.ColorRole.WindowText: "#E9EAEE" if dark else "#252830",
        QPalette.ColorRole.Base: "#272A30" if dark else "#FFFFFF",
        QPalette.ColorRole.AlternateBase: "#30343A" if dark else "#F3F4F6",
        QPalette.ColorRole.Text: "#E9EAEE" if dark else "#252830",
        QPalette.ColorRole.Button: "#30343A" if dark else "#F0F1F4",
        QPalette.ColorRole.ButtonText: "#E9EAEE" if dark else "#252830",
        QPalette.ColorRole.Highlight: "#90B7EF" if dark else "#386BB5",
        QPalette.ColorRole.HighlightedText: "#172337" if dark else "#FFFFFF",
        QPalette.ColorRole.PlaceholderText: "#949BA8" if dark else "#707780",
    }
    for role, value in values.items():
        palette.setColor(role, QColor(value))
    app.setPalette(palette)
    app.setStyleSheet("""
        QLineEdit, QPlainTextEdit, QComboBox { padding: 5px; border: 1px solid palette(mid); border-radius: 4px; }
        QPushButton { padding: 5px 9px; }
        QSplitter::handle { background: palette(mid); width: 1px; }
        QListView { border: 0; }
        QToolButton { padding: 3px 6px; }
    """)
