import re
from collections.abc import Iterable
from .database import Database, now
from .models import Idea, Project, Tag, STATUSES


def valid_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("Names must be text.")
    name = name.strip()
    if not name or len(name) > 200:
        raise ValueError("Names must contain 1–200 characters.")
    return name


def valid_color(color: str) -> str:
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("Use a color in #RRGGBB format.")
    return color.upper()


def like_literal(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"

class Repository:
    def __init__(self, database: Database):
        self.db = database
        self.conn = database.connection

    def projects(self, query: str = "") -> list[Project]:
        rows = self.conn.execute("SELECT id,name,color,created_at FROM projects WHERE name_key LIKE ? ESCAPE '\\' ORDER BY name_key,id", (like_literal(query.casefold()),))
        return [Project(**dict(row)) for row in rows]

    def tags(self, query: str = "") -> list[Tag]:
        rows = self.conn.execute("SELECT id,name FROM tags WHERE name_key LIKE ? ESCAPE '\\' ORDER BY name_key,id", (like_literal(query.casefold()),))
        return [Tag(**dict(row)) for row in rows]

    def create_project(self, name: str, color: str = "#EDE7F6") -> int:
        name, color = valid_name(name), valid_color(color)
        with self.conn:
            return self.conn.execute("INSERT INTO projects(name,name_key,color,created_at) VALUES(?,?,?,?)", (name, name.casefold(), color, now())).lastrowid

    def update_project(self, project_id: int, name: str, color: str) -> None:
        name, color = valid_name(name), valid_color(color)
        with self.conn:
            self.conn.execute("UPDATE projects SET name=?,name_key=?,color=? WHERE id=?", (name, name.casefold(), color, project_id))

    def delete_project(self, project_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM projects WHERE id=?", (project_id,))

    def create_tag(self, name: str) -> int:
        name = valid_name(name)
        with self.conn:
            return self.conn.execute("INSERT INTO tags(name,name_key) VALUES(?,?)", (name, name.casefold())).lastrowid

    def update_tag(self, tag_id: int, name: str) -> None:
        name = valid_name(name)
        with self.conn:
            self.conn.execute("UPDATE tags SET name=?,name_key=? WHERE id=?", (name, name.casefold(), tag_id))

    def delete_tag(self, tag_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM tags WHERE id=?", (tag_id,))

    def _write_idea(self, content: str, project_id: int | None, status: str,
                    pinned: bool, tags: Iterable[int], idea_id: int | None = None,
                    created_at: str | None = None, updated_at: str | None = None) -> int:
        if status not in STATUSES or not isinstance(content, str):
            raise ValueError("Invalid idea content or status")
        timestamp = now()
        if idea_id is None:
            idea_id = self.conn.execute("INSERT INTO ideas(content,project_id,status,pinned,created_at,updated_at) VALUES(?,?,?,?,?,?)", (content, project_id, status, int(pinned), created_at or timestamp, updated_at or timestamp)).lastrowid
        else:
            if self.conn.execute("UPDATE ideas SET content=?,project_id=?,status=?,pinned=?,updated_at=? WHERE id=?", (content, project_id, status, int(pinned), timestamp, idea_id)).rowcount != 1:
                raise ValueError("This idea no longer exists.")
            self.conn.execute("DELETE FROM idea_tags WHERE idea_id=?", (idea_id,))
        self.conn.executemany("INSERT INTO idea_tags(idea_id,tag_id) VALUES(?,?)", [(idea_id, tag) for tag in sorted(set(tags))])
        return idea_id

    def create_idea(self, content: str = "", project_id: int | None = None,
                    status: str = "inbox", pinned: bool = False, tags: Iterable[int] = ()) -> int:
        with self.conn:
            return self._write_idea(content, project_id, status, pinned, tags)

    def update_idea(self, idea_id: int, content: str, project_id: int | None,
                    status: str, pinned: bool, tags: Iterable[int]) -> None:
        with self.conn:
            self._write_idea(content, project_id, status, pinned, tags, idea_id)

    def delete_idea(self, idea_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM ideas WHERE id=?", (idea_id,))

    def get_idea(self, idea_id: int) -> Idea:
        ideas = self.search(idea_id=idea_id)
        if not ideas:
            raise ValueError("This idea no longer exists.")
        row = ideas[0]
        tags = tuple(Tag(**dict(r)) for r in self.conn.execute("SELECT t.id,t.name FROM tags t JOIN idea_tags it ON it.tag_id=t.id WHERE it.idea_id=? ORDER BY t.name_key,t.id", (idea_id,)))
        return Idea(**{**row.__dict__, "tags": tags})

    def search(self, query: str = "", *, project_id: int | None = None,
               tag_ids: Iterable[int] = (), status: str | None = None,
               pinned: bool | None = None, idea_id: int | None = None) -> list[Idea]:
        conditions, params = [], []
        for column, value in (("i.project_id", project_id), ("i.status", status), ("i.pinned", pinned), ("i.id", idea_id)):
            if value is not None:
                conditions.append(f"{column}=?")
                params.append(value)
        for tag in sorted(set(tag_ids)):
            conditions.append("EXISTS(SELECT 1 FROM idea_tags it WHERE it.idea_id=i.id AND it.tag_id=?)")
            params.append(tag)
        # Each unfinished word may match content, project or a tag; all words must match.
        for term in query.split():
            if len(term) >= 3:
                content_sql = "i.id IN (SELECT rowid FROM ideas_fts WHERE ideas_fts MATCH ?)"
                content_param = '"' + term.replace('"', '""') + '"'
            else:
                content_sql, content_param = "i.content LIKE ? ESCAPE '\\'", like_literal(term)
            conditions.append(f"({content_sql} OR p.name_key LIKE ? ESCAPE '\\' OR EXISTS(SELECT 1 FROM idea_tags it JOIN tags t ON t.id=it.tag_id WHERE it.idea_id=i.id AND t.name_key LIKE ? ESCAPE '\\'))")
            params.extend((content_param, like_literal(term.casefold()), like_literal(term.casefold())))
        sql = "SELECT i.*,p.name AS project_name,p.color AS project_color FROM ideas i LEFT JOIN projects p ON p.id=i.project_id"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY i.pinned DESC,i.updated_at DESC,i.id DESC"
        return [Idea(**{**dict(row), "pinned": bool(row["pinned"])}) for row in self.conn.execute(sql, params)]
