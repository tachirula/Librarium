# src/librarium/main.py

"""
Main entrypoint. Thin dispatcher: either starts the daemon (in the
foreground or daemonized) or forwards a subcommand to the running
daemon over the Unix socket.
"""

import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path

from librarium.cli.client import send_command
from librarium.cli.parser import socket_path
from librarium.context import AppContext
from librarium.service.daemon import LibrariumDaemon
from librarium.service.providers import browser_patcher


class LibrariumApp:
    def __init__(self) -> None:
        self.context = AppContext.get()

    # ---------------------- argument parsing ----------------------

    def parse_arguments(self) -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            prog="libra",
            description="Librarium Discord Rich Presence Service",
        )
        parser.add_argument(
            "--cli",
            action="store_true",
            help="Run without a frontend (CLI-only mode).",
        )
        parser.add_argument(
            "--foreground", "-F",
            action="store_true",
            help="Do not daemonize; run in the foreground (for debugging).",
        )

        sub = parser.add_subparsers(dest="command")

        p_start = sub.add_parser("start", help="Start the daemon.")
        p_start.add_argument("--foreground", "-F", action="store_true")
        p_start.add_argument("--cli", action="store_true")

        sub.add_parser("stop", help="Stop the running daemon.")
        sub.add_parser("status", help="Check whether the daemon is running.")
        sub.add_parser(
            "setup-browser",
            help="Patch browser launchers (usually done by `start`).",
        )
        sub.add_parser(
            "restore-browser",
            help="Remove the CDP patch from browser launchers.",
        )

        p_state = sub.add_parser("state", help="Update the Discord 'state' field.")
        p_state.add_argument("text", nargs="?", default="")

        p_details = sub.add_parser("details", help="Update the Discord 'details' field.")
        p_details.add_argument("text", nargs="?", default="")

        return parser.parse_args()

    # ---------------------- helpers ----------------------

    def _daemon_is_running(self) -> bool:
        path = socket_path()
        if not path.exists():
            return False
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(str(path))
            return True
        except OSError:
            return False

    def _log_path(self) -> Path:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
        log_dir = base / "librarium"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / "daemon.log"

    def _spawn_daemon(self) -> None:
        log_path = self._log_path()

        cmd = [sys.executable, "-m", "librarium.main", "start", "-F"]
        if self.context.cli_mode:
            cmd.append("--cli")

        with open(log_path, "a") as log:
            subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        print(f"Librarium daemon started (log: {log_path}).")

    def _forward_to_daemon(self, command: str) -> None:
        sys.exit(send_command(command))

    def _cleanup_stale_patch(self) -> None:
        """If the daemon is dead but a patch is present, remove it.

        Covers the case where the daemon was SIGKILLed or the machine
        crashed while the daemon was running.
        """
        if self._daemon_is_running():
            return
        if not browser_patcher.is_patched():
            return
        removed = browser_patcher.restore()
        if removed:
            print(f"Cleaned up stale browser patch: {', '.join(removed)}")

    # ---------------------- lifecycle ----------------------

    def run(self) -> None:
        args = self.parse_arguments()

        self.context.cli_mode = args.cli
        self.context.foreground = args.foreground
        self.context.command = args.command

        # Explicitly patched/unpatched via subcommands
        if args.command == "setup-browser":
            patched = browser_patcher.setup()
            if patched:
                print(f"Patched: {', '.join(patched)}.")
                print("Fully quit the browser (all windows), then reopen.")
            else:
                print("No supported browsers found to patch.")
            return

        if args.command == "restore-browser":
            removed = browser_patcher.restore()
            if removed:
                print(f"Restored: {', '.join(removed)}.")
            else:
                print("No patches found to remove.")
            return

        # Any other command: clean up leftover patches if no daemon is alive
        self._cleanup_stale_patch()

        # Commands forwarded to the running daemon
        if args.command == "status":
            self._forward_to_daemon("status")
        if args.command == "stop":
            self._forward_to_daemon("stop")
        if args.command == "state":
            self._forward_to_daemon(f"state {args.text}")
        if args.command == "details":
            self._forward_to_daemon(f"details {args.text}")

        # Start (or default command with no subcommand)
        if args.command in (None, "start"):
            if self._daemon_is_running():
                print("Librarium daemon is already running.")
                sys.exit(0)

            if self.context.foreground:
                LibrariumDaemon().run()
                return

            self._spawn_daemon()
            return

        print(f"Unknown command: {args.command}")
        sys.exit(1)


def main() -> None:
    LibrariumApp().run()


if __name__ == "__main__":
    main()
