# Idea

A small, local-first idea inbox for Ubuntu. Python 3.12+, PySide6, SQLite FTS5,
and plain text. No accounts, network requests, AI, server or daemon. A panel icon provides quick capture.

## Install and launch

From this directory, with Python 3.12 or later and its `venv` module installed:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/idea
```

This workspace already has an installed `.venv`; launch it with:

```bash
cd /home/sany/Workspace/system_setup/idea-inbox
.venv/bin/idea
```

Installation downloads Qt/Python packages; using Idea requires no internet.
No system configuration is changed. The Qt runtime is a substantial download;
the application itself uses only the Python standard library and PySide6.
SQLite must support FTS5 and its trigram tokenizer (SQLite 3.34+).

Qt automatically selects the desktop platform. If platform selection needs to
be explicit, use `QT_QPA_PLATFORM=wayland .venv/bin/idea` on Wayland, or
`QT_QPA_PLATFORM=xcb .venv/bin/idea` on X11. Qt's platform plugins require their
normal desktop system libraries. The installed package was tested on Ubuntu
26.04, Python 3.14.4 and Qt 6.11.2, including a native Wayland launch and graceful
close. Python 3.12 and other Ubuntu releases were not separately exercised.

A separate portable/test database and configuration can be selected:

```bash
.venv/bin/idea --database /path/to/ideas.db --config /path/to/config.toml
```

Only one application instance can edit a given database at once. This prevents
stale editors from overwriting one another. A second launch reports the lock;
it does not open another editor or activate the existing window.

## Desktop icon and login autostart

To install the current checkout for your user:

```bash
.venv/bin/python tools/install_desktop.py
```

This adds **Idea** with a lightbulb icon to the application menu and launches its
panel icon when you log in, keeping the main window hidden. It uses the per-user XDG application/autostart
locations, following the [Freedesktop autostart specification](https://specifications.freedesktop.org/autostart/latest/).
It does not start a daemon or change system-wide settings. The application also
uses its bundled icon for its window, and identifies itself as `idea-inbox` for
Wayland launcher/dock association.

The installer refers to this checkout's `.venv/bin/idea`; keep that directory in
place. It refuses to replace conflicting existing files and can be rerun when
its installed files are identical. The exact previous installer-generated
autostart entry can be upgraded to panel-only startup; customized entries are
preserved. To disable login autostart, remove only
`~/.config/autostart/idea-inbox.desktop` (or the corresponding `XDG_CONFIG_HOME`
path); the application-menu launcher remains available. Favorites/dock pinning
can be done through your desktop's normal **Add to Favorites** action.

## Top-panel Add note icon

Idea shows its lightbulb icon in your desktop's panel/tray. Select **+ Add note**
from its menu to open quick capture, **Open Idea** to return to the main window,
or **Quit Idea** to flush edits and exit. Desktops that support direct activation
also open capture on a normal or middle click. On Ubuntu/GNOME, a click may open
the menu instead; **+ Add note** is always provided.

Closing the main window saves pending edits and leaves the panel icon running.
**Quit Idea**, in the panel menu or File menu, exits; failed saves or a cancelled
capture-discard confirmation prevent exit. Capturing from the panel uses the same
process, database and error handling as the editor. There is no floating desktop
window or always-on-top window. Panel-only startup preserves the editor's saved
size and splitter positions even when the editor was never opened.

```bash
.venv/bin/idea --tray     # Panel-only startup; fallback to editor if unsupported
.venv/bin/idea --no-tray  # Main window only; closing it exits
```

The icon uses [Qt's Linux tray support](https://doc.qt.io/qt-6/qsystemtrayicon.html)
and requires a desktop tray/StatusNotifier host. This Ubuntu Wayland session has
that support already. If it is unavailable, Idea shows the ordinary window
instead of leaving an inaccessible hidden application. Qt can register the icon
later if the panel is still starting at login. Exact icon ordering is controlled
by your desktop. Other Ubuntu installations may need their normal panel tray
support enabled; this application does not install desktop extensions.

## Capture, organize and find ideas

- Click **New idea** to create a blank Inbox idea. The first nonempty line is its
  title; no separate title is required. Paste multiline text, URLs or code.
- Content saves after 350 ms of inactivity. Project, tag, status and pin changes
  save immediately, including pending text. Switching ideas, filtering, export,
  capture opening and closing also flush pending changes.
- If a write fails, edits remain in the editor. Navigation and shutdown are
  blocked until a retry succeeds. Correct the underlying problem, then press
  **Ctrl+S**. Autosave cannot protect the last debounce interval from a hard kill,
  process crash or power loss.
- Choose Inbox, Active, Someday, Archive, Pinned or All ideas on the left. Combine
  a view with **Pinned only**, a project and multiple tags. Tags use AND semantics.
- Search matches every whitespace-separated word, anywhere in idea content,
  project names or assigned tag names. Words can match different fields. Search
  is literal, case-insensitive for ordinary Latin text and debounced by 180 ms.
  FTS5 trigram indexing supports substring/unfinished-word matches of 3+ characters;
  shorter words use a literal SQL substring fallback. There is no query syntax,
  fuzzy matching, stemming or semantic search. Accent-insensitive matching is
  not enabled; Unicode text is stored unchanged.
- Projects and tags are optional. Type in a project selector to autocomplete,
  then choose an existing project. Use **+** to create one. Type an existing or
  new tag and click **Add**; click its chip's **×** to remove it.
- **Manage projects** / **Manage tags** offer search, creation, rename and delete.
  Names are unique using Unicode case folding. Deleting organization preserves
  ideas: projects become unassigned and tag associations are removed.
- Project management offers eight pastel presets, a color picker and HEX entry.
  The entire idea row uses its project's background; changes update immediately.
  Custom colors choose black/white text for contrast, and dark mode adapts colors.
- Drag the three panel boundaries to resize them. Panel sizes, window dimensions
  and theme persist in TOML. Light is the default; select a theme in **Theme**.
- Right-click an idea to pin/unpin, archive or view **Details** (creation and
  last-modified timestamps in local time, including the UTC offset). Archived
  ideas also offer **Restore to Inbox** and **Delete permanently**. Restore keeps
  content, project, tags, pin and creation time; deletion asks for confirmation
  and removes the idea and its tag/FTS associations. It cannot be undone in Idea,
  although older backups/exports may still contain the idea. Up/Down navigate when the list has
  focus; text-editor arrow keys and selection retain their standard behavior.

The project navigation is a searchable selector rather than a long project list,
which keeps the sidebar usable on smaller screens. The list uses Qt model/view
and a delegate, not one widget per idea. Results sort pinned first, then most
recently modified, with a stable ID tie-break. Selection and scroll are retained
when possible; filtering an idea out selects the first remaining result.

## Quick capture and shortcuts

**Quick capture** opens a small window with immediate text focus, optional project
and tags, and Save/Cancel. It defaults to Inbox. Esc/window close asks before
throwing away typed content or selected organization; a failed save retains it.
The capture window is modal to the main window, preventing conflicting edits.

| Action | Shortcut |
| --- | --- |
| New idea | Ctrl+N |
| Search | Ctrl+F |
| Flush/save | Ctrl+S |
| Archive selected idea | Ctrl+E |
| Pin/unpin selected idea | Ctrl+P |
| Quick capture | Ctrl+Shift+N |
| Save quick capture | Ctrl+Enter |
| Close quick capture | Esc, with discard confirmation |

These shortcuts are application-local. There is no global shortcut in this MVP; this avoids desktop-specific Wayland
shortcut behavior. The explicitly enabled panel icon keeps this same GUI process
alive when its main window is hidden.

## Storage, backups and restoration

Default locations respect `XDG_DATA_HOME` and `XDG_CONFIG_HOME`:

- Database: `~/.local/share/idea/ideas.db`
- Automatic backups: `~/.local/share/idea/backups/ideas-<UTC timestamp>.db`
- Configuration: `~/.config/idea/config.toml`

SQLite foreign keys, transactional writes, WAL and FULL synchronous mode protect
consistency. Schema version 1 is recorded in `PRAGMA user_version`; newer schemas
are rejected, and existing databases are backed up before initial migration.

A consistent backup is made on the first launch of each UTC day. Keep the newest
seven automatic backups. There is no periodic background worker: a long-running
session does not make new daily backups until relaunched. Use **File → Back up
now** to save an additional consistent backup whenever needed. Backup failures
are reported; a failed automatic backup prevents startup rather than hiding the
problem. Backups use SQLite's backup API and are integrity-checked, never copied
from a live database with a file copy. Manual backups never replace existing files.

To restore without overwriting anything:

1. Close Idea.
2. Choose a backup and inspect its integrity if desired:

   ```bash
   .venv/bin/python -c 'import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute("PRAGMA integrity_check").fetchone()[0])' /path/to/backup.db
   ```

3. Copy it to a **new** database pathname; preserve the current database and its
   `-wal`/`-shm` files as a set. Never replace an active database or mix old WAL files
   with a restored database.
4. Launch `.venv/bin/idea --database /path/to/restored.db`. Once verified, continue
   using that path, or move the entire old default data directory aside and place
   the restored database into a new default data directory while Idea is closed.

The SQLite database is not encrypted. Its files use the user's normal filesystem
permissions. Store it somewhere protected if the content is sensitive.

## Export and import

**File → Export JSON** writes the versioned `idea-inbox` format, containing all
ideas, projects (including colors/creation dates), tags and relationships. It
preserves idea content, status, pinned state and timestamps. Existing export files
are rejected, even if the file dialog's overwrite prompt was accepted.

**Export Markdown** creates a new timestamped directory under a chosen parent.
Each file has a unique ID plus a sanitized title, JSON metadata in a fenced block,
and the exact plain-text content. A failed multi-file export can leave already
completed files; the error is reported. Markdown import is not supported.

**Import JSON** validates the full document before an atomic transaction:

- Every idea receives a new local ID. Existing ideas are never overwritten.
- Reimporting the same export intentionally creates duplicate ideas; the UI warns.
- Tags with matching case-folded names are reused.
- Projects with matching names and colors are reused. Color conflicts get a new,
  uniquely named `(import N)` project, preserving both colors.
- Existing organization, including any default tags, remains. Imports are additive,
  not destructive database replacements. For an exact database restore, use backups.
- Invalid references, repeated IDs/names, invalid colors/statuses/flags and invalid
  timestamps reject the entire import. Imported timestamps normalize to UTC.

## Tests and reproducible measurements

```bash
.venv/bin/python -m pip install -e '.[test]'
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/python tools/benchmark.py
```

Tests use temporary databases and temporary XDG locations; they never access real
notes. Core and Qt tests cover schema setup, persistence, Unicode, organization,
FTS synchronization, literal search, combined filters, autosave, write failures,
shutdown, quick capture, export/import validation and backup integrity.

The deterministic benchmark creates 10,000 ideas in a temporary database and
measures ten queries per scenario. It writes a local `benchmark-preview.png` and
prints JSON; [benchmark-results.json](benchmark-results.json) records this run.
Measured on Linux/Python 3.14.4/Qt 6.11.2 with **offscreen Qt**, not a desktop compositor:

| Measurement | Result |
| --- | --- |
| All 10,000 rows, median | 36.18 ms |
| Content search, median, 10,000 matches | 41.96 ms |
| Project-name search, median, 5,000 matches | 21.90 ms |
| Tag-name search, median, 2,000 matches | 12.32 ms |
| Combined filters, median, 39 matches | 1.54 ms |
| GUI construction through first offscreen display | 100.93 ms |
| Fresh-process first display, including startup backup | 273.43 ms |
| Peak process RSS, including Qt and generated dataset | 122.96 MiB |
| Idle CPU over a two-second event-loop sample | 0.13% of one core |

These are observations, not guarantees. GUI construction excludes interpreter,
module import and automatic-backup time. Searches are synchronous and materialize
result records; much larger collections, very large individual notes, one-character
queries, backup/export/import and slow storage can pause the UI. The tests and
measurements cover the specified 10,000-idea dataset, not every hardware/desktop
combination. Fresh-process startup was measured with a warm filesystem cache;
no cold-filesystem or long-duration idle benchmark was performed. All 99 tests
passed in the final validation run.


The bug audit also covers actions while filtered edits change the selected row,
editor selection and undo retention, cancelled-capture organization refresh,
failed reads and reentrant save warnings, temporary menu/completer cleanup,
unrelated or mismatched database rejection, backup connection closure, import
rollback, and empty/relative XDG settings. Invalid databases are rejected before
schema or journal changes. Empty XDG settings use the standard default locations;
the app warns and falls back for relative values, while the desktop installer
rejects relative paths. An isolated Ubuntu Wayland smoke test passed capture,
pin, archive, restoration, deletion and database integrity checks with a tray
available. No real notes were used in validation.
