"""Portable exports and atomic, additive imports."""
import json
import os
from contextlib import contextmanager
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from .models import STATUSES, Project
from .repository import Repository, valid_name, valid_color

FORMAT_VERSION = 1

@contextmanager
def new_text_file(path: Path):
    # Exclusive creation prevents overwrites; failed writes remove only our file.
    output = Path(path).open("x", encoding="utf-8")
    try:
        with output:
            yield output
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        Path(path).unlink(missing_ok=True)
        raise

def export_json(repo: Repository, path: Path) -> None:
    # Snapshot all tables in the same read transaction.
    with repo.conn:
        repo.conn.execute("BEGIN")
        ideas = [dict(row) for row in repo.conn.execute("SELECT * FROM ideas ORDER BY id")]
        associations = {}
        for row in repo.conn.execute("SELECT idea_id,tag_id FROM idea_tags ORDER BY idea_id,tag_id"):
            associations.setdefault(row[0], []).append(row[1])
        for idea in ideas:
            idea["pinned"] = bool(idea["pinned"])
            idea["tag_ids"] = associations.get(idea["id"], [])
        payload = {"format": "idea-inbox", "version": FORMAT_VERSION,
                   "projects": [asdict(p) for p in repo.projects()],
                   "tags": [asdict(t) for t in repo.tags()], "ideas": ideas}
    with new_text_file(Path(path)) as output:
        json.dump(payload, output, ensure_ascii=False, indent=2)
        output.write("\n")


def _identifier(value) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("Identifiers must be positive integers")
    return value


def _timestamp(value) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Timestamps must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def validate_payload(payload: dict) -> None:
    if not isinstance(payload, dict) or payload.get("format") != "idea-inbox" or type(payload.get("version")) is not int or payload["version"] != FORMAT_VERSION:
        raise ValueError("Unsupported Idea JSON format/version")
    ids = {}
    for kind in ("projects", "tags", "ideas"):
        rows = payload.get(kind)
        if not isinstance(rows, list):
            raise ValueError(f"Missing {kind} array")
        ids[kind] = set()
        names = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"Invalid {kind} record")
            identity = _identifier(row.get("id"))
            if identity in ids[kind]:
                raise ValueError(f"Duplicate identifier in {kind}")
            ids[kind].add(identity)
            if kind != "ideas":
                name = valid_name(row.get("name", ""))
                if name.casefold() in names:
                    raise ValueError(f"Duplicate name in {kind}")
                names.add(name.casefold())
            if kind == "projects":
                valid_color(row.get("color"))
                _timestamp(row.get("created_at"))
    for idea in payload["ideas"]:
        if not isinstance(idea.get("content"), str) or idea.get("status") not in STATUSES or type(idea.get("pinned")) is not bool:
            raise ValueError("Invalid idea content/status/pinned flag")
        _timestamp(idea.get("created_at"))
        _timestamp(idea.get("updated_at"))
        project = idea.get("project_id")
        if project is not None and _identifier(project) not in ids["projects"]:
            raise ValueError("Unknown project reference")
        tags = idea.get("tag_ids")
        if not isinstance(tags, list) or any(_identifier(tag) not in ids["tags"] for tag in tags) or len(tags) != len(set(tags)):
            raise ValueError("Invalid tag references")


def import_json(repo: Repository, path: Path) -> int:
    with Path(path).open(encoding="utf-8") as source:
        payload = json.load(source)
    validate_payload(payload)
    # Never reuse idea IDs. Reuse exact organization matches; preserve conflicting
    # project colors by making a uniquely named imported project.
    with repo.conn:
        project_map, tag_map = {}, {}
        projects = {p.name.casefold(): p for p in repo.projects()}
        for project in payload["projects"]:
            name, color = valid_name(project["name"]), valid_color(project["color"])
            existing = projects.get(name.casefold())
            if existing and existing.color == color:
                project_map[project["id"]] = existing.id
                continue
            base, suffix = name, 1
            while name.casefold() in projects:
                suffix += 1
                name = f"{base[:170]} (import {suffix})"
            identity = repo.conn.execute("INSERT INTO projects(name,name_key,color,created_at) VALUES(?,?,?,?)", (name, name.casefold(), color, _timestamp(project["created_at"]))).lastrowid
            projects[name.casefold()] = Project(identity, name, color, _timestamp(project["created_at"]))
            project_map[project["id"]] = identity
        tags = {t.name.casefold(): t.id for t in repo.tags()}
        for tag in payload["tags"]:
            name = valid_name(tag["name"])
            if name.casefold() not in tags:
                tags[name.casefold()] = repo.conn.execute("INSERT INTO tags(name,name_key) VALUES(?,?)", (name, name.casefold())).lastrowid
            tag_map[tag["id"]] = tags[name.casefold()]
        for idea in payload["ideas"]:
            repo._write_idea(idea["content"], project_map.get(idea["project_id"]), idea["status"], idea["pinned"], [tag_map[t] for t in idea["tag_ids"]], created_at=_timestamp(idea["created_at"]), updated_at=_timestamp(idea["updated_at"]))
    return len(payload["ideas"])


def export_markdown(repo: Repository, directory: Path) -> int:
    # The caller selects a new directory; never mix with or overwrite user files.
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    with repo.conn:
        repo.conn.execute("BEGIN")
        ideas = [repo.get_idea(i.id) for i in repo.search()]
    for idea in ideas:
        title = re.sub(r"[^\w .-]", "_", idea.title, flags=re.UNICODE).strip(" .").encode("utf-8")[:180].decode("utf-8", errors="ignore") or "idea"
        metadata = {"id": idea.id, "project": idea.project_name, "project_color": idea.project_color,
                    "tags": [tag.name for tag in idea.tags], "status": idea.status,
                    "pinned": idea.pinned, "created_at": idea.created_at, "updated_at": idea.updated_at}
        with new_text_file(directory / f"{idea.id}-{title}.md") as output:
            output.write("```json\n" + json.dumps(metadata, ensure_ascii=False, indent=2) + "\n```\n\n" + idea.content + "\n")
    return len(ideas)
