"""One window per site: a Unix socket per site in $XDG_RUNTIME_DIR/sitewrap/<id>.sock.

The running window listens on it (QLocalServer); a second `webapp <id>` (or the dashboard) connects and
sends "raise" instead of opening a duplicate. "ping" just answers "pong" (running indicator).
Pure-Python client side, so the dashboard never needs QtWebEngine.
"""
from __future__ import annotations

import os
import socket
from pathlib import Path


def runtime_dir() -> Path:
    env = os.environ.get("SITEWRAP_RUNTIME")
    d = Path(env) if env else Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/sitewrap-{os.getuid()}") / "sitewrap"
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    return d


def socket_path(site_id: str) -> Path:
    return runtime_dir() / f"{site_id}.sock"


def send(site_id: str, msg: str = "ping", timeout: float = 0.5) -> str:
    """Send a command to the running instance; '' if none is running (stale sockets count as not running)."""
    p = socket_path(site_id)
    if not p.exists():
        return ""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(p))
            s.sendall(msg.encode() + b"\n")
            return s.recv(64).decode(errors="replace").strip() or "ok"
    except OSError:
        return ""


def is_running(site_id: str) -> bool:
    return send(site_id, "ping") == "pong"


def serve(site_id: str, on_raise, parent=None):
    """Listen for other instances (call after QApplication exists). Returns the QLocalServer or None if
    another live instance already owns the socket."""
    from PySide6.QtNetwork import QLocalServer
    if is_running(site_id):
        return None
    path = str(socket_path(site_id))
    QLocalServer.removeServer(path)                      # stale socket from a crash
    srv = QLocalServer(parent)
    srv.setSocketOptions(QLocalServer.UserAccessOption)
    if not srv.listen(path):
        return None

    def on_conn():
        while srv.hasPendingConnections():
            c = srv.nextPendingConnection()

            def ready(c=c):
                line = bytes(c.readAll()).decode(errors="replace").strip()
                if line == "raise":
                    on_raise(); c.write(b"raised\n")
                else:
                    c.write(b"pong\n")
                c.flush(); c.disconnectFromServer()
            c.readyRead.connect(ready)
    srv.newConnection.connect(on_conn)
    return srv
