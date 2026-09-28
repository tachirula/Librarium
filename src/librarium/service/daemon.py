# src/librarium/service/daemon.py

"""
Background daemon. Owns the IPC socket, the AppController, and the
browser patch lifecycle. Patches the browser on start, restores it on
any reasonably catchable shutdown path.
"""

from __future__ import annotations

import atexit
import os
import select
import signal
import socket
import traceback

from librarium.cli.parser import socket_path
from librarium.service.app_controller import DEFAULT_DETAILS, AppController
from librarium.service.providers import browser_patcher


class LibrariumDaemon:
    def __init__(self):
        self.app = AppController()
        self.running = True
        self.sock_path = socket_path()
        self.server = None
        self._stopped = False

    # ---------------------- setup ----------------------

    def _setup_socket(self):
        try:
            self.sock_path.unlink()
        except FileNotFoundError:
            pass
        except PermissionError as e:
            raise RuntimeError(
                f"cannot replace existing socket {self.sock_path}: {e}"
            ) from e

        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        # Create the socket already restricted to the owner: no window
        # between bind() and chmod() where it has wider permissions.
        old_umask = os.umask(0o177)
        try:
            self.server.bind(str(self.sock_path))
        finally:
            os.umask(old_umask)
        os.chmod(self.sock_path, 0o600)

        self.server.listen(8)
        self.server.setblocking(False)

    def _install_signal_handlers(self):
        def _handle(signum, frame):
            print(f"\n[daemon] signal {signum}, shutting down...", flush=True)
            self.running = False

        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            try:
                signal.signal(sig, _handle)
            except (ValueError, OSError):
                # Not in main thread, or signal not supported on this OS
                pass

    # ---------------------- client handling ----------------------

    def _handle_client(self, conn: socket.socket):
        try:
            conn.settimeout(2.0)
            data = conn.recv(4096).decode("utf-8", errors="replace").strip()
            if not data:
                return
            response = self._dispatch(data)
            if response:
                conn.sendall(response.encode("utf-8"))
        except Exception as e:
            try:
                conn.sendall(f"error: {e}".encode())
            except Exception:
                pass
        finally:
            conn.close()

    def _dispatch(self, raw: str) -> str:
        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "ping":
            return "pong"
        if cmd == "status":
            return "running"
        if cmd == "state":
            self.app.set_manual_presence(
                details=DEFAULT_DETAILS,
                state=arg or "Idle",
            )
            return f"state -> {arg or 'Idle'}"
        if cmd == "details":
            self.app.set_manual_presence(
                details=arg or DEFAULT_DETAILS,
                state="Idle",
            )
            return f"details -> {arg or DEFAULT_DETAILS}"
        if cmd in ("quit", "stop"):
            self.running = False
            return (
                "stopping (a browser that is already open keeps its debug "
                "port until you fully quit it)"
            )
        return f"unknown command: {cmd}"

    # ---------------------- main loop ----------------------

    def run(self):
        print("Starting Librarium daemon...", flush=True)

        # Make sure we always restore, even on uncaught exceptions
        atexit.register(self.stop)
        self._install_signal_handlers()

        # Socket first: `libra status` must see a live daemon before the
        # browser is patched, otherwise the stale-patch cleanup could
        # remove the patch while we are starting up.
        self._setup_socket()

        patched = browser_patcher.setup()
        if patched:
            print(f"[daemon] browser patched: {', '.join(patched)}", flush=True)
            print("[daemon] restart any open browser for CDP to take effect.", flush=True)
        else:
            print("[daemon] no supported browser found to patch.", flush=True)

        self.app.start()
        print(f"Listening on {self.sock_path}.", flush=True)

        try:
            while self.running:
                try:
                    rlist, _, _ = select.select([self.server], [], [], 1.0)
                except InterruptedError:
                    continue
                except OSError:
                    break

                for s in rlist:
                    if s is self.server:
                        try:
                            conn, _ = self.server.accept()
                        except OSError:
                            continue
                        self._handle_client(conn)

                self.app.update_loop()
        except BaseException:
            traceback.print_exc()
        finally:
            self.stop()

    # ---------------------- shutdown ----------------------

    def stop(self):
        """Idempotent cleanup. Safe to call from signals and atexit."""
        if self._stopped:
            return
        self._stopped = True

        print("Stopping Librarium daemon...", flush=True)

        try:
            self.app.stop()
        except Exception as e:
            print(f"[daemon] app.stop failed: {e}", flush=True)

        if self.server:
            try:
                self.server.close()
            except Exception:
                pass
            self.server = None

        try:
            self.sock_path.unlink()
        except FileNotFoundError:
            pass

        removed = browser_patcher.restore()
        if removed:
            print(f"[daemon] browser restored: {', '.join(removed)}", flush=True)
            print(
                "[daemon] note: a browser that is already running keeps its "
                "debug port open until it is fully quit.",
                flush=True,
            )
