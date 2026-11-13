"""Launch preflight and failure diagnostics for the navigation tool (Windows; standard library only today, adding dependencies is fine: pin them in scripts/requirements.txt, see CLAUDE.md).

Purpose: say why the game cannot be driven, in one place.
  - config_problems(text): what is unsafe about a game config (fullscreen, no adapter id, a mode index that was never chosen, data paths that are
    not relative to the install). Pure, so it is unit tested.
  - session_problem(): the process runs in a Windows session that is not the active console session (another user is signed in on the screen):
    the screen cannot be captured and the game cannot create its display, so it starts GTR2Config instead (seen 2026-11-11).
  - describe_windows(game_hwnd): the foreground window (title, process), the game window's state (visible, minimised, hung, rectangles).
Usage (through gtr2-nav.py):   preflight       checks before a launch, exit 1 if any fail
                               diagnose        what the screen and windows look like now (also printed when `ready` fails)
"""
import ctypes
import re
import subprocess
from ctypes import wintypes


def tools_root():
    """The folder that holds scripts/ (this repository)."""
    from pathlib import Path
    return Path(__file__).resolve().parents[2]


def profile_name(root=None):
    """The player profile to use: GTR2_PROFILE if set, else the newest UserData/<name>/<name>.PLR (the game's placeholder
    PlayerNameNeverUsed only when it is the only one), else the placeholder name."""
    import os
    if os.environ.get("GTR2_PROFILE") or tools_config().get("profile"):
        return os.environ.get("GTR2_PROFILE") or tools_config()["profile"]
    ud = (root or game_root()) / "UserData"
    found = sorted((d for d in ud.glob("*") if d.is_dir() and (d / (d.name + ".PLR")).is_file()),
                   key=lambda d: (d.name != "PlayerNameNeverUsed", (d / (d.name + ".PLR")).stat().st_mtime)) if ud.is_dir() else []
    return found[-1].name if found else "PlayerNameNeverUsed"


def plr_path(root=None):
    """UserData/<profile>/<profile>.PLR under the game folder."""
    root = root or game_root()
    name = profile_name(root)
    return root / "UserData" / name / (name + ".PLR")


def tools_config():
    """The settings written by scripts/gtr2-setup.py (gtr2-tools.json in the repository root), or {}."""
    import json
    try:
        return json.loads((tools_root() / "gtr2-tools.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def game_root():
    """The game folder: GTR2_ROOT if set, else game_root in gtr2-tools.json, else the parent of scripts/ (tools placed inside the install)."""
    import os
    from pathlib import Path
    return Path(os.environ.get("GTR2_ROOT") or tools_config().get("game_root") or Path(__file__).resolve().parents[2])

user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
kernel32.WTSGetActiveConsoleSessionId.restype = wintypes.DWORD
PROCESS_QUERY_LIMITED = 0x1000


def parse_config(text):
    """KEY=VALUE pairs of a game config (the file has a NUL-byte header and [SECTIONS], which are ignored)."""
    return dict(re.findall(r"^([A-Z0-9_]+)=([^\r\n]*)", text.replace("\x00", ""), re.M))


def config_problems(text):
    """Reasons the game would not open a normal window with this config, or an empty list."""
    c = parse_config(text)
    problems = []
    if c.get("WINDOWEDMODE") != "1":
        problems.append("WINDOWEDMODE is %s, not 1: the game would take the whole display" % c.get("WINDOWEDMODE", "missing"))
    if not c.get("VIDEOGUID"):
        problems.append("VIDEOGUID is empty: no graphics adapter is chosen (the game writes a fullscreen default and exits)")
    if c.get("VIDEOMODE") in (None, "", "0"):
        problems.append("VIDEOMODE is %s: no video mode was chosen" % (c.get("VIDEOMODE") or "missing"))
    for key in ("LOGDIR", "REPLAYDIR", "TIMETRIALDIR", "DRIVINGSCHOOLDIR"):
        v = c.get(key, "")
        if not v or re.match(r"^[A-Za-z]:|^\\\\", v):
            problems.append("%s=%s is not relative to the install: data would land outside this folder" % (key, v or "missing"))
    return problems


def console_session():
    """(this process's session id, the active console session id)."""
    sid = wintypes.DWORD()
    kernel32.ProcessIdToSessionId(kernel32.GetCurrentProcessId(), ctypes.byref(sid))
    return sid.value, kernel32.WTSGetActiveConsoleSessionId()


def session_problem():
    mine, console = console_session()
    if console in (0xFFFFFFFF,):
        return None            # no console session reported (a remote desktop session): nothing to compare
    if mine != console:
        return ("this process runs in Windows session %d but the screen shows session %d: another user is signed in on the screen, so the "
                "screen cannot be captured and the game cannot create its display (it would start GTR2Config instead)" % (mine, console))
    return None


def running(image):
    """PIDs of running processes with this image name (tasklist)."""
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + image, "/FO", "CSV", "/NH"], capture_output=True, text=True,
                         creationflags=0x08000000).stdout
    return [int(m.group(1)) for m in re.finditer(r'^"[^"]*","(\d+)"', out, re.M)]


def _title(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def _process_of(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    name = "?"
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid.value)
    if h:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            name = buf.value.rsplit("\\", 1)[-1]
        kernel32.CloseHandle(h)
    return pid.value, name


def pid_of(hwnd):
    """The process id that owns a window."""
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def cpu_seconds(pid):
    """User + kernel CPU seconds a process has used so far (None when it cannot be opened)."""
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = wintypes.HANDLE
    handle = k32.OpenProcess(0x1000, False, pid)    # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        times = [wintypes.FILETIME() for _ in range(4)]    # creation, exit, kernel, user
        if not k32.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
            return None
        return sum(((t.dwHighDateTime << 32) | t.dwLowDateTime) / 1e7 for t in times[2:])
    finally:
        k32.CloseHandle(handle)


def sample_busy_threads(pid, seconds=0.5, samples=6):
    """Which of a (32-bit) process's threads use the CPU, and in which module they are executing: measures every thread's CPU time over
    `seconds`, then takes `samples` instruction-pointer readings of the busiest one (each suspends it for a moment). Returns one line, e.g.
    'busiest thread 1234 used 0.49 s of 0.50 s; executing in GTR2.exe x4, nvwgf2um.dll x2'. Never raises: a failure is part of the line."""
    import struct
    import time
    k32 = ctypes.windll.kernel32
    k32.OpenThread.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE

    class ThreadEntry(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("tid", wintypes.DWORD), ("owner", wintypes.DWORD),
                    ("base", wintypes.LONG), ("delta", wintypes.LONG), ("flags", wintypes.DWORD)]

    class ModuleEntry(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("id", wintypes.DWORD), ("pid", wintypes.DWORD), ("glob", wintypes.DWORD), ("proc", wintypes.DWORD),
                    ("base", ctypes.c_void_p), ("length", wintypes.DWORD), ("handle", ctypes.c_void_p), ("name", ctypes.c_wchar * 256),
                    ("path", ctypes.c_wchar * 260)]

    def ticks(handle):
        t = [wintypes.FILETIME() for _ in range(4)]
        if not k32.GetThreadTimes(handle, *[ctypes.byref(x) for x in t]):
            return None
        return sum(((x.dwHighDateTime << 32) | x.dwLowDateTime) / 1e7 for x in t[2:])

    handles = {}
    try:
        snap = k32.CreateToolhelp32Snapshot(0x4, 0)      # TH32CS_SNAPTHREAD
        entry = ThreadEntry()
        entry.size = ctypes.sizeof(ThreadEntry)
        ok = k32.Thread32First(snap, ctypes.byref(entry))
        while ok:
            if entry.owner == pid:
                h = k32.OpenThread(0x0800 | 0x0002 | 0x0008, False, entry.tid)    # QUERY_LIMITED | SUSPEND_RESUME | GET_CONTEXT
                if h:
                    handles[entry.tid] = h
            ok = k32.Thread32Next(snap, ctypes.byref(entry))
        k32.CloseHandle(snap)
        if not handles:
            return "no threads could be opened"
        before = {tid: ticks(h) for tid, h in handles.items()}
        time.sleep(seconds)
        used = {tid: (ticks(h) or 0) - (before[tid] or 0) for tid, h in handles.items()}
        top = sorted(used, key=used.get, reverse=True)
        busiest = top[0]
        modules = []
        snap = k32.CreateToolhelp32Snapshot(0x8 | 0x10, pid)      # TH32CS_SNAPMODULE | SNAPMODULE32
        me = ModuleEntry()
        me.size = ctypes.sizeof(ModuleEntry)
        ok = k32.Module32FirstW(snap, ctypes.byref(me))
        while ok:
            modules.append((me.base or 0, me.length, me.name))
            ok = k32.Module32NextW(snap, ctypes.byref(me))
        k32.CloseHandle(snap)
        seen = {}
        for _ in range(samples):
            buf = ctypes.create_string_buffer(716)          # WOW64_CONTEXT
            struct.pack_into("<I", buf, 0, 0x00010001)      # CONTEXT_i386 | CONTEXT_CONTROL
            h = handles[busiest]
            if k32.SuspendThread(h) == 0xFFFFFFFF:
                continue
            got = k32.Wow64GetThreadContext(h, buf)
            k32.ResumeThread(h)
            if got:
                eip = struct.unpack_from("<I", buf, 184)[0]
                name = next((n for b, ln, n in modules if b <= eip < b + ln), "unknown (%#x)" % eip)
                seen[name] = seen.get(name, 0) + 1
            time.sleep(0.03)
        where = ", ".join("%s x%d" % kv for kv in sorted(seen.items(), key=lambda kv: -kv[1])) or "no reading"
        others = ", ".join("%d %.2f s" % (t, used[t]) for t in top[1:3] if used[t] > 0.02)
        return "busiest thread %d used %.2f s of %.2f s%s; executing in %s" % (busiest, used[busiest], seconds, ("; next: " + others) if others else "", where)
    except Exception as e:      # evidence gathering must never break the run
        return "thread sampling failed: %s" % e
    finally:
        for h in handles.values():
            k32.CloseHandle(h)


def blank_window_note(game_hwnd, seconds, cpu_before):
    """One line explaining a window that stays blank: is the game busy (CPU used while blank) or idle, does it answer window messages,
    who has the focus, how full is memory. Written to gtr2_ui/runs/blank_window.log by the navigator, so a rare fault leaves evidence."""
    cpu_now = cpu_seconds(pid_of(game_hwnd))
    busy = "CPU use unknown" if cpu_now is None or cpu_before is None else \
        "GTR2 used %.2f s of CPU in %.1f s (%s)" % (cpu_now - cpu_before, seconds, "busy" if cpu_now - cpu_before > 0.3 * seconds else "idle")
    result = wintypes.DWORD(0)
    answers = bool(user32.SendMessageTimeoutW(game_hwnd, 0, 0, 0, 2, 500, ctypes.byref(result)))    # WM_NULL, SMTO_ABORTIFHUNG
    fg = user32.GetForegroundWindow()
    class MemStatus(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD)] + [(n, ctypes.c_uint64) for n in
                    ("total", "free", "pagetotal", "pagefree", "virttotal", "virtfree", "ext")]
    mem = MemStatus()
    mem.length = ctypes.sizeof(MemStatus)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
    return "blank for %.1f s; %s; answers window messages: %s; focus on %r; memory in use %d%%; hung=%s; %s" % (
        seconds, busy, "yes" if answers else "NO", _title(fg) if fg else "nothing", mem.load, bool(user32.IsHungAppWindow(game_hwnd)),
        sample_busy_threads(pid_of(game_hwnd)))


def describe_windows(game_hwnd=None):
    """Lines describing the foreground window and the game window."""
    lines = []
    fg = user32.GetForegroundWindow()
    if fg:
        pid, name = _process_of(fg)
        lines.append("foreground: %r of %s (pid %d)" % (_title(fg), name, pid))
    else:
        lines.append("foreground: none (the screen may be locked or another session's)")
    game = game_hwnd or user32.FindWindowW(None, "GTR2")
    if not game:
        lines.append("game window: not found")
        return lines
    rect, client = wintypes.RECT(), wintypes.RECT()
    user32.GetWindowRect(game, ctypes.byref(rect))
    user32.GetClientRect(game, ctypes.byref(client))
    lines.append("game window: visible=%s minimised=%s hung=%s outer=(%d,%d)-(%d,%d) client=%dx%d foreground=%s" % (
        bool(user32.IsWindowVisible(game)), bool(user32.IsIconic(game)), bool(user32.IsHungAppWindow(game)),
        rect.left, rect.top, rect.right, rect.bottom, client.right, client.bottom, fg == game))
    return lines
