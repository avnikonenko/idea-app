import sqlite3
import pytest
from idea.database import Database
from idea.models import DEFAULT_TAGS


def test_initialization_reopen_and_newer_schema(tmp_path):
    path = tmp_path / "db"
    db = Database(path)
    assert db.connection.execute("PRAGMA user_version").fetchone()[0] == 2
    assert db.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert db.connection.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == len(DEFAULT_TAGS)
    db.close()
    db = Database(path)
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1
    db.connection.execute("PRAGMA user_version=99")
    db.close()
    with pytest.raises(ValueError, match="newer"):
        Database(path)


def test_idea_defaults_unicode_title_and_update(repo):
    identity = repo.create_idea("\n\n  Žluťoučký 🧠\n代码\nhttps://example.org\nprint('hi')")
    idea = repo.get_idea(identity)
    assert idea.title == "Žluťoučký 🧠"
    assert (idea.status, idea.pinned, idea.project_id, idea.tags) == ("inbox", False, None, ())
    repo.update_idea(identity, "Updated", None, "active", True, [])
    updated = repo.get_idea(identity)
    assert updated.content == "Updated" and updated.created_at == idea.created_at
    assert updated.updated_at > idea.updated_at
    assert repo.search(status="active", pinned=True)[0].id == identity


def test_project_lifecycle_and_uniqueness(repo):
    project = repo.create_project("Straße", "#e2f3e8")
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_project("STRASSE")
    identity = repo.create_idea("note", project)
    assert repo.projects("STRAS")[0].id == project
    repo.update_project(project, "Renamed", "#E3F0FA")
    assert repo.get_idea(identity).project_color == "#E3F0FA"
    repo.delete_project(project)
    assert repo.get_idea(identity).project_id is None
    assert len(repo.search()) == 1
    with pytest.raises(ValueError):
        repo.create_project("bad", "red")


def test_tag_lifecycle_associations(repo):
    a, b = repo.create_tag("研究"), repo.create_tag("Code")
    identity = repo.create_idea("note", tags=[a, b, a])
    assert len(repo.get_idea(identity).tags) == 2
    repo.update_tag(b, "Coding")
    assert repo.tags("cod")[0].name == "Coding"
    repo.delete_tag(a)
    assert [t.id for t in repo.get_idea(identity).tags] == [b]
    repo.delete_tag(b)
    assert repo.get_idea(identity).tags == ()


def test_search_all_fields_partial_filters_and_fts_sync(repo):
    project = repo.create_project("CReM-agent")
    a, b = repo.create_tag("Experimentation"), repo.create_tag("ML")
    one = repo.create_idea("Docking molecules café", project, "active", True, [a, b])
    two = repo.create_idea("Other experiment", project, tags=[a])
    for term in ("dock", "ocking", "CREM", "Experim", "ML", "café", "CReM mole"):
        assert one in [i.id for i in repo.search(term)]
    assert [i.id for i in repo.search("mole", project_id=project, tag_ids=[a,b], status="active", pinned=True)] == [one]
    assert len(repo.search("exper", tag_ids=[a])) == 2
    repo.update_idea(one, "Replacement", project, "active", True, [a, b])
    assert repo.search("docking") == []
    assert repo.search("replac")[0].id == one
    repo.delete_idea(one)
    assert repo.search("replacement") == []
    assert repo.get_idea(two)

@pytest.mark.parametrize("query", ['"', '"""', '%', '_', "OR", "NEAR(", "x' OR 1=1 --", "😀", "a-b"])
def test_search_metacharacters_are_literal(repo, query):
    identity = repo.create_idea("Literal " + query)
    assert identity in [i.id for i in repo.search(query)]


def test_transaction_rollback_invalid_tag(repo):
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_idea("must rollback", tags=[9999])
    assert repo.search() == []
    identity = repo.create_idea("Original")
    with pytest.raises(sqlite3.IntegrityError):
        repo.update_idea(identity, "Broken", None, "inbox", False, [9999])
    assert repo.get_idea(identity).content == "Original"


def test_backup_integrity_and_no_overwrite(repo, tmp_path):
    repo.create_idea("backup Unicode 🧠")
    path = repo.db.backup(tmp_path / "backup.db")
    with sqlite3.connect(path) as check:
        assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert check.execute("SELECT content FROM ideas").fetchone()[0] == "backup Unicode 🧠"
        assert check.execute("SELECT COUNT(*) FROM ideas_fts WHERE ideas_fts MATCH 'Unicode'").fetchone()[0] == 1
    with pytest.raises(FileExistsError):
        repo.db.backup(path)
    with pytest.raises(ValueError):
        repo.db.backup(repo.db.path)


@pytest.mark.parametrize("version", [0, 1, -1])
def test_unrelated_database_is_rejected_without_mutation(tmp_path, version):
    path = tmp_path / "other.db"
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE important(value TEXT)")
        conn.execute("INSERT INTO important VALUES('preserve me')")
        conn.execute(f"PRAGMA user_version={version}")
        conn.commit()
    finally:
        conn.close()
    before = path.read_bytes()
    with pytest.raises(ValueError):
        Database(path)
    assert path.read_bytes() == before
    assert not (tmp_path / "backups").exists()


@pytest.mark.parametrize("fail_integrity", [False, True])
def test_backup_connections_close_on_success_and_failure(repo, tmp_path, monkeypatch, fail_integrity):
    targets = []
    class Tracked(sqlite3.Connection):
        closed = False
        def execute(self, sql, *args):
            if fail_integrity and sql == "PRAGMA integrity_check":
                raise sqlite3.DatabaseError("simulated integrity failure")
            return super().execute(sql, *args)
        def close(self):
            self.closed = True
            super().close()
    original = sqlite3.connect
    def connect(*args, **kwargs):
        target = original(*args, **kwargs, factory=Tracked)
        targets.append(target)
        return target
    monkeypatch.setattr(sqlite3, "connect", connect)
    path = tmp_path / "backup.db"
    if fail_integrity:
        with pytest.raises(sqlite3.DatabaseError):
            repo.db.backup(path)
        assert not path.exists()
    else:
        repo.db.backup(path)
        assert path.exists()
    assert targets and all(target.closed for target in targets)


def test_incompatible_versioned_schema_is_rejected_before_backup(tmp_path):
    path = tmp_path / "schema.db"
    database = Database(path, automatic_backup=False)
    database.connection.execute("ALTER TABLE projects RENAME COLUMN color TO old_color")
    database.connection.commit()
    database.close()
    before = path.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):
        Database(path)
    assert path.read_bytes() == before
    assert not (tmp_path / "backups").exists()


@pytest.mark.parametrize("schema", ["CREATE TABLE sqliteXimportant(value TEXT)", "CREATE VIEW important AS SELECT 42 AS value"])
def test_unversioned_custom_schema_is_never_initialized(tmp_path, schema):
    path = tmp_path / "other.db"
    conn = sqlite3.connect(path)
    try:
        conn.execute(schema)
        conn.commit()
    finally:
        conn.close()
    before = path.read_bytes()
    with pytest.raises(ValueError):
        Database(path)
    assert path.read_bytes() == before
