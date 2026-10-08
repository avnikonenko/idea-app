"""Install a per-user GNOME shortcut without replacing existing shortcuts."""
import ast
import os
from pathlib import Path
import re
import shlex
import subprocess

MEDIA = "org.gnome.settings-daemon.plugins.media-keys"
ENTRY_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/idea-inbox/"
ENTRY = MEDIA + ".custom-keybinding:" + ENTRY_PATH
BINDING = "<Control><Alt>n"


def read(schema, key):
    value = subprocess.run(["gsettings", "get", schema, key], capture_output=True, text=True, check=True).stdout.strip()
    return ast.literal_eval(value.removeprefix("@as "))


def write(schema, key, value):
    subprocess.run(["gsettings", "set", schema, key, repr(value)], capture_output=True, text=True, check=True)
    if read(schema, key) != value:
        raise OSError(f"GNOME did not persist {key}.")


def normalized(binding):
    modifiers = {part.lower().replace("primary", "control").replace("ctrl", "control").replace("mod1", "alt") for part in re.findall(r"<([^>]+)>", binding)}
    return tuple(sorted(modifiers)), re.sub(r"<[^>]+>", "", binding).lower()


def builtin_conflicts():
    for schema in (MEDIA, "org.gnome.desktop.wm.keybindings", "org.gnome.shell.keybindings"):
        result = subprocess.run(["gsettings", "list-recursively", schema], capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            fields = line.split(maxsplit=2)
            if len(fields) < 3:
                continue
            try:
                values = ast.literal_eval(fields[2].removeprefix("@as "))
            except (ValueError, SyntaxError):
                continue
            bindings = values if isinstance(values, list) else [values]
            if any(isinstance(value, str) and normalized(value) == normalized(BINDING) for value in bindings):
                raise ValueError(f"Ctrl+Alt+N is already assigned to {fields[1]}; existing binding preserved.")


def install():
    if "GNOME" not in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
        raise ValueError("This installer supports GNOME. On another desktop, bind Ctrl+Alt+N to 'idea --capture' in its settings.")
    executable = Path(__file__).resolve().parents[1] / ".venv/bin/idea"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError("Install Idea in this checkout's .venv first.")
    command = shlex.join([str(executable), "--capture"])
    paths = read(MEDIA, "custom-keybindings")
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        raise ValueError("Unexpected GNOME shortcut list; no settings were changed.")
    desired = {"name": "Idea — Add idea", "command": command, "binding": BINDING}
    original = {key: read(ENTRY, key) for key in desired}
    if any(original.values()) and original != desired:
        raise ValueError("The Idea shortcut entry was customized; existing settings preserved.")
    for path in paths:
        if path != ENTRY_PATH and normalized(read(MEDIA + ".custom-keybinding:" + path, "binding")) == normalized(BINDING):
            raise ValueError("Ctrl+Alt+N is already used by another custom shortcut; existing settings preserved.")
    builtin_conflicts()
    try:
        for key, value in desired.items():
            write(ENTRY, key, value)
        write(MEDIA, "custom-keybindings", paths if ENTRY_PATH in paths else paths + [ENTRY_PATH])
    except Exception:
        # Only restore values this installation tried to change.
        for key, value in original.items():
            write(ENTRY, key, value)
        write(MEDIA, "custom-keybindings", paths)
        raise
    print("Installed Idea quick capture: Ctrl+Alt+N")
    return command


if __name__ == "__main__":
    install()
