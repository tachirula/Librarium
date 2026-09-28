#src/librarium/cli/parser.py
"""
Helpers for the CLI side. Keeps the socket path in one place so the
client and the daemon agree on where to talk to each other.
"""
import os
from pathlib import Path


def socket_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return Path(runtime) / f"librarium-{os.getuid()}.sock"