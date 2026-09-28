# src/librarium/service/providers/browser_patcher.py

"""
Patches and restores browser .desktop entries so they launch with a
local-only CDP endpoint. The patch is designed to be temporary: the
daemon applies it on start and removes it on shutdown.

Security model:
  - CDP binds to 127.0.0.1 only.
  - Only origins set to http://localhost:9222 are accepted, which no
    website can spoof (the browser sets the Origin header itself).
  - Clients that send no Origin header (local processes) are NOT
    filtered by this flag. Any local process can reach the port while
    the browser runs with the patch.

User overrides:
  - If the user already has a personal override of a launcher in
    ~/.local/share/applications/, it is moved to `<name>.librarium-bak`
    before patching, used as the base for the patch (so their own flags
    survive), and moved back by restore().
  - Files are only deleted by restore() when they carry our marker.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


CDP_PORT = 9222
CDP_ORIGIN = f"http://localhost:{CDP_PORT}"
_FLAGS = (
    f"--remote-debugging-port={CDP_PORT} "
    f"--remote-allow-origins={CDP_ORIGIN}"
)

# Legacy marker (older versions had no comment marker).
_PATCH_MARKER = f"--remote-debugging-port={CDP_PORT}"

# Explicit marker written as a comment at the end of files we create.
_MANAGED_MARK = "# Librarium-managed: created by Librarium, safe to delete."

_BACKUP_SUFFIX = ".librarium-bak"

# Overrides we may write to ~/.local/share/applications/
_OVERRIDE_NAMES = (
    "brave-browser.desktop",
    "brave_brave.desktop",
    "google-chrome.desktop",
    "chromium.desktop",
    "chromium_chromium.desktop",
    "microsoft-edge.desktop",
)

# (label, [candidate system .desktop paths in priority order])
_SOURCES = (
    ("Brave", (
        "/usr/share/applications/brave-browser.desktop",
        "/var/lib/snapd/desktop/applications/brave_brave.desktop",
    )),
    ("Google Chrome", (
        "/usr/share/applications/google-chrome.desktop",
    )),
    ("Chromium", (
        "/usr/share/applications/chromium.desktop",
        "/var/lib/snapd/desktop/applications/chromium_chromium.desktop",
    )),
    ("Microsoft Edge", (
        "/usr/share/applications/microsoft-edge.desktop",
    )),
)


# ---------------------- helpers ----------------------

def _overrides_dir() -> Path:
    d = Path.home() / ".local/share/applications"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _backup_path(target: Path) -> Path:
    return target.with_name(target.name + _BACKUP_SUFFIX)


def _is_ours(text: str) -> bool:
    """True if this override was created by Librarium."""
    if _MANAGED_MARK in text:
        return True
    # Legacy patches: both flags exactly as we write them.
    return _PATCH_MARKER in text and CDP_ORIGIN in text


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _refresh_desktop_db() -> None:
    try:
        subprocess.run(
            ["update-desktop-database", str(_overrides_dir())],
            check=False,
        )
    except OSError:
        # update-desktop-database (desktop-file-utils) is not installed.
        pass


def _patched_content(original: str) -> str:
    lines = []
    for line in original.splitlines():
        if line.startswith("Exec=") and "--remote-debugging-port" not in line:
            if " %" in line:
                prefix, sep, suffix = line.partition(" %")
                line = f"{prefix} {_FLAGS}{sep}{suffix}"
            else:
                line = f"{line} {_FLAGS}"
        lines.append(line)
    return "\n".join(lines).rstrip("\n") + "\n" + _MANAGED_MARK + "\n"


# ---------------------- public API ----------------------

def setup() -> list[str]:
    """Patch browser launchers. Idempotent. Returns patched labels."""
    patched: list[str] = []
    overrides_dir = _overrides_dir()

    for label, sources in _SOURCES:
        for src in sources:
            system = Path(src)
            if not system.exists():
                continue

            target = overrides_dir / system.name
            backup = _backup_path(target)

            if target.exists():
                current = target.read_text(encoding="utf-8")
                if _is_ours(current):
                    # Already patched with our exact flags?
                    if CDP_ORIGIN in current:
                        patched.append(label)
                        break
                    # Ours but stale: regenerate below.
                elif backup.exists():
                    # A personal override AND an old backup: don't guess.
                    print(
                        f"[patcher] {target.name}: personal override found "
                        f"next to an existing backup; leaving it untouched.",
                        flush=True,
                    )
                    break
                else:
                    # The user's own override: keep it safe.
                    target.replace(backup)

            # Base = the user's own override if we saved one, else system.
            base = backup if backup.exists() else system
            _atomic_write(
                target,
                _patched_content(base.read_text(encoding="utf-8")),
            )
            patched.append(label)
            break

    if patched:
        _refresh_desktop_db()
    return patched


def restore() -> list[str]:
    """Remove our patches and put back any override we backed up.

    Returns the list of .desktop filenames that were changed.
    """
    overrides_dir = _overrides_dir()
    removed: list[str] = []

    for name in _OVERRIDE_NAMES:
        f = overrides_dir / name
        backup = _backup_path(f)
        changed = False

        if f.exists() and _is_ours(f.read_text(encoding="utf-8")):
            f.unlink()
            changed = True

        if backup.exists() and not f.exists():
            backup.replace(f)
            changed = True

        if changed:
            removed.append(name)

    if removed:
        _refresh_desktop_db()
    return removed


def is_patched() -> bool:
    """True if at least one of our patched overrides exists."""
    overrides_dir = _overrides_dir()
    for name in _OVERRIDE_NAMES:
        f = overrides_dir / name
        if f.exists() and _is_ours(f.read_text(encoding="utf-8")):
            return True
    return False
