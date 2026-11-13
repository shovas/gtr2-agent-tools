"""Thin client for the gtr2-nav.py server (standard library only so each command starts fast: about 0.2 to 0.4 s through the server against about 0.6 s when the command itself imports numpy; not a requirement. A startup under 1 s is acceptable, so this client and the server could be dropped; what must stay accurate are the in-game timings the navigator measures, not its own start-up).

gtr2-nav.py imports numpy, Pillow and mss and decodes the page references: about 0.6 s of start-up that every command used to pay.
The first command starts `gtr2-nav.py serve` (a hidden background process); later commands send their arguments to it over a
localhost socket and print what it prints, with the same exit code. The server holds the imports, the decoded references and the
screen grabber, restarts itself when any script changes, and exits after 20 minutes without a command.

Safety: it listens on 127.0.0.1 only and every request must carry a random token kept in scripts/gtr2_ui/runs/nav_token.txt, so a web
page or another user's process can't send it commands. Set GTR2_NAV_DIRECT=1 to run a command in-process without the server.
"""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = 47621
TOKEN_FILE = HERE / "runs" / "nav_token.txt"
DIRECT_ONLY = {"serve", "watch"}       # watch blocks for minutes; serve is the server itself
END = b"\x00EXIT:"


def version():
    """Changes whenever a script of the tool changes, so a stale server is replaced."""
    files = [HERE.parent / "gtr2-nav.py"] + sorted(HERE.glob("*.py"))
    sig = ";".join("%s:%d" % (f.name, f.stat().st_mtime_ns) for f in files)
    cfg = HERE.parent.parent / "gtr2-tools.json"          # the game folder / profile are read once at start-up: a change must replace the server too
    try:
        extra = cfg.read_text(encoding="utf-8")
    except OSError:
        extra = ""
    return sig + "|root=%s|profile=%s|cfg=%s" % (os.environ.get("GTR2_ROOT", ""), os.environ.get("GTR2_PROFILE", ""), extra)


def _connect(timeout=0.2):
    s = socket.socket()
    s.settimeout(timeout)
    s.connect(("127.0.0.1", PORT))
    return s


def _start_server(script):
    flags = 0x00000200 | 0x08000000                       # NEW_PROCESS_GROUP | NO_WINDOW (not DETACHED: that makes python.exe open its own console)
    env = dict(os.environ, GTR2_NAV_DIRECT="1")
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")            # python.exe would open a console window on top of the game
    subprocess.Popen([str(windowless if windowless.exists() else exe), "-I", str(script), "serve"], creationflags=flags, env=env,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            _connect().close()
            return True
        except OSError:
            time.sleep(0.05)
    return False


def _talk(argv, stop=False):
    try:
        token = TOKEN_FILE.read_text().strip()
    except OSError:
        return None
    try:
        s = _connect()
    except OSError:
        return None
    s.settimeout(None)
    s.sendall((json.dumps({"token": token, "argv": argv, "version": version(), "stop": stop}) + "\n").encode())
    buf = b""
    out = sys.stdout.buffer
    while True:
        chunk = s.recv(65536)
        if not chunk:
            # the server went away after it was sent a command: never run the command again (it may have pressed buttons)
            sys.stdout.flush()
            print("nav server closed the connection mid-command; the command was NOT repeated", file=sys.stderr)
            return 3
        buf += chunk
        if END in buf:
            body, _, tail = buf.partition(END)
            out.write(body)
            out.flush()
            code = tail.split(b"\n")[0]
            return code.decode() if code in (b"RESTART",) else int(code)
        # keep a small tail in case the marker is split across chunks
        keep = len(END) - 1
        out.write(buf[:-keep])
        out.flush()
        buf = buf[-keep:]


def forward(argv, script):
    """Run the command in the server and exit with its code. Returns (so the caller runs it in-process) if the server can't be used."""
    if os.environ.get("GTR2_NAV_DIRECT") == "1" or not argv or argv[0] in DIRECT_ONLY:
        return
    if argv[0] == "stop":
        r = _talk([], stop=True)
        print("server stopped" if r is not None else "no server running")
        sys.exit(0)
    for attempt in range(3):
        code = _talk(argv)
        if code == "RESTART":                       # the scripts changed: the old server shut itself down
            time.sleep(0.3)
            code = None
        if isinstance(code, int):
            sys.exit(code)
        if not _start_server(script):
            return
