import argparse
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QLockFile
from .config import Config, config_path, data_path
from .database import Database
from .repository import Repository
from .ui.main_window import MainWindow


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Idea — local-first idea inbox")
    parser.add_argument("--database", type=Path, help="Use a separate database (for testing or portable storage)")
    parser.add_argument("--config", type=Path, help="Use a separate TOML configuration")
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Idea")
    app.setOrganizationName("Idea")
    app.setStyle("Fusion")
    cfg_path = args.config or config_path()
    try:
        config = Config.load(cfg_path)
    except Exception as exc:
        QMessageBox.warning(None, "Could not read preferences", f"Default settings will be used. {exc}")
        config = Config()
        cfg_path = None  # Preserve the unreadable original preferences.
    db_path = (args.database or data_path()).resolve()
    lock = None
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(db_path) + ".lock")
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            QMessageBox.warning(None, "Idea is already running", "Another Idea instance is using this database, or its lock could not be created.")
            return 1
        database = Database(db_path)
    except Exception as exc:
        if lock is not None:
            lock.unlock()
        QMessageBox.critical(None, "Idea could not open its database", str(exc))
        return 1
    try:
        window = MainWindow(Repository(database), config, cfg_path)
        window.show()
        return app.exec()
    finally:
        database.close()
        lock.unlock()
