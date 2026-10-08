"""Deterministic Linux benchmark; only temporary databases are used."""
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import qVersion
from PySide6.QtWidgets import QApplication
from idea.database import Database, now
from idea.repository import Repository
from idea.config import Config
from idea.ui.main_window import MainWindow


def main():
    with tempfile.TemporaryDirectory(prefix="idea-benchmark-") as temporary:
        db = Database(Path(temporary) / "ideas.db", automatic_backup=False)
        repo = Repository(db)
        project = repo.create_project("Docking research")
        tag = repo.create_tag("Experimentation")
        timestamp = now()
        start = time.perf_counter()
        with repo.conn:
            repo.conn.executemany("INSERT INTO ideas(content,project_id,status,pinned,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                [(f"Idea {n}: molecular docking\nUnicode 🧠 café. Compound {n % 100}. " + "some details " * 20,
                  project if n % 2 else None, "active" if n % 3 else "inbox", n % 17 == 0, timestamp, timestamp) for n in range(10000)])
            repo.conn.executemany("INSERT INTO idea_tags(idea_id,tag_id) VALUES(?,?)", [(n, tag) for n in range(1,10001,5)])
        seed_seconds = time.perf_counter() - start
        results = {}
        for name, kwargs in {"all": {}, "content": {"query": "mole dock"}, "project": {"query": "research"},
                             "tag": {"query": "experim"}, "combined": {"query": "dock", "project_id": project, "tag_ids": [tag], "status": "active", "pinned": True}}.items():
            samples = []
            for _ in range(10):
                start = time.perf_counter()
                rows = repo.search(**kwargs)
                samples.append((time.perf_counter() - start) * 1000)
            results[name] = {"median_ms": round(statistics.median(samples), 2), "max_ms": round(max(samples), 2), "matches": len(rows)}
        start = time.perf_counter()
        app = QApplication([])
        app.setStyle("Fusion")
        window = MainWindow(repo, Config())
        window.show()
        app.processEvents()
        startup_ms = (time.perf_counter() - start) * 1000
        wall, cpu = time.perf_counter(), time.process_time()
        # Observe idle event loop CPU, without a timer doing application work.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, app.quit)
        app.exec()
        idle_cpu = (time.process_time() - cpu) / (time.perf_counter() - wall) * 100
        screenshot = Path(__file__).resolve().parents[1] / "benchmark-preview.png"
        window.grab().save(str(screenshot))
        cold_start = time.perf_counter()
        child = subprocess.run([sys.executable, "-c", """
import sys, time, resource
from pathlib import Path
from PySide6.QtWidgets import QApplication
from idea.database import Database
from idea.repository import Repository
from idea.config import Config
from idea.ui.main_window import MainWindow
app = QApplication([])
app.setStyle("Fusion")
db = Database(Path(sys.argv[2]))
window = MainWindow(Repository(db), Config())
window.show()
app.processEvents()
print((time.perf_counter() - float(sys.argv[1])) * 1000)
window.close()
db.close()
""", str(cold_start), str(db.path)], capture_output=True, text=True, check=True)
        process_startup_ms = float(child.stdout.strip())
        output = {"python": platform.python_version(), "qt": qVersion(), "platform": platform.platform(),
                  "ideas": 10000, "seed_seconds": round(seed_seconds, 3), "search": results,
                  "gui_construct_show_ms": round(startup_ms, 2),
                  "fresh_process_first_show_ms_with_backup": round(process_startup_ms, 2),
                  "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2),
                  "idle_cpu_percent_2s": round(idle_cpu, 2), "display": "Qt offscreen (not a compositor)"}
        print(json.dumps(output, indent=2))
        window.close()
        db.close()

if __name__ == "__main__":
    main()
