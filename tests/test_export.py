import json
import pytest
from idea.database import Database
from idea.repository import Repository
from idea.export import export_json, import_json, export_markdown


def test_round_trip_and_additive_import(repo, tmp_path):
    project = repo.create_project("研究", "#F9E3EB")
    tags = [repo.create_tag("☕"), repo.tags()[0].id]
    identity = repo.create_idea("\n../Unsafe / title 🧠\nText", project, "someday", True, tags)
    source = repo.get_idea(identity)
    path = tmp_path / "export.json"
    export_json(repo, path)
    db = Database(tmp_path / "restored.db", automatic_backup=False)
    target = Repository(db)
    assert import_json(target, path) == 1
    restored = target.get_idea(target.search()[0].id)
    assert (restored.content, restored.project_name, restored.project_color, restored.status, restored.pinned, restored.created_at, restored.updated_at) == (source.content, source.project_name, source.project_color, source.status, source.pinned, source.created_at, source.updated_at)
    assert {t.name for t in restored.tags} == {t.name for t in source.tags}
    assert import_json(target, path) == 1
    assert len(target.search()) == 2
    db.close()
    with pytest.raises(FileExistsError):
        export_json(repo, path)
    output = tmp_path / "markdown"
    assert export_markdown(repo, output) == 1
    files = list(output.iterdir())
    assert len(files) == 1 and files[0].parent == output
    assert source.content in files[0].read_text()
    with pytest.raises(FileExistsError):
        export_markdown(repo, output)


def test_project_color_conflict_is_preserved(repo, tmp_path):
    project = repo.create_project("Project", "#F9E3EB")
    repo.create_idea("note", project)
    path = tmp_path / "export.json"
    export_json(repo, path)
    repo.update_project(project, "Project", "#E3F0FA")
    import_json(repo, path)
    assert {p.color for p in repo.projects()} == {"#F9E3EB", "#E3F0FA"}
    assert len(repo.projects()) == 2

@pytest.mark.parametrize("mutation", [
    lambda p: p["ideas"][0].update(tag_ids=[9999]),
    lambda p: p["ideas"][0].update(project_id=True),
    lambda p: p["ideas"][0].update(pinned=1),
    lambda p: p["ideas"][0].update(status="deleted"),
    lambda p: p["ideas"][0].update(created_at="not-a-date"),
    lambda p: p["projects"][0].update(color="red"),
    lambda p: p["ideas"].append(p["ideas"][0].copy()),
])
def test_invalid_import_is_atomic(repo, tmp_path, mutation):
    project = repo.create_project("Project")
    repo.create_idea("Original", project)
    path = tmp_path / "export.json"
    export_json(repo, path)
    payload = json.loads(path.read_text())
    mutation(payload)
    path.write_text(json.dumps(payload))
    before = (repo.search(), repo.projects(), repo.tags())
    with pytest.raises(ValueError):
        import_json(repo, path)
    assert (repo.search(), repo.projects(), repo.tags()) == before


def test_markdown_long_astral_unicode_filename(repo, tmp_path):
    repo.create_idea("𐐀" * 150 + "\ncontent")
    destination = tmp_path / "markdown"
    assert export_markdown(repo, destination) == 1
    path = next(destination.iterdir())
    assert len(path.name.encode("utf-8")) <= 255
    assert "content" in path.read_text()
