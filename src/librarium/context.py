# src/librarium/context.py
"""
Shared application context. Holds CLI flags and runtime state so any
module can consult them without re-parsing argv or threading params
through every call.

The context is a singleton: `AppContext.get()` always returns the same
instance within a process. Note that a daemonized child process is a
different process, so it parses its own argv (we forward `--cli` to it)
and builds its own context.
"""

from typing import Optional


class AppContext:
    _instance: Optional["AppContext"] = None

    def __init__(self) -> None:
        self.cli_mode: bool = False
        self.foreground: bool = False
        self.command: Optional[str] = None

    @classmethod
    def get(cls) -> "AppContext":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Mostly useful for tests."""
        cls._instance = None

    def __repr__(self) -> str:
        return (
            f"AppContext(cli_mode={self.cli_mode}, "
            f"foreground={self.foreground}, command={self.command!r})"
        )