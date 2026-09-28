#src/librarium/cli/parser.py
"""
Helpers for the CLI side. Keeps the socket path in one place so the
client and the daemon agree on where to talk to each other.
"""
import os
from pathlib import Path


def _socket_dir() -> Path:
    """Private directory for the IPC socket.

    Prefers $XDG_RUNTIME_DIR (already 0700 and per-user). If it is not
    set, falls back to a private directory under the user's cache instead
    of the world-writable /tmp.
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime)

    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    d = cache / "librarium"
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    return d


def socket_path() -> Path:
    return _socket_dir() / f"librarium-{os.getuid()}.sock"
