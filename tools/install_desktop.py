"""Install the current checkout's launcher, icon and login autostart for this user."""
import os
from pathlib import Path


def desktop_exec(path: Path) -> str:
    value = str(path)
    if any(char in value for char in "\r\n\0="):
        raise ValueError("Unsupported character in executable path")
    # Desktop Entry string escaping is applied before Exec quoting/field codes.
    escaped = value.replace("\\", "\\\\\\\\")
    for char in ('"', '`', '$'):
        escaped = escaped.replace(char, "\\\\" + char)
    return '"' + escaped.replace("%", "%%") + '"'


def install() -> list[Path]:
    project = Path(__file__).resolve().parents[1]
    executable = project / ".venv/bin/idea"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError("Install Idea in this checkout's .venv first; see README.md.")
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    if not data.is_absolute() or not config.is_absolute():
        raise ValueError("XDG directories must be absolute paths")
    icon = data / "icons/hicolor/scalable/apps/idea-inbox.svg"
    # Absolute Icon avoids depending on a desktop's icon-cache refresh policy.
    entry = ("[Desktop Entry]\nType=Application\nVersion=1.0\nName=Idea\n"
             "Comment=Capture, organize and revisit ideas\n"
             f"Exec={desktop_exec(executable)}\nIcon={icon}\n"
             "Terminal=false\nCategories=Office;\nStartupNotify=false\n")
    payloads = {
        icon: (project / "src/idea/assets/idea-inbox.svg").read_bytes(),
        data / "applications/idea-inbox.desktop": entry.encode("utf-8"),
        config / "autostart/idea-inbox.desktop": entry.encode("utf-8"),
    }
    # Preflight every file before mutation. Reruns accept identical files only.
    for path, content in payloads.items():
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.read_bytes() != content)):
            raise FileExistsError(f"Refusing to replace existing file: {path}")
    created = []
    try:
        for path, content in payloads.items():
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as output:
                    created.append(path)
                    output.write(content)
            print(f"Installed: {path}")
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    return list(payloads)


if __name__ == "__main__":
    install()
