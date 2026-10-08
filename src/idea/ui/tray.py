"""Panel quick capture, using the application's existing database and save path."""
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


class IdeaTray:
    def __init__(self, window):
        self.window = window
        self.menu = QMenu(window)
        self.add_action = self.menu.addAction("+ Add note", window.quick_capture)
        self.menu.setDefaultAction(self.add_action)
        self.open_action = self.menu.addAction("Open Idea", window.open_window)
        self.menu.addSeparator()
        self.quit_action = self.menu.addAction("Quit Idea", window.quit_application)
        self.icon = QSystemTrayIcon(QApplication.windowIcon(), window)
        self.icon.setToolTip("Idea — Add note")
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self.activated)
        # Qt registers this later if the panel is still starting at login.
        self.icon.show()

    def available(self) -> bool:
        return self.icon.isVisible() and QSystemTrayIcon.isSystemTrayAvailable()

    def activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.MiddleClick):
            self.window.quick_capture()

    def hide(self):
        self.icon.hide()
