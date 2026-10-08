from dataclasses import dataclass, field

STATUSES = ("inbox", "active", "someday", "archived")
DEFAULT_TAGS = ("Idea", "Question", "Experiment", "Reading", "Improvement", "Learning", "Personal")
COLORS = {
    "Lavender": "#EDE7F6", "Mint": "#E2F3E8", "Blue": "#E3F0FA",
    "Peach": "#FCE8DC", "Yellow": "#FFF4CF", "Pink": "#F9E3EB",
    "Sage": "#E4EDDF", "Gray": "#F0F0F0",
}

@dataclass(frozen=True)
class Project:
    id: int
    name: str
    color: str
    created_at: str

@dataclass(frozen=True)
class Tag:
    id: int
    name: str

@dataclass(frozen=True)
class Idea:
    id: int
    content: str
    project_id: int | None
    status: str
    pinned: bool
    created_at: str
    updated_at: str
    project_name: str | None = None
    project_color: str | None = None
    tags: tuple[Tag, ...] = field(default_factory=tuple)

    @property
    def title(self) -> str:
        return next((line.strip() for line in self.content.splitlines() if line.strip()), "Untitled idea")
