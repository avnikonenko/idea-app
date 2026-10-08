import sqlite3
from contextlib import closing
from pathlib import Path
from datetime import datetime, timezone
from .models import DEFAULT_TAGS

SCHEMA_VERSION = 2

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")

class Database:
    def __init__(self, path: Path, *, automatic_backup: bool = True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists() and self.path.stat().st_size > 0
        self.connection = sqlite3.connect(self.path, timeout=5)
        self.connection.row_factory = sqlite3.Row
        try:
            self.connection.execute("PRAGMA foreign_keys = ON")
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise ValueError("This database was created by a newer Idea version.")
            if version < 0:
                raise ValueError("Unsupported Idea database schema version.")
            tables = {row[0] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT GLOB 'sqlite_*'"
            )}
            if version == 0 and tables:
                raise ValueError("This is not an empty or versioned Idea database; it was left unchanged.")
            if version in (1, 2):
                expected = {"ideas", "projects", "tags", "idea_tags", "ideas_fts"}
                if not expected <= tables:
                    raise ValueError("This database is missing required Idea tables; it was left unchanged.")
                if version == 2:
                    if "groups" not in tables:
                        raise ValueError("This database is missing Idea groups; it was left unchanged.")
                    self.connection.execute("SELECT id,name,name_key FROM groups LIMIT 0")
                    self.connection.execute("SELECT group_id FROM ideas LIMIT 0")
                # Prepare reads before backup/WAL setup so mismatched schemas fail
                # explicitly without changing an existing file.
                for table, columns in (
                    ("ideas", "id,content,project_id,status,pinned,created_at,updated_at"),
                    ("projects", "id,name,name_key,color,created_at"),
                    ("tags", "id,name,name_key"), ("idea_tags", "idea_id,tag_id"),
                ):
                    self.connection.execute(f"SELECT {columns} FROM {table} LIMIT 0")
                self.connection.execute("SELECT rowid FROM ideas_fts WHERE ideas_fts MATCH ? LIMIT 0", ('"schema check"',))
            if existed and automatic_backup:
                self.daily_backup(force=version < SCHEMA_VERSION)
            if version == 0:
                self._initialize()
                version = 1
            if version == 1:
                self._migrate_groups()
            self.connection.execute("PRAGMA journal_mode = WAL")
            self.connection.execute("PRAGMA synchronous = FULL")
            if automatic_backup:
                self.daily_backup()
        except Exception:
            self.connection.close()
            raise

    def _initialize(self) -> None:
        # One transaction includes schema creation, FTS triggers and default tags.
        self.connection.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                name_key TEXT NOT NULL UNIQUE, color TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                name_key TEXT NOT NULL UNIQUE
            );
            CREATE TABLE ideas (
                id INTEGER PRIMARY KEY, content TEXT NOT NULL,
                project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                status TEXT NOT NULL DEFAULT 'inbox'
                    CHECK(status IN ('inbox','active','someday','archived')),
                pinned INTEGER NOT NULL DEFAULT 0 CHECK(pinned IN (0,1)),
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE idea_tags (
                idea_id INTEGER NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
                tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (idea_id, tag_id)
            );
            CREATE INDEX ideas_project ON ideas(project_id);
            CREATE INDEX ideas_sort ON ideas(pinned DESC, updated_at DESC, id DESC);
            CREATE INDEX ideas_status_sort ON ideas(status, pinned DESC, updated_at DESC, id DESC);
            CREATE INDEX idea_tags_tag ON idea_tags(tag_id, idea_id);
            CREATE VIRTUAL TABLE ideas_fts USING fts5(
                content, content='ideas', content_rowid='id', tokenize='trigram'
            );
            CREATE TRIGGER ideas_ai AFTER INSERT ON ideas BEGIN
                INSERT INTO ideas_fts(rowid, content) VALUES(new.id, new.content);
            END;
            CREATE TRIGGER ideas_ad AFTER DELETE ON ideas BEGIN
                INSERT INTO ideas_fts(ideas_fts,rowid,content) VALUES('delete',old.id,old.content);
            END;
            CREATE TRIGGER ideas_au AFTER UPDATE OF content ON ideas BEGIN
                INSERT INTO ideas_fts(ideas_fts,rowid,content) VALUES('delete',old.id,old.content);
                INSERT INTO ideas_fts(rowid,content) VALUES(new.id,new.content);
            END;
        """)
        try:
            self.connection.executemany("INSERT INTO tags(name,name_key) VALUES(?,?)",
                                        [(name, name.casefold()) for name in DEFAULT_TAGS])
            self.connection.execute("PRAGMA user_version = 1")
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def _migrate_groups(self) -> None:
        self.connection.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE groups (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                name_key TEXT NOT NULL UNIQUE
            );
            ALTER TABLE ideas ADD COLUMN group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL;
            CREATE INDEX ideas_group_sort ON ideas(group_id, pinned DESC, updated_at DESC, id DESC);
            PRAGMA user_version = 2;
            COMMIT;
        """)

    def backup(self, destination: Path) -> Path:
        if self.connection.in_transaction:
            raise ValueError("Finish the current transaction before making a backup.")
        destination = Path(destination)
        if destination.resolve() == self.path.resolve():
            raise ValueError("A backup cannot replace the active database.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Reserve exclusively so an existing backup is never overwritten.
        with destination.open("xb"):
            pass
        try:
            with closing(sqlite3.connect(destination)) as target:
                self.connection.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("Backup integrity check failed")
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return destination

    def daily_backup(self, *, force: bool = False) -> None:
        directory = self.path.parent / "backups"
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        if not force and any(directory.glob(f"ideas-{day}T*.db")):
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.backup(directory / f"ideas-{stamp}.db")
        # Only rotate files created by this application.
        for old in sorted(directory.glob("ideas-????????T????????????Z.db"), reverse=True)[7:]:
            old.unlink()

    def close(self) -> None:
        self.connection.close()
