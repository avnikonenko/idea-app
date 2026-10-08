import argparse
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtGui import QIcon
from .config import Config, config_path, data_path
from .database import Database
from .repository import Repository
from .ui.main_window import MainWindow
from .ui.tray import IdeaTray
from .capture_request import CaptureServer, request_capture


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Idea — local-first idea inbox")
    parser.add_argument("--database", type=Path, help="Use a separate database (for testing or portable storage)")
    parser.add_argument("--config", type=Path, help="Use a separate TOML configuration")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--tray", action="store_true", help="Start in the panel; show the window if no tray is available")
    modes.add_argument("--no-tray", action="store_true", help="Run without a panel icon; closing the window exits")
    parser.add_argument("--capture", action="store_true", help="Open quick capture, reusing a running instance")
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Idea")
    app.setOrganizationName("Idea")
    app.setDesktopFileName("idea-inbox")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets/idea-inbox.svg")))
    app.setStyle("Fusion")
    db_path = (args.database or data_path()).resolve()
    lock = None
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(db_path) + ".lock")
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            if args.capture:
                if request_capture(db_path):
                    return 0
                QMessageBox.warning(None, "Quick capture unavailable", "The running Idea instance cannot receive this request. Quit Idea through its tray menu and reopen it once to enable the shortcut. Your notes have not been changed.")
                return 1
            QMessageBox.warning(None, "Idea is already running", "Another Idea instance is using this database, or its lock could not be created.")
            return 1
        database = Database(db_path)
    except Exception as exc:
        if lock is not None:
            lock.unlock()
        QMessageBox.critical(None, "Idea could not open its database", str(exc))
        return 1
    capture_server = None
    try:
        cfg_path = args.config or config_path()
        try:
            config = Config.load(cfg_path)
        except Exception as exc:
            QMessageBox.warning(None, "Could not read preferences", f"Default settings will be used. {exc}")
            config = Config()
            cfg_path = None  # Preserve the unreadable original preferences.
        window = MainWindow(Repository(database), config, cfg_path)
        try:
            capture_server = CaptureServer(db_path, window.quick_capture, window)
        except Exception as exc:
            QMessageBox.warning(window, "Desktop quick capture unavailable", str(exc))
        if not args.no_tray:
            window.tray = IdeaTray(window)
        tray_available = window.tray is not None and window.tray.available()
        app.setQuitOnLastWindowClosed(not tray_available)
        if (not args.tray and not args.capture) or not tray_available:
            window.show()
            if args.tray and not tray_available:
                window.statusBar().showMessage("Panel tray unavailable — use this window to capture ideas.")
        if args.capture:
            QTimer.singleShot(0, window.quick_capture)
        try:
            return app.exec()
        finally:
            if window.tray is not None:
                window.tray.hide()
    finally:
        if capture_server is not None:
            capture_server.close()
        database.close()
        lock.unlock()
