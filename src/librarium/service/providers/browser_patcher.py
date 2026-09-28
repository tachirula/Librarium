# src/librarium/service/providers/browser_patcher.py

"""
Patches and restores browser .desktop entries so they launch with a
local-only CDP endpoint. The patch is designed to be temporary: the
daemon applies it on start and removes it on shutdown.

Security model:
  - CDP binds to 127.0.0.1 only.
  - Only origins set to http://localhost:9222 are accepted, which no
    website can spoof (the browser sets the Origin header itself).
"""

from __future__ import annotations

import subprocess
from pathlib import Path


CDP_PORT = 9222
CDP_ORIGIN = f"http://localhost:{CDP_PORT}"
_FLAGS = (
    f"--remote-debugging-port={CDP_PORT} "
    f"--remote-allow-origins={CDP_ORIGIN}"
)

# Marker used to recognize our own patch (do not touch other patches).
_PATCH_MARKER = f"--remote-debugging-port={CDP_PORT}"

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


def _overrides_dir() -> Path:
    d = Path.home() / ".local/share/applications"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _refresh_desktop_db() -> None:
    subprocess.run(
        ["update-desktop-database", str(_overrides_dir())],
        check=False,
    )


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
    return "\n".join(lines)


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

            # Already patched with our exact flags?
            if target.exists() and CDP_ORIGIN in target.read_text():
                patched.append(label)
                break

            target.write_text(_patched_content(system.read_text()))
            patched.append(label)
            break

    if patched:
        _refresh_desktop_db()
    return patched


def restore() -> list[str]:
    """Remove our patches. Returns list of removed .desktop filenames."""
    overrides_dir = _overrides_dir()
    removed: list[str] = []

    for name in _OVERRIDE_NAMES:
        f = overrides_dir / name
        if not f.exists():
            continue
        if _PATCH_MARKER not in f.read_text():
            continue
        f.unlink()
        removed.append(name)

    if removed:
        _refresh_desktop_db()
    return removed


def is_patched() -> bool:
    """True if at least one of our patched overrides exists."""
    overrides_dir = _overrides_dir()
    for name in _OVERRIDE_NAMES:
        f = overrides_dir / name
        if f.exists() and _PATCH_MARKER in f.read_text():
            return True
    return False