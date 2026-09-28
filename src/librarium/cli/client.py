# src/librarium/cli/client.py
"""
Thin CLI client. Connects to the daemon socket, sends one command,
prints the response and exits. This is what the shell invokes.
"""
import socket
import sys

from librarium.cli.parser import socket_path


def send_command(command: str) -> int:
    path = socket_path()
    if not path.exists():
        print("Librarium daemon is not running.", file=sys.stderr)
        return 1

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(3.0)
            s.connect(str(path))
            s.sendall(command.encode("utf-8"))
            s.shutdown(socket.SHUT_WR)

            chunks = []
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    response = b"".join(chunks).decode("utf-8", errors="replace")
    if response:
        print(response)
    return 0