"""Render README screenshots using only fictional notes in a temporary database."""
import os
from pathlib import Path
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["TZ"] = "UTC"
time.tzset()

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QDialog
from idea.config import Config
from idea.database import Database
from idea.repository import Repository
from idea.ui.main_window import MainWindow

EXAMPLE = "Try a 15-minute idea review\nEach Friday, revisit the inbox and choose one idea to explore."


def main():
    output = Path(__file__).resolve().parents[1] / "docs/images"
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyle("Fusion")
    app.setFont(QFont("DejaVu Sans", 10))
    with tempfile.TemporaryDirectory(prefix="idea-screenshots-") as temporary:
        database = Database(Path(temporary) / "ideas.db", automatic_backup=False)
        try:
            repo = Repository(database)
            personal = repo.create_project("Personal", "#E2F3E8")
            learning = repo.create_project("Learning", "#E3F0FA")
            home = repo.create_project("Home", "#FCE8DC")
            tags = {tag.name: tag.id for tag in repo.tags()}
            samples = (
                ("Build a tiny reading tracker\nKeep a short list of books and one sentence about each.", learning, True, [tags["Idea"]]),
                (EXAMPLE, personal, False, [tags["Improvement"]]),
                ("Learn one new keyboard shortcut\nPractice it until it feels natural.", learning, False, [tags["Learning"]]),
                ("Weekend project: desk organizer\nSketch a simple design before buying materials.", home, False, [tags["Personal"]]),
                ("Question: what makes an idea worth revisiting?\nWrite down a few criteria.", None, False, [tags["Question"]]),
            )
            identities = [repo.create_idea(content, project, pinned=pinned, tags=tag_ids) for content, project, pinned, tag_ids in samples]
            repo.create_group("Weekend")
            with repo.conn:
                for index, identity in enumerate(identities):
                    stamp = f"2026-10-09T10:{30-index:02d}:00+00:00"
                    repo.conn.execute("UPDATE ideas SET created_at=?,updated_at=? WHERE id=?", (stamp, stamp, identity))
            window = MainWindow(repo, Config(width=1120, height=760, splitter=[185, 350, 585]))
            try:
                window.show()
                window.refresh(preferred=identities[1])
                app.processEvents()
                save(window, output / "main-window.png")
                window.quick_capture()
                capture = window.capture
                capture.resize(520, 390)
                capture.content.setPlainText(EXAMPLE)
                capture.project.reload(personal)
                capture.tags.reload([tags["Improvement"]])
                app.processEvents()
                save(capture, output / "quick-capture.png")
                capture.done(QDialog.DialogCode.Rejected)
            finally:
                # Fake capture text can be discarded even if image writing fails.
                if window.capture is not None:
                    window.capture.done(QDialog.DialogCode.Rejected)
                window.close()
                window.deleteLater()
                app.processEvents()
        finally:
            database.close()


def save(widget, path):
    if not widget.grab().save(str(path)):
        raise OSError(f"Could not save screenshot: {path}")
    print(f"Rendered: {path.relative_to(Path(__file__).resolve().parents[1])}")


if __name__ == "__main__":
    main()
