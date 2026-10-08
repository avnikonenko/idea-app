import os
import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
import tempfile


def _xdg_directory(variable: str, default: Path) -> Path:
    value = os.environ.get(variable)
    if not value:
        return default
    path = Path(value)
    if not path.is_absolute():
        logging.getLogger(__name__).warning("Ignoring relative %s; using its default directory", variable)
        return default
    return path


def data_path() -> Path:
    return _xdg_directory("XDG_DATA_HOME", Path.home() / ".local/share") / "idea" / "ideas.db"


def config_path() -> Path:
    return _xdg_directory("XDG_CONFIG_HOME", Path.home() / ".config") / "idea" / "config.toml"

@dataclass
class Config:
    theme: str = "light"
    splitter: list[int] = field(default_factory=lambda: [180, 320, 560])
    width: int = 1060
    height: int = 720

    @classmethod
    def load(cls, path: Path) -> "Config":
        if not path.exists():
            return cls()
        with path.open("rb") as source:
            values = tomllib.load(source)
        theme = values.get("theme", "light")
        splitter = values.get("splitter", [180, 320, 560])
        width, height = values.get("width", 1060), values.get("height", 720)
        if theme not in ("light", "dark") or not isinstance(splitter, list) or len(splitter) != 3 or any(type(n) is not int or n < 0 for n in splitter):
            raise ValueError("Invalid theme or splitter configuration")
        if any(type(n) is not int or n < 1 for n in (width, height)):
            raise ValueError("Invalid window dimensions")
        return cls(theme, splitter, width, height)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        value = f'theme = "{self.theme}"\nsplitter = {self.splitter}\nwidth = {self.width}\nheight = {self.height}\n'
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as output:
                temporary = Path(output.name)
                output.write(value)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
