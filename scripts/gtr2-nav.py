"""Click GTR2 menus with measured timings and wait for each screen to change and settle, instead of fixed sleeps.

Windows. Needs scripts/.venv (numpy, Pillow, mss; adding dependencies is fine: pin them in scripts/requirements.txt, see CLAUDE.md). Timings are measured values:
hover 30 ms, press 10 ms, release 30 ms (buttons act on release; the mouse must stay on the button for a moment), then
the mouse is parked. A screen change is detected by a 160x90 thumbnail of the game window, polled every 50 ms.

Usage:
  python -I scripts\\gtr2-nav.py click X Y                 # click a client point (1280x720 client), then wait for the screen to settle
  python -I scripts\\gtr2-nav.py click X Y --no-wait        # click only
  python -I scripts\\gtr2-nav.py measure X Y [--runs 5]     # click, time how long until the screen changes and settles
  python -I scripts\\gtr2-nav.py ready                      # wait for the window and the main menu (verified by page recognition)
  python -I scripts\\gtr2-nav.py where                      # which menu page is showing (page recognition, numpy based)
  python -I scripts\\gtr2-nav.py goto PAGE LABEL            # press a button of the menu map; verifies the source and destination pages
  python -I scripts\\gtr2-nav.py path FILE                  # run 'PAGE | LABEL [| EXPECTED]' steps in one process (scripts\\nav_paths)
  python -I scripts\\gtr2-nav.py pause [ROW [--enter]]      # read the pause menu's highlighted row; with ROW step the highlight to it (Enter only with --enter)
  python -I scripts\\gtr2-nav.py watch [--limit S]          # watchdog: stop the game on a display change, the time limit or Ctrl+Alt+End
  python -I scripts\\gtr2-nav.py drag X1 Y1 X2 Y2           # drag between two UI points (800x600 canvas units) with the button held
  python -I scripts\\gtr2-nav.py slider PAGE N left|right  # drag the Nth slider (0 = first) of an Options page to an end; needs that page showing
  python -I scripts\\gtr2-nav.py row circuit|model|class N  # click a list row (circuit names, first car, class radio)
  python -I scripts\\gtr2-nav.py scroll circuit|class down|up [N]   # press a list's scrollbar arrow N times
  python -I scripts\\gtr2-nav.py exit                       # close the game through EXIT and its confirm tick (from the main menu)
Client coordinates: origin is the top-left inside the GTR2 window (the window must be in front).
"""
import argparse
import ctypes
import hashlib
import json
import re
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "gtr2_ui"))
if __name__ == "__main__":
    # Every command is forwarded to a background server that already holds numpy, the decoded page references and the screen
    # grabber (about 0.6 s of start-up saved per command). Falls back to running here if the server can't be used.
    import nav_client
    nav_client.forward(sys.argv[1:], Path(__file__).resolve())
import menumap  # noqa: E402
import mss  # noqa: E402  (needs scripts/.venv: numpy, Pillow, mss; see scripts/requirements.txt)
import numpy as np  # noqa: E402
import pagerec  # noqa: E402
from paths import LOCAL_BASELINES  # noqa: E402
import diag  # noqa: E402  (preflight and failure diagnostics)
from pausemenu import pause_row_of  # noqa: E402
import coords  # noqa: E402  (measured slider and list positions)

user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
user32.SetProcessDPIAware()

MIN_STEP = 0.03                                # lowest allowed hover/hold/release (seconds)
HOVER, HOLD, RELEASE = 0.03, 0.03, 0.03       # 30 ms each: the minimum the user set; the 10 ms settings missed clicks on tabs
POLL = 0.05                                    # how often the screen is looked at
QUIET = 0.15                                   # the screen must stay the same this long to count as settled
CLIENT = [1280, 720]                           # the game window's client size; read from the window by refresh_client (default: the reference size)
THUMB = (160, 90)                              # thumbnail size used for the change check
PARK = (5, 5)                                  # client point the mouse rests on, away from buttons


GAME = [None]
SCT = []     # one screen grabber, created on first use
ARRIVED = [None]   # the page the last verified step arrived on, so the next step can skip re-checking its source


def ensure_focus(timeout=1.0):
    """Clicks on a window that isn't in front usually only activate it, which looks like a 'first click only hovers'.
    So bring the game forward and wait until it is, before every press (it waits; it never refuses and skips the press)."""
    h = GAME[0]
    if user32.GetForegroundWindow() == h:
        return True
    for attempt in range(3):
        if attempt == 1:
            # Windows refuses SetForegroundWindow to a process that did not get the last input (a taskbar or notification window may hold
            # the foreground): a tap on Alt counts as input from this process, which is the usual way past that
            user32.keybd_event(0x12, 0, 0, 0)
            user32.keybd_event(0x12, 0, 2, 0)
        elif attempt == 2:
            if user32.IsIconic(h):
                user32.ShowWindow(h, 9)
            fg = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
            me = ctypes.windll.kernel32.GetCurrentThreadId()
            user32.AttachThreadInput(me, fg, True)
            user32.SetForegroundWindow(h)
            user32.AttachThreadInput(me, fg, False)
        user32.SetForegroundWindow(h)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if user32.GetForegroundWindow() == h:
                return True
            time.sleep(0.02)
    sys.exit("could not bring GTR2 to the front (foreground is another window); click refused")


def refresh_client(h):
    """Read the window's client size (the game runs windowed at whatever size setup chose). Page recognition shrinks every capture to
    800x450 and the UI is an 800x600 canvas stretched over the client, so any 16:9 or 4:3 size works with the one set of references."""
    r = wintypes.RECT()
    if user32.GetClientRect(h, ctypes.byref(r)) and r.right > 0 and r.bottom > 0:
        CLIENT[0], CLIENT[1] = r.right, r.bottom
        pagerec.SCORE_SLACK[0] = 1.0 if (r.right, r.bottom) == (1280, 720) else 2.0


def window_origin():
    h = user32.FindWindowW(None, "GTR2")
    if not h:
        sys.exit("GTR2 window not found (is the game running?)")
    GAME[0] = h
    refresh_client(h)
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(h, ctypes.byref(pt))
    return pt.x, pt.y, h


POPUP_REPEAT_AFTER = 8.0     # a popup tick that seems to have done nothing is repeated once, no earlier than this


def game_responsive(ox, oy, probes=3, timeout_ms=300):
    """True if the game's message loop answers every one of `probes` WM_NULL messages within timeout_ms (it is busy, not just
    slow to redraw, while it unloads a track). Used before repeating a popup tick."""
    user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
    out = ctypes.c_size_t(0)
    for _ in range(probes):
        r = user32.SendMessageTimeoutW(GAME[0], 0, 0, 0, 0x0002, timeout_ms, ctypes.byref(out))   # SMTO_ABORTIFHUNG
        if not r:
            return False
        time.sleep(0.2)
    return True


def move_to(ox, oy, x, y):
    user32.SetCursorPos(ox + x, oy + y)


def mouse(flag):
    user32.mouse_event(flag, 0, 0, 0, 0)


def press(ox, oy, x, y, hover=HOVER, hold=HOLD, release=RELEASE):
    """Move, hover, press, hold, release, release-delay, then park the mouse. No step is shorter than MIN_STEP."""
    hover, hold, release = max(hover, MIN_STEP), max(hold, MIN_STEP), max(release, MIN_STEP)
    ensure_focus()
    move_to(ox, oy, x, y)
    time.sleep(hover)
    mouse(0x0002)          # LEFTDOWN
    time.sleep(hold)
    mouse(0x0004)          # LEFTUP
    time.sleep(release)
    move_to(ox, oy, *PARK)


def heading_hash(ox, oy, region=(478, 166, 137, 18)):
    """Hash of a client-area region (default: the selected level's heading text, which changes only when a level is clicked)."""
    rx, ry, w, h = region
    x0, y0 = ox + rx, oy + ry
    sdc = user32.GetDC(0)
    mdc = gdi32.CreateCompatibleDC(sdc)
    bmp = gdi32.CreateCompatibleBitmap(sdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    gdi32.BitBlt(mdc, 0, 0, w, h, sdc, x0, y0, 0x00CC0020)
    bi = (ctypes.c_uint32 * 10)(40, w, ctypes.c_uint32(-h & 0xFFFFFFFF).value, (32 << 16) | 1, 0, 0, 0, 0, 0, 0)
    buf = (ctypes.c_ubyte * (w * h * 4))()
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, bi, 0)
    gdi32.SelectObject(mdc, old); gdi32.DeleteObject(bmp); gdi32.DeleteDC(mdc); user32.ReleaseDC(0, sdc)
    return hashlib.md5(bytes(buf)).hexdigest()


def sweep(ox, oy, points, n=20, region=(478, 166, 137, 18)):
    """Alternate clicks between two rows (each click should change the screen) for each timing set; report how many changed it.
    The screen check is the thumbnail, so a hover-only change would be counted too; the rows' text changes only on a click."""
    sets = [("old 0.4/0.15/0", 0.40, 0.15, 0.0), ("current 0.03/0.01/0.03", 0.03, 0.01, 0.03),
            ("0.00/0.01/0.00", 0.0, 0.01, 0.0), ("0.01/0.01/0.01", 0.01, 0.01, 0.01),
            ("0.03/0.01/0.00", 0.03, 0.01, 0.0), ("0.00/0.01/0.03", 0.0, 0.01, 0.03)]
    # learn the heading text of each row first: click row 0 then row 1, long waits
    press(ox, oy, *points[0]); time.sleep(1.0); h0 = heading_hash(ox, oy, region)
    press(ox, oy, *points[1]); time.sleep(1.0); h1 = heading_hash(ox, oy, region)
    if h0 == h1:
        sys.exit("the two rows show the same heading text; pick two different levels")
    expected = [h0, h1]
    for name, hv, hd, rl in sets:
        ok, t_total = 0, 0.0
        for i in range(n):
            k = i % 2
            x, y = points[k]
            before = thumbnail(ox, oy, *CLIENT)
            t0 = time.time()
            press(ox, oy, x, y, hv, hd, rl)
            ch, st = wait_change_then_settle(ox, oy, before, timeout=3.0)
            t_total += time.time() - t0
            # registered = the heading shows the row that was clicked (not just a hover highlight)
            if heading_hash(ox, oy, region) == expected[k]:
                ok += 1
        print("%-24s registered %2d/%d   mean %.2f s per click" % (name, ok, n, t_total / n))


def capture(ox, oy, w=None, h=None):
    """The game window's client area scaled to THUMB (160x90), as top-down 32-bit BGRA bytes."""
    w, h = w or CLIENT[0], h or CLIENT[1]
    tw, th = THUMB
    sdc = user32.GetDC(0)
    mdc = gdi32.CreateCompatibleDC(sdc)
    bmp = gdi32.CreateCompatibleBitmap(sdc, tw, th)
    old = gdi32.SelectObject(mdc, bmp)
    gdi32.SetStretchBltMode(mdc, 4)   # HALFTONE
    gdi32.StretchBlt(mdc, 0, 0, tw, th, sdc, ox, oy, w, h, 0x00CC0020)   # SRCCOPY
    bi = (ctypes.c_uint32 * 10)(40, tw, ctypes.c_uint32(-th & 0xFFFFFFFF).value, (32 << 16) | 1, 0, 0, 0, 0, 0, 0)
    buf = (ctypes.c_ubyte * (tw * th * 4))()
    gdi32.GetDIBits(mdc, bmp, 0, th, buf, bi, 0)
    gdi32.SelectObject(mdc, old); gdi32.DeleteObject(bmp); gdi32.DeleteDC(mdc); user32.ReleaseDC(0, sdc)
    return bytes(buf)


def thumbnail(ox, oy, w, h):
    """Hash of the game window scaled to THUMB, so a changed page shows up cheaply."""
    buf = capture(ox, oy, w, h)
    # rows are top-down; skip the main menu's animated photo band (client y 75-165) so it can't keep
    # a screen from ever settling
    row = THUMB[0] * 4
    rows = [buf[r * row:(r + 1) * row] for r in range(THUMB[1]) if not (9 <= r <= 21)]
    return hashlib.md5(b"".join(rows)).hexdigest()


def look(ox, oy):
    """The game's client area as pagerec's 800x450 comparison picture."""
    if not SCT:
        SCT.append(mss.MSS())
    g = SCT[0].grab({"left": ox, "top": oy, "width": CLIENT[0], "height": CLIENT[1]})
    return pagerec.shrink(np.frombuffer(g.rgb, dtype=np.uint8).reshape(g.height, g.width, 3).astype(np.int16))


def has_ref(page):
    return page in pagerec.cached_references()


def recognize_now(ox, oy):
    return pagerec.recognize_fast(look(ox, oy), pagerec.cached_references())


def wait_for_page(ox, oy, pages_wanted, timeout=3.0, need=2):
    """Wait until one of the pages shows on `need` looks in a row. Returns seconds or None."""
    t0, hits = time.time(), 0
    while time.time() - t0 < timeout:
        cap = look(ox, oy)
        hits = hits + 1 if any(pagerec.is_page(cap, p) for p in pages_wanted) else 0
        if hits >= need:
            return time.time() - t0
        time.sleep(0.02)
    return None


def wait_change_then_settle(ox, oy, before, timeout=10.0):
    """Wait until the screen differs from `before`, then until it has been unchanged for QUIET seconds.
    Returns (seconds to first change, seconds to settle) or (None, None) on timeout."""
    w, h = CLIENT
    t0 = time.time()
    changed = None
    while time.time() - t0 < timeout:
        cur = thumbnail(ox, oy, w, h)
        if changed is None and cur != before:
            changed = time.time() - t0
            last, since = cur, time.time()
        elif changed is not None:
            if cur != last:
                last, since = cur, time.time()
            elif time.time() - since >= QUIET:
                return changed, time.time() - t0
        time.sleep(POLL)
    return (changed, None)


HOST_OK = [False]        # set by --host-step: only the games list's HOST -> SUMMARY_MPCLIENT (opens the setup pages; hosts nothing)
LAN_OK = [False]         # set by --lan-step: the local multiplayer pages in coords.LAN_PAGES (never host, join, refresh or add a server)
POPUP_OK = [False]       # set by --popup-step: opens save/delete/rename/load/exit popups (coords.POPUP_PAGES); a path may only cancel them
SEASON_OK = [False]      # set by --season-step: also unlocks the championship season kinds (menumap.SEASON_STEP_TYPES)
SESSION_OK = [False]     # set by --session-step: unlocks only loading a track and leaving it (menumap.session_step_ok)
DRIVE_OK = [False]       # set by --drive-step: the post-race CONTINUE in a path, and the "!RACE" / "!NEXTSESSION" steps (see special_step)
# The only DRIVE_STEP_TYPES kind an ordinary path step may press. DRIVE itself and NEXT SESSION are pressed only by the "!" steps, which
# check the screen and drive the race; a plain `MONITOR_SINGLE | DRIVE` line stays refused even with --drive-step.
PATH_DRIVE_TYPES = {"APP_BUTTON_POSTRACENAVIGATION"}
SETTING_OK = [False]     # set by --setting-step: the "!CONTROLS" step, which clicks every checkbox and spinner of a settings page
LOAD_TIMEOUT = 30.0      # loading a track takes 3 to 7 s here; wait up to 30 s before calling it a failure


def wait_session_loaded(ox, oy, before_thumb, timeout=LOAD_TIMEOUT, source=None, again=None):
    """After pressing a load button: wait until the screen has changed and then shows a lit, still page (the static top and bottom bars unchanged 0.5 s apart, twice in a row). Returns seconds or None."""
    t0, hits = time.time(), 0
    while time.time() - t0 < timeout:
        if thumbnail(ox, oy, *CLIENT) == before_thumb:
            time.sleep(POLL)
            continue
        if source and has_ref(source) and pagerec.is_page(look(ox, oy), source):
            # still the page that was pressed on: a load shows another screen. After 3 s press once more (a first click that
            # only hovered did nothing, so a repeat can't start it twice).
            hits = 0
            if again and time.time() - t0 >= 3.0 and not again[0]:
                again[0] = True
                again[1]()
            elif time.time() - t0 > 12.0:
                return None
            time.sleep(POLL)
            continue
        a = grab_client(ox, oy).astype(np.int16)
        time.sleep(0.5)
        b = grab_client(ox, oy).astype(np.int16)
        bands = (slice(0, CLIENT[1] // 8), slice(CLIENT[1] * 4 // 5, CLIENT[1]))
        still = all(float(np.abs(a[r] - b[r]).mean()) < 1.0 for r in bands)
        hits = hits + 1 if (still and float(b.mean()) > 20) else 0
        if hits >= 2:
            return time.time() - t0
    return None


ARRIVE_TIMEOUT = 5.0     # how long a verified page may take to show before the step fails
PRESS_AGAIN_AFTER = 1.0  # a press that did nothing is repeated once after this long, only while the source page still shows



def net_risk(name):
    """True for a page the menu map marks as multiplayer or an online service (not the other kinds of risky page, like the race monitor)."""
    return menumap.page_risk(name) in ("multiplayer", "online service or account")


def lan_problem(b, map_page, want):
    """Why a press touching a multiplayer or online page is refused, or None. Hosting, joining, refreshing the list and adding a server
    are refused outright (even with --lan-step); other presses on those pages need --lan-step and the pages must be in coords.LAN_PAGES."""
    names = [map_page] + [w for w in want if w]
    risky = [n for n in names if net_risk(n)]
    if not risky:
        return None
    kind, cap = getattr(b, "kind", ""), getattr(b, "caption", "").upper()
    if HOST_OK[0] and LAN_OK[0] and map_page == "SUMMARY_MPLIST" and cap == "HOST" and list(want) == ["SUMMARY_MPCLIENT"] \
            and kind not in ("APP_MP_TRACKLOCKEDBUTTON",):
        return None      # the one allowed HOST: it only opens the setup pages
    if kind in coords.LAN_NEVER_KINDS or cap in coords.LAN_NEVER_CAPTIONS:
        return "%s on a multiplayer page hosts, joins, refreshes or adds a server: never pressed by a path" % (cap or kind)
    if not LAN_OK[0]:
        return "%s is a multiplayer or online page: needs --lan-step" % risky[0]
    outside = [n for n in risky if n not in coords.LAN_PAGES]
    if outside:
        return "%s is not one of the local multiplayer pages (coords.LAN_PAGES)" % outside[0]
    return None


def step_policy(b, map_page, want):
    """Whether a path step may press button `b` of menu-map page `map_page` that leads to the pages `want`.
    Returns (problem, unlocked, popup): `problem` is why it is refused (None if allowed), `unlocked` is True when an opt-in flag
    lets a blocked kind through (a session or season step), `popup` is True for a press that only opens a popup."""
    unlocked = bool((SESSION_OK[0] and menumap.session_step_ok(b, map_page)) or (SEASON_OK[0] and b.kind in menumap.SEASON_STEP_TYPES)
                    or (DRIVE_OK[0] and b.kind in PATH_DRIVE_TYPES))
    popup = bool(POPUP_OK[0] and want and all(w in coords.POPUP_PAGES for w in want))
    lan = lan_problem(b, map_page, want)
    if lan:
        return lan, unlocked, popup
    problem = (None if (unlocked or popup) else menumap.never_press(b)) or (
        "EXIT is done from the menu by hand" if "EXIT" in b.label.upper() and not popup else None)
    return problem, unlocked, popup


def position_policy(pages, map_page, spot, want):
    """The rules for a path step given as a canvas position. A position that lands on a mapped button gets that button's rules (the
    the button's own rules), so a path can't reach a blocked button, such as a popup's confirm tick or a season start, by its
    coordinates; a position on nothing mapped (a list row) is allowed. Returns (problem, unlocked, popup, kind of the button there)."""
    near = [nb for nb in pages[map_page].buttons if nb.center and abs(nb.center[0] - spot[0]) <= 1 and abs(nb.center[1] - spot[1]) <= 1]         if map_page in pages else []
    unlocked = popup = False
    if map_page in coords.ACK_POPUPS:
        near = []              # the tick of a notice with nothing left to decide (coords.ACK_POPUPS): "Game Saved", the empty LAN lobby's exit
    for nb in near:
        problem, nb_unlocked, nb_popup = step_policy(nb, map_page, want)
        if problem:
            return "%s: %s" % (nb.label, problem), False, False, ""
        unlocked, popup = unlocked or nb_unlocked, popup or nb_popup
    return None, unlocked, popup, near[0].kind if near else ""


def goto_one(ox, oy, pages, page, label, expect=None, verify=True, on_page=False):
    """Press one button of the menu map and wait until the page it leads to is on screen. Returns (ok, message).

    Before pressing, the screen must show `page` (when it has a saved reference), so a path can't run on from the wrong place.
    The destination is the button's target in the menu map, or `expect` (comma separated page names) when given. If a
    destination has no saved reference the step falls back to 'the screen changed and settled'."""
    if label.startswith("!"):
        return special_step(ox, oy, pages, page, label, expect)
    map_page = page
    if "=" in page:
        # "MAPPAGE=REFNAME": the buttons come from the menu-map page, the screen is checked against another reference (a popup
        # drawn over a mode's own page can differ from the map page's reference)
        map_page, page = page.split("=", 1)
    if label.startswith("@") and page in coords.POPUP_PAGES and page not in coords.ACK_POPUPS and float(label[1:].split(",")[0]) > 400:
        return False, "refused: %s is on the confirm side of the popup %s (paths may only cancel popups)" % (label, page)
    if label.startswith("@") and net_risk(map_page) and (not LAN_OK[0] or map_page not in coords.LAN_PAGES):
        return False, "refused: %s on %s (a multiplayer or online page: needs --lan-step and a page in coords.LAN_PAGES)" % (label, map_page)
    if label.startswith("@"):
        # a position in canvas units, "@x,y", for buttons that share a name with others on the page.
        # Needs an expected page: nothing in the map says what it does.
        if not expect:
            return False, "refused: %s needs an expected page (third column)" % label
        session = False
        popup_press = False
        spot = tuple(float(v) for v in label[1:].split(","))
        want = [d.strip() for d in expect.split(",")]
        problem, session, popup_press, kind = position_policy(pages, map_page, spot, want)
        if problem:
            return False, "refused: %s (%s)" % (label, problem)
        b = type("PositionButton", (), {"center": spot, "targets": [], "kind": kind})      # a stand-in for a map button
    else:
        b = menumap.find_button(pages, map_page, label)
        want = [d.strip() for d in expect.split(",")] if expect else [str(t) for t in b.targets]
        problem, session, popup = step_policy(b, map_page, want)
        popup_press = popup
        if problem:
            return False, "refused: %s (%s)" % (label, problem)
    source_known = verify and has_ref(page)
    on_page = on_page or ARRIVED[0] == page
    ARRIVED[0] = None
    if source_known and not on_page and wait_for_page(ox, oy, [page], timeout=2.0, need=1) is None:
        shown = recognize_now(ox, oy)
        return False, "not on %s before pressing %s: the screen shows %s (score %.1f)" % (page, label, shown[0], shown[1])
    dests = [d.strip() for d in expect.split(",")] if expect else sorted(set(map(str, b.targets)))
    dests = [d for d in dests if d and d != "-"]
    verified = [d for d in dests if has_ref(d)] if verify and dests and all(has_ref(d) for d in dests) else []
    if page in dests:        # a button that stays on its own page can't be verified by arrival
        verified = []
    cx, cy = b.center
    # the 800x600 canvas is stretched over the client (1.6 across, 1.2 down at 1280x720); checked against known buttons
    x, y = ui(cx, cy)
    before = thumbnail(ox, oy, *CLIENT)
    t0 = time.time()
    press(ox, oy, x, y)
    names = ", ".join(dests) or "-"
    # only loading a track takes up to a minute; leaving one or starting a season shows its next page in seconds
    slow = getattr(b, "kind", "") == "APP_BUTTON_PLAYREPLAY"      # opening a replay loads its track: 4 to 5 s here, and a second press would reload it
    limit = (LOAD_TIMEOUT if b.kind == "APP_BUTTON_CIRCUITSELECT" else 15.0) if session else (20.0 if slow else ARRIVE_TIMEOUT)
    if session and not verified:
        # loading or leaving a session: never pressed twice; wait for the new page to be lit and still
        took = wait_session_loaded(ox, oy, before, source=page, again=[False, lambda: press(ox, oy, x, y)])
        return took is not None, "%s -> %s at client (%d,%d): session step, %s" % (
            label, names, x, y, "page lit and still after %.1f s (no saved reference: not identified)" % took if took else "NOT loaded within %.0f s" % LOAD_TIMEOUT)
    if verified:
        hits, again = 0, False
        still_since, last_thumb = time.time(), None
        while time.time() - t0 < limit:
            cap = look(ox, oy)
            if session and source_known and time.time() - t0 >= 3.0 and pagerec.is_page(cap, page):
                if page.upper().startswith("CONFIRM") or page in coords.POPUP_PAGES or "BACKTOMAIN" in getattr(b, "kind", "").upper():
                    # A popup tick is repeated only late and only when the game is demonstrably alive: leaving a session freezes the
                    # game for several seconds with the popup still drawn, and a press queued in that freeze lands on the main menu
                    # behind it (its Local Network button sits where the tick is: opened the games list twice).
                    if not again and time.time() - t0 >= POPUP_REPEAT_AFTER and game_responsive(ox, oy) and pagerec.is_page(look(ox, oy), page):
                        again = True
                        press(ox, oy, x, y)
                        t0 = time.time() - 0.5
                        continue
                    if time.time() - t0 < limit:
                        time.sleep(0.05)
                        continue
                    break
                # the source page is still showing 3 s after the press: the press did nothing (a first click that only hovers).
                # Press once more, then give up: nothing was started, so a repeat can't start it twice.
                if not again:
                    again = True
                    press(ox, oy, x, y)
                    t0 = time.time() - 0.5
                    continue
                break
            here = next((d for d in verified if pagerec.is_page(cap, d)), None)
            if here:
                hits += 1
                if hits >= 2:
                    ARRIVED[0] = here
                    return True, "%s -> %s at client (%d,%d): verified after %.2f s%s" % (
                        label, names, x, y, time.time() - t0, " (pressed again)" if again else "")
                continue
            hits = 0
            if not again and not session and not slow and time.time() - t0 >= PRESS_AGAIN_AFTER and source_known and pagerec.is_page(cap, page):
                again = True              # nothing happened (a click on a window that was not ready): press once more
                press(ox, oy, x, y)
            time.sleep(0.03)
        shown = recognize_now(ox, oy)
        return False, "%s -> %s at client (%d,%d): NOT verified after %.1f s; the screen shows %s (score %.1f)" % (
            label, names, x, y, time.time() - t0, shown[0], shown[1])
    ch, st = wait_change_then_settle(ox, oy, before, timeout=1.0)
    if ch is None:
        # nothing happened (a first click can only hover): press once more, while the screen is unchanged; never for
        # buttons that start something (those were refused above)
        press(ox, oy, x, y)
        ch, st = wait_change_then_settle(ox, oy, before, timeout=2.0)
    repeatable = (not session and not popup_press and not page.upper().startswith("CONFIRM") and page not in coords.POPUP_PAGES
                  and "BACKTOMAIN" not in getattr(b, "kind", "").upper())      # never repeat a popup tick: the screen behind it has buttons too
    if ch is not None and has_ref(page) and repeatable and pagerec.is_page(look(ox, oy), page):
        # the screen changed (a hover highlight) but the source page is still showing: the click did not take. Press once more.
        press(ox, oy, x, y)
        ch2, st2 = wait_change_then_settle(ox, oy, thumbnail(ox, oy, *CLIENT), timeout=1.0)
        ch, st = (ch2, st2) if ch2 is not None else (ch, st)
    if ch is None and page in dests and has_ref(page) and pagerec.is_page(look(ox, oy), page):
        # a click that stays on its own page (selecting a list row) changes nothing when the row was already selected
        return True, "%s -> %s at client (%d,%d): same-page click, still on %s" % (label, names, x, y, page)
    ok = ch is not None
    return ok, "%s -> %s at client (%d,%d): changed %s s, settled %s s (destination has no saved reference: change only)" % (
        label, names, x, y, "-" if ch is None else "%.2f" % ch, "-" if st is None else "%.2f" % st)


ROOT = diag.game_root()
PLR = diag.plr_path(ROOT)
SC_ESC, SC_SPACE, SC_K = 0x01, 0x39, 0x25      # hardware scancodes. K is Time Acceleration in this profile
SESSION_LABEL = (700, 114, 100, 20)            # UI units: "PRACTICE I", "QUALIFYING I", "RACE" in the session monitor's top right
RACE_TIMEOUT = 180.0                           # seconds from the pause menu's Autopilot to the results page (3 laps took about 35 s)


def plr_value(key):
    """A `Key="value"` setting from the profile file on disk (the game writes it only on exit, so this is the state it started with)."""
    try:
        text = PLR.read_bytes().decode("latin1")
    except OSError:
        return None
    m = re.search(r'^%s="([^"]*)"' % re.escape(key), text, re.M)
    return m.group(1) if m else None


def ui_region(ox, oy, x, y, w, h):
    """A part of the live window given in UI units (800x600), as an int16 array."""
    (x0, y0), (x1, y1) = ui(x, y), ui(x + w, y + h)
    return grab_client(ox, oy)[y0:y1, x0:x1].astype(np.int16)


def region_moved(ox, oy, before, rect, timeout=1.5, level=3.0):
    """Wait until the UI-unit rectangle differs from `before` (mean absolute change above `level`)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if float(np.abs(ui_region(ox, oy, *rect) - before).mean()) > level:
            return True
        time.sleep(0.1)
    return False


def drag_until_moved(ox, oy, start, to_x, rect, tries=2):
    """Drag a slider thumb from `start` (where it sits at its saved value) to the x position; repeat once if its region did not change
    (the Opponents drag missed once in ten runs). If it still did not change, the thumb may already be at the left end
    from an earlier run in this game process (a repeat run): try once from the left end. Returns "moved", "already at the end" or None."""
    for _ in range(tries):
        before = ui_region(ox, oy, *rect)
        drag(ox, oy, start[0], start[1], to_x, start[1])
        if region_moved(ox, oy, before, rect):
            return "moved"
    before = ui_region(ox, oy, *rect)
    drag(ox, oy, to_x + 2, start[1], to_x - 30, start[1])
    return "already at the end" if not region_moved(ox, oy, before, rect, timeout=1.0) else "moved"


def checkbox_ticked(ox, oy, pos):
    """Whether the checkbox at the UI position is ticked: the tick mark raises the spread of the pixels (std about 60 ticked, 48 not,
    measured on the Race Weekend summary's Friday practice and Saturday qualifying boxes)."""
    return float(ui_region(ox, oy, pos[0] - 15, pos[1] - 15, 30, 30).std()) > 54.0


def step_short_race(ox, oy, page):
    """On the Race Weekend summary: distance and opponents to their minimum (3 laps, car alone), Friday practice and Saturday
    qualifying off (a checkbox is clicked only if the profile on disk, which is what the game started with, has it on)."""
    if wait_for_page(ox, oy, [page], timeout=3.0, need=1) is None:
        return False, "!SHORTRACE: not on %s (screen shows %s)" % (page, recognize_now(ox, oy)[0])
    (dx, dy), (px, py) = coords.GP_DISTANCE, coords.GP_OPPONENTS
    notes = []
    for name, start, y in (("Distance", coords.GP_DISTANCE, dy), ("Opponents", coords.GP_OPPONENTS, py)):
        res = drag_until_moved(ox, oy, start, 470, (440, y - 17, 330, 35))
        if res is None:
            return False, "!SHORTRACE: the %s slider did not move" % name
        notes.append("%s %s" % (name, res))
    for name, pos in (("Friday practice", coords.GP_PRACTICE), ("Saturday qualifying", coords.GP_QUALIFYING)):
        if not checkbox_ticked(ox, oy, pos):
            notes.append("%s already off" % name)
            continue
        rect = (pos[0] - 15, pos[1] - 15, 30, 30)
        before = ui_region(ox, oy, *rect)
        press(ox, oy, *ui(*pos))
        if not region_moved(ox, oy, before, rect, timeout=2.0) or checkbox_ticked(ox, oy, pos):
            return False, "!SHORTRACE: the %s checkbox is still ticked" % name
        notes.append("%s off" % name)
    return True, "!SHORTRACE: " + ", ".join(notes)


def step_short_endurance(ox, oy, page):
    """On the 24 Hour summary: race length down to 24 minutes (eight presses of the spinner's left arrow) and no opponents."""
    if wait_for_page(ox, oy, [page], timeout=3.0, need=1) is None:
        return False, "!SHORTENDURANCE: not on %s (screen shows %s)" % (page, recognize_now(ox, oy)[0])
    lx, ly = coords.ENDURANCE_LENGTH_DOWN
    rect = (300, 225, 400, 30)                       # the race length's value
    for n in range(8):
        before = ui_region(ox, oy, *rect)
        press(ox, oy, *ui(lx, ly))
        if not region_moved(ox, oy, before, rect, timeout=1.5):
            break                                   # at the minimum already (always so on a repeat run in this game process)
    res = drag_until_moved(ox, oy, coords.ENDURANCE_OPPONENTS, 360, (340, coords.ENDURANCE_OPPONENTS[1] - 17, 240, 35))
    if res is None:
        return False, "!SHORTENDURANCE: the Opponents slider did not move"
    return True, "!SHORTENDURANCE: race length stepped down, opponents %s" % res


def step_short_champ(ox, oy, page):
    """On a new season's summary: Opponents and Distance dragged to their left ends (both thumbs start at the right end, x 536; a repeat finds them already at the left end)."""
    if wait_for_page(ox, oy, [page], timeout=3.0, need=1) is None:
        return False, "!SHORTCHAMP: not on %s (screen shows %s)" % (page, recognize_now(ox, oy)[0])
    notes = []
    for name, y in (("Opponents", 243), ("Distance", 283)):
        res = drag_until_moved(ox, oy, (536, y), 380, (380, y - 12, 170, 28))
        if res is None:
            return False, "!SHORTCHAMP: the %s slider did not move" % name
        notes.append("%s %s" % (name, res))
    return True, "!SHORTCHAMP: " + ", ".join(notes)


CONTROL_LOG = Path(__file__).resolve().parent / "gtr2_ui" / "runs" / "controls_clicked.jsonl"


def click_control(ox, oy, control, where, should_change):
    """Click a checkbox or spinner and say whether it changed on screen, waiting 2 s if it should and 0.6 s if not. A click that should
    have changed something but did not is clicked once more (a click soon after a page appears is sometimes lost; repeating is safe
    because nothing happened)."""
    rect = (control.x, control.y, control.w, control.h)
    before = ui_region(ox, oy, *rect)
    press(ox, oy, *ui(*where))
    if region_moved(ox, oy, before, rect, timeout=2.0 if should_change else 0.6, level=1.0):
        return True
    if not should_change:
        return False
    press(ox, oy, *ui(*where))
    return region_moved(ox, oy, before, rect, timeout=2.0, level=1.0)


def step_controls(ox, oy, pages, page):
    """On a settings page (Options Basic, Audio, Advanced or Realism, of the main menu or of a mode): click every checkbox and spinner
    once and check that exactly the controls expected to change (coords.CONTROL_PAGES) changed on screen. Changes the settings of the
    profile, which the game writes when it exits: needs --setting-step, and the suite or gtr2-control-check.py reverts the profile.
    Every control that changed is appended to runs/controls_clicked.jsonl with the profile key it should have saved."""
    if not SETTING_OK[0]:
        return False, "refused: !CONTROLS needs --setting-step"
    expected = coords.control_expectation(page)
    if expected is None or page not in pages:
        return False, "refused: !CONTROLS works only on the Options, Audio, Advanced and Realism pages (coords.CONTROL_PAGES), not on %s" % page
    working, inert = expected
    if wait_for_page(ox, oy, [page], timeout=3.0, need=1) is None:
        return False, "!CONTROLS: not on %s (screen shows %s)" % (page, recognize_now(ox, oy)[0])
    shown, skipped = {}, []
    for control in pages[page].controls:
        try:
            where = menumap.spinner_next(control) if control.attribute_set.startswith("SpinBox") else control.center
        except KeyError:
            skipped.append(control.kind)
            continue
        shown[control.kind] = click_control(ox, oy, control, where, control.kind in working)
    changed = {k for k, v in shown.items() if v}
    CONTROL_LOG.parent.mkdir(exist_ok=True)
    with CONTROL_LOG.open("a", encoding="utf-8") as f:
        for kind in sorted(shown):
            f.write(json.dumps({"page": page, "kind": kind, "key": working.get(kind), "changed": shown[kind], "expected": kind in working}) + "\n")
    missing, extra = sorted(set(working) - changed), sorted(changed - set(working))
    note = "%d controls clicked, %d changed on screen%s" % (len(shown), len(changed), ", %d unmeasured skipped" % len(skipped) if skipped else "")
    # a difference from the expectation is a finding, not a navigation failure: the tour goes on and gtr2-control-check.py reports it
    if missing or extra:
        return True, "!CONTROLS %s: %s; MISMATCH did not change but should: %s; changed but should not: %s" % (page, note, missing or "-", extra or "-")
    return True, "!CONTROLS %s: %s, as expected" % (page, note)


HOVER_LOG = Path(__file__).resolve().parent / "gtr2_ui" / "runs" / "hover_results.jsonl"
HOVER_RESPONSE = 3.0      # mean change inside a button's rectangle that counts as a visible reaction


def step_hover(ox, oy, pages, page):
    """On any page: move the mouse over every mapped button, one after another, without clicking, and note which ones visibly react (their
    picture changes by more than HOVER_RESPONSE). A button that never reacts is greyed out, inert or has no highlight. Read-only: no click,
    no key. Results go to runs/hover_results.jsonl."""
    if page not in pages:
        return False, "!HOVER: %s is not a page of the menu map" % page
    if has_ref(page) and wait_for_page(ox, oy, [page], timeout=3.0, need=1) is None:
        return False, "!HOVER: not on %s (screen shows %s)" % (page, recognize_now(ox, oy)[0])
    seen, tested, silent = set(), 0, []
    HOVER_LOG.parent.mkdir(exist_ok=True)
    with HOVER_LOG.open("a", encoding="utf-8") as log:
        for b in sorted(pages[page].buttons, key=lambda b: (b.y, b.x)):
            c = b.center
            if c is None or not (0 <= c[0] <= 800 and 0 <= c[1] <= 600) or (round(c[0]), round(c[1])) in seen:
                continue
            seen.add((round(c[0]), round(c[1])))
            x0, y0 = max(b.x, 0), max(b.y, 0)
            w, h = min(b.x + b.w, 800) - x0, min(b.y + b.h, 600) - y0
            if w <= 0 or h <= 0:
                continue
            ensure_focus()
            move_to(ox, oy, *PARK)
            time.sleep(0.12)
            before = ui_region(ox, oy, x0, y0, w, h)
            move_to(ox, oy, *ui(*c))
            t0, change = time.time(), 0.0
            while time.time() - t0 < 0.4 and change <= HOVER_RESPONSE:
                time.sleep(0.04)
                change = float(np.abs(ui_region(ox, oy, x0, y0, w, h) - before).mean())
            tested += 1
            reacts = change > HOVER_RESPONSE
            if not reacts:
                silent.append(b.label)
            log.write(json.dumps({"page": page, "label": b.label, "kind": b.kind, "x": round(c[0], 1), "y": round(c[1], 1),
                                   "reacts": reacts, "change": round(change, 1), "targets": [str(x) for x in b.targets]}) + "\n")
    move_to(ox, oy, *PARK)
    return True, "!HOVER %s: %d buttons, %d silent%s" % (page, tested, len(silent), ": " + ", ".join(silent[:8]) if silent else "")


def open_pause_menu(ox, oy, tries=6):
    """Esc until the pause menu shows. Pressed too early it does nothing, so press again only while the menu has not opened (a press
    that opened it is never repeated, so it can't close it again)."""
    for _ in range(tries):
        press_key(SC_ESC)
        t0 = time.time()
        while time.time() - t0 < 1.5:
            if pause_row_now(ox, oy) is not None:
                return True
            time.sleep(0.1)
    return False


def step_race(ox, oy, pages, page, expect):
    """From a race session's monitor: press the race button (DRIVE), give the car to the game's own autopilot from the pause menu,
    switch time acceleration on with K and wait for the results page. Enter is pressed only on the Autopilot row (never Restart,
    Save, Return to Garage or Quit); on a formation lap the menu has no Autopilot row, so it is closed with Continue, SPACE skips
    the lap and the menu is tried again. Needs --drive-step."""
    if not DRIVE_OK[0]:
        return False, "refused: !RACE needs --drive-step"
    dests = [d.strip() for d in (expect or "POST RACE MONITOR").split(",")]
    if not all(has_ref(d) for d in dests):
        return False, "!RACE: no saved reference for %s" % ", ".join(dests)
    if wait_for_page(ox, oy, [page], timeout=3.0, need=1) is None:
        return False, "!RACE: not on %s (screen shows %s)" % (page, recognize_now(ox, oy)[0])
    drive = [b for b in pages[page].buttons if b.kind == "APP_BUTTON_TOREALTIME"]
    if len(drive) != 1:
        return False, "!RACE: %s has %d race buttons" % (page, len(drive))
    x, y = ui(*drive[0].center)
    t0 = time.time()
    before = thumbnail(ox, oy, *CLIENT)
    press(ox, oy, x, y)
    ch, _ = wait_change_then_settle(ox, oy, before, timeout=2.5)
    if ch is None and pagerec.is_page(look(ox, oy), page):
        press(ox, oy, x, y)                         # the first click only hovered: nothing was started, so pressing again is safe
    # wait for the session to load and the page to be left
    while time.time() - t0 < 60 and pagerec.is_page(look(ox, oy), page):
        time.sleep(0.2)
    opened = False
    for attempt in range(4):
        if not open_pause_menu(ox, oy, tries=8 if attempt == 0 else 3):
            continue
        ok, msg = select_pause_row(ox, oy, "Autopilot", enter=True)
        if ok:
            opened = True
            break
        select_pause_row(ox, oy, "Continue", enter=True)        # a menu without Autopilot (formation lap): close it, skip the lap
        time.sleep(0.4)
        press_key(SC_SPACE)
        time.sleep(2.0)
    if not opened:
        return False, "!RACE: the pause menu never offered Autopilot (left in the race; close it by hand)"
    t1 = time.time()
    while pause_row_now(ox, oy) is not None and time.time() - t1 < 3:
        time.sleep(0.1)
    press_key(SC_K)
    limit = RACE_TIMEOUT * (1.7 if any("ENDURANCE" in d for d in dests) else 1.0)      # a 24 minute race takes longer than 3 laps
    deadline = time.time() + limit
    while time.time() < deadline:
        if not user32.IsWindow(GAME[0]):
            return False, "!RACE: the game window closed during the race"
        here = next((d for d in dests if wait_for_page(ox, oy, [d], timeout=1.0, need=2) is not None), None)
        if here:
            ARRIVED[0] = here
            return True, "!RACE -> %s: autopilot race finished in %.0f s" % (here, time.time() - t0)
    shown = recognize_now(ox, oy)
    return False, "!RACE: no results page within %.0f s; the screen shows %s (left running: did K switch time acceleration on?)" % (
        limit, shown[0])


def step_drive(ox, oy, pages, page, expect):
    """On a practice or time trial session's monitor: press DRIVE (the car leaves the monitor for the cockpit, in its garage box) and wait
    until the monitor is gone and the cockpit has been still for a moment. Nothing else is pressed: the driving is left to the caller
    (gtr2-drive-lap.py). Needs --drive-step."""
    if not DRIVE_OK[0]:
        return False, "refused: !DRIVE needs --drive-step"
    if wait_for_page(ox, oy, [page], timeout=3.0, need=1) is None:
        return False, "!DRIVE: not on %s (screen shows %s)" % (page, recognize_now(ox, oy)[0])
    drive = [b for b in pages[page].buttons if b.kind == "APP_BUTTON_TOREALTIME"]
    if len(drive) != 1:
        return False, "!DRIVE: %s has %d drive buttons" % (page, len(drive))
    x, y = ui(*drive[0].center)
    t0 = time.time()
    before = thumbnail(ox, oy, *CLIENT)
    press(ox, oy, x, y)
    ch, _ = wait_change_then_settle(ox, oy, before, timeout=2.5)
    if ch is None and pagerec.is_page(look(ox, oy), page):
        press(ox, oy, x, y)                         # the first click only hovered: nothing started yet
    while time.time() - t0 < 60 and pagerec.is_page(look(ox, oy), page):
        time.sleep(0.2)
    if pagerec.is_page(look(ox, oy), page):
        return False, "!DRIVE: still on %s after 60 s" % page
    time.sleep(3.0)                                 # the cockpit view settles
    return True, "!DRIVE: in the car after %.1f s" % (time.time() - t0)


def step_leave_drive(ox, oy, pages, page, expect):
    """From the cockpit: Esc to the pause menu and Enter on the Return to Garage row only, then wait for the session monitor (`expect`, default
    MONITOR_SINGLE). Never Restart, Save or Quit. The first column says which monitor to expect. Needs --drive-step."""
    if not DRIVE_OK[0]:
        return False, "refused: !LEAVEDRIVE needs --drive-step"
    dest = (expect or page).split(",")[0].strip()
    if not has_ref(dest):
        return False, "!LEAVEDRIVE: no saved reference for %s" % dest
    if not open_pause_menu(ox, oy, tries=8):
        return False, "!LEAVEDRIVE: the pause menu never opened"
    ok, msg = select_pause_row(ox, oy, "Return to Garage", enter=True)
    if not ok:
        return False, "!LEAVEDRIVE: " + msg
    t0 = time.time()
    if wait_for_page(ox, oy, [dest], timeout=30.0, need=2) is None:
        return False, "!LEAVEDRIVE: %s not shown after 30 s (screen shows %s)" % (dest, recognize_now(ox, oy)[0])
    ARRIVED[0] = dest
    return True, "!LEAVEDRIVE -> %s after %.1f s" % (dest, time.time() - t0)


def step_next_session(ox, oy, pages, page):
    """On a session monitor: NEXT SESSION (practice to qualifying to race), then wait for the session label to change and settle.
    Needs --drive-step."""
    if not DRIVE_OK[0]:
        return False, "refused: !NEXTSESSION needs --drive-step"
    if wait_for_page(ox, oy, [page], timeout=3.0, need=1) is None:
        return False, "!NEXTSESSION: not on %s (screen shows %s)" % (page, recognize_now(ox, oy)[0])
    nxt = [b for b in pages[page].buttons if b.kind == "APP_BUTTON_NEXTSESSION"]
    if len(nxt) != 1:
        return False, "!NEXTSESSION: %s has %d next-session buttons" % (page, len(nxt))
    before = ui_region(ox, oy, *SESSION_LABEL)
    t0 = time.time()
    press(ox, oy, *ui(*nxt[0].center))
    if not region_moved(ox, oy, before, SESSION_LABEL, timeout=10.0):
        return False, "!NEXTSESSION: the session label did not change"
    last = ui_region(ox, oy, *SESSION_LABEL)
    quiet = time.time()
    while time.time() - quiet < 0.6 and time.time() - t0 < 15:
        cur = ui_region(ox, oy, *SESSION_LABEL)
        if float(np.abs(cur - last).mean()) > 1.0:
            last, quiet = cur, time.time()
        time.sleep(0.1)
    wait_for_page(ox, oy, [page], timeout=3.0, need=2)
    return True, "!NEXTSESSION: session changed after %.1f s" % (time.time() - t0)


def special_step(ox, oy, pages, page, label, expect):
    """Path-file steps whose label starts with "!": things a plain button press cannot do. The first column is still the page
    that must be showing. !SHORTRACE and !SHORTENDURANCE (setup sliders), !NEXTSESSION and !RACE (the last two need --drive-step)."""
    verb = label[1:].strip().upper()
    if verb == "SHORTRACE":
        return step_short_race(ox, oy, page)
    if verb == "SHORTENDURANCE":
        return step_short_endurance(ox, oy, page)
    if verb == "DRIVE":
        return step_drive(ox, oy, pages, page, expect)
    if verb == "LEAVEDRIVE":
        return step_leave_drive(ox, oy, pages, page, expect)
    if verb == "HOVER":
        return step_hover(ox, oy, pages, page)
    if verb == "CONTROLS":
        return step_controls(ox, oy, pages, page)
    if verb == "SHORTCHAMP":
        return step_short_champ(ox, oy, page)
    if verb == "NEXTSESSION":
        return step_next_session(ox, oy, pages, page)
    if verb == "RACE":
        return step_race(ox, oy, pages, page, expect)
    return False, "refused: unknown step %s" % label


def learn(ox, oy, pages, steps, start_page=None, samples=4, relearn=()):
    """Walk a path by 'the screen changed' and save a reference for every page it reaches that has none yet (or is in `relearn`):
    the page shown after each step, named by the step's expected page or the button's single target, and `start_page` for where
    the path begins. Several captures give the mask of moving pixels. References go to
    baselines/local, which override the shipped copies, because those were made on another profile (a different difficulty
    mode changes which controls are greyed). Returns the pages learned."""
    learned = []

    def settle_on(name):
        """A page that already has a reference is checked, not overwritten, so a button that led somewhere else can't
        replace a good reference with the wrong page's picture."""
        if has_ref(name) and name not in relearn and "all" not in relearn:
            if wait_for_page(ox, oy, [name], timeout=2.0) is None:
                shown = recognize_now(ox, oy)
                print("expected %s but the screen shows %s (score %.1f)" % (name, shown[0], shown[1]))
                return False
            return True
        frames = []
        for _ in range(samples):
            frames.append(look(ox, oy))
            time.sleep(0.25)
        share = pagerec.save_reference(name, frames, directory=LOCAL_BASELINES)
        pagerec.register_reference(name)
        learned.append(name)
        print("learned %-28s (%.0f%% of the pixels ignored)" % (name, 100.0 * share), flush=True)
        return True

    if start_page and not settle_on(start_page):
        return []
    for step in steps:
        page, label = step[0], step[1]
        ok, msg = goto_one(ox, oy, pages, page, label, step[2] if len(step) > 2 else None, verify=False)
        print(msg, flush=True)
        if not ok:
            print("stopped at: %s | %s" % (page, label))
            break
        dests = [d.strip() for d in step[2].split(",")] if len(step) > 2 else sorted(set(map(str, menumap.find_button(pages, page, label).targets)))
        if len(dests) == 1 and dests[0] not in ("", "-") and dests[0] != page:
            if not settle_on(dests[0]):
                break
    print("%d page(s) learned" % len(learned))
    return learned or [None]


SC_DOWN, SC_ENTER = 0x50, 0x1C   # hardware scancodes; Down is an extended key


def press_key(scancode, extended=False, hold=0.03):
    """A hardware-scancode key press (SendKeys does nothing in GTR2). Waits after the release too:
    the game reads keys by polling."""
    ensure_focus()
    flags = 0x0008 | (0x0001 if extended else 0)
    user32.keybd_event(0, scancode, flags, 0)
    time.sleep(hold)
    user32.keybd_event(0, scancode, flags | 0x0002, 0)
    time.sleep(hold)


def grab_client(ox, oy):
    with mss.MSS() as s:
        g = s.grab({"left": ox, "top": oy, "width": CLIENT[0], "height": CLIENT[1]})
    return np.frombuffer(g.rgb, dtype=np.uint8).reshape(g.height, g.width, 3)


def pause_row_now(ox, oy):
    """The pause menu's highlighted row in the live window, or None when the menu isn't showing."""
    return pause_row_of(grab_client(ox, oy).astype(np.int16))


def select_pause_row(ox, oy, target, limit=9, enter=False):
    """Step the highlight Down until it is on `target`, reading the screen after every key (the menu reopens on the row last
    used and its rows differ by session, so counting presses is unsafe). Enter is pressed only when `enter` is set and the
    highlight is verified on the target. Returns (ok, message)."""
    for _ in range(limit + 1):
        row = pause_row_now(ox, oy)
        if row is None:
            return False, "the pause menu is not showing"
        if row == target:
            if enter:
                press_key(SC_ENTER)
                return True, "pressed Enter on %s" % row
            return True, "highlight is on %s" % row
        press_key(SC_DOWN, extended=True)
        time.sleep(0.15)
    return False, "highlight never reached %s (last seen %s)" % (target, pause_row_now(ox, oy))


def solid_white(ox, oy):
    """True for a flat white window (an intermittent GTR2 fault: the game runs but the window stays white)."""
    a = grab_client(ox, oy).reshape(-1)[::97]
    return float(a.mean()) > 250 and float(a.std()) < 1.0


def solid_black(ox, oy):
    """True for a flat black window. Normal for the first few seconds of a start; a window that stays black 8 s after it appeared is
    the same fault (seen 2026-11-11: the game answered but drew nothing until a click)."""
    a = grab_client(ox, oy).reshape(-1)[::97]
    return float(a.mean()) < 3 and float(a.std()) < 1.0


def recover_blank_window(ox, oy):
    """The ladder for a white window: mouse move, minimize and restore, nudge by 1 px. Returns the step that worked."""
    h = GAME[0]

    def nudge():
        r = wintypes.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        user32.SetWindowPos(h, 0, r.left + 1, r.top + 1, 0, 0, 0x0001 | 0x0004 | 0x0010)

    steps = [("mouse move over the window", lambda: (move_to(ox, oy, 400, 300), time.sleep(0.05), move_to(ox, oy, 401, 301))),
             ("click in the window's empty centre", lambda: (move_to(ox, oy, 640, 360), time.sleep(0.05), mouse(0x0002), time.sleep(0.03), mouse(0x0004))),
             ("minimize and restore", lambda: (user32.ShowWindow(h, 6), time.sleep(0.6), user32.ShowWindow(h, 9))),
             ("move the window by 1 px", nudge)]
    for name, act in steps:
        act()
        time.sleep(1.5)
        if not solid_white(ox, oy) and not solid_black(ox, oy):
            return name
    return None


def screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def cmd_watch(limit, poll=0.25):
    """The launch watchdog, for a game that is already running: stops it when the desktop resolution changes (a wrong
    VIDEOMODE switches the whole display), when `limit` seconds pass, or on Ctrl+Alt+End. The only place a kill is allowed:
    those are the emergencies. Windowed GTR2 can be killed safely and Windows restores the display."""
    import subprocess
    h = user32.FindWindowW(None, "GTR2")
    if not h:
        print("GTR2 window not found; nothing to watch")
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    base = screen_size()
    hotkey = bool(user32.RegisterHotKey(None, 1, 0x1 | 0x2, 0x23))      # Ctrl+Alt+End
    print("watching pid %d: display %dx%d, limit %.0f s, Ctrl+Alt+End %s" % (
        pid.value, base[0], base[1], limit, "armed" if hotkey else "unavailable"), flush=True)
    t0, msg, reason = time.time(), wintypes.MSG(), None
    while user32.IsWindow(h):
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            if msg.message == 0x0312:
                reason = "Ctrl+Alt+End"
        if time.time() - t0 > limit:
            reason = "time limit"
        if screen_size() != base:
            reason = "display changed to %dx%d" % screen_size()
        if reason:
            subprocess.run(["taskkill", "/F", "/PID", str(pid.value)], capture_output=True)
            print("killed GTR2: %s" % reason)
            return False
        time.sleep(poll)
    print("game exited after %.0f s" % (time.time() - t0))
    return True



def ui(x, y):
    """UI canvas units (800x600) to client pixels (1.6 across and 1.2 down at 1280x720; the canvas is stretched over any window size)."""
    return int(round(x * CLIENT[0] / 800)), int(round(y * CLIENT[1] / 600))


DRAG_STEPS = 12


def drag(ox, oy, x1, y1, x2, y2):
    """Press at one UI point, move to another in small steps with the button held, release, park. The button is always released."""
    ensure_focus()
    (cx1, cy1), (cx2, cy2) = ui(x1, y1), ui(x2, y2)
    move_to(ox, oy, cx1, cy1)
    time.sleep(HOVER)
    mouse(0x0002)
    try:
        time.sleep(HOLD)
        for i in range(1, DRAG_STEPS + 1):
            move_to(ox, oy, cx1 + (cx2 - cx1) * i // DRAG_STEPS, cy1 + (cy2 - cy1) * i // DRAG_STEPS)
            time.sleep(0.02)
        time.sleep(HOLD)
    finally:
        mouse(0x0004)
    time.sleep(RELEASE)
    move_to(ox, oy, *PARK)


def cmd_slider(ox, oy, page, index, side):
    """Drag one slider of an Options page to its left or right end. The page must be showing (checked by page recognition when
    the page has a reference). The positions are the measured ones for the main-menu pages; a mode's own copy of the page
    (suffix _SUMMARY, _SCHOOL, ...) uses the same positions, so name the main page's key and the screen is checked against `--shows`."""
    geom = coords.SLIDER_GEOMETRY.get(page)
    if geom is None:
        print("no slider data for %s (known: %s)" % (page, ", ".join(sorted(coords.SLIDER_GEOMETRY))))
        return False
    if not 0 <= index < len(geom):
        print("%s has sliders 0 to %d" % (page, len(geom) - 1))
        return False
    if has_ref(page) and wait_for_page(ox, oy, [page], timeout=2.0, need=1) is None:
        print("not on %s: the screen shows %s" % (page, recognize_now(ox, oy)[0]))
        return False
    y, start, left, right = geom[index]
    before = thumbnail(ox, oy, *CLIENT)
    drag(ox, oy, start, y, left if side == "left" else right, y)
    key = coords.SLIDERS[page][index][0]
    ch, st = wait_change_then_settle(ox, oy, before, timeout=1.0)
    print("slider %d (%s) on %s dragged to the %s end: %s" % (
        index, key, page, side, "screen changed" if ch is not None else "no change on screen (already at that end?)"))
    return True


def cmd_row(ox, oy, which, index):
    """Click a list entry. circuit N = the Nth circuit name shown; model = the first car on the Model tab; class = the first class radio."""
    if which == "circuit":
        pt = coords.circuit_row(index)
    elif which == "model":
        pt = coords.MODEL_FIRST_ROW
    elif which == "class":
        pt = coords.CLASS_RADIO
    else:
        print("unknown list %s" % which)
        return False
    before = thumbnail(ox, oy, *CLIENT)
    press(ox, oy, *ui(*pt))
    ch, st = wait_change_then_settle(ox, oy, before, timeout=1.0)
    print("%s row %d at UI (%.1f,%.1f): %s" % (which, index, pt[0], pt[1], "screen changed" if ch is not None else "no change"))
    return ch is not None


def cmd_scroll(ox, oy, which, direction, count):
    down, up = ((coords.CIRCUIT_SCROLL_DOWN, coords.CIRCUIT_SCROLL_UP) if which == "circuit"
                else (coords.CLASS_SCROLL_DOWN, coords.CLASS_SCROLL_UP))
    pt = down if direction == "down" else up
    moved = 0
    for _ in range(count):
        before = thumbnail(ox, oy, *CLIENT)
        press(ox, oy, *ui(*pt))
        ch, _st = wait_change_then_settle(ox, oy, before, timeout=0.5)
        moved += ch is not None
    print("%s list scrolled %s: %d of %d presses changed the screen" % (which, direction, moved, count))
    return moved > 0



def cmd_refine(ox, oy, name, samples=3):
    """Merge what is on screen into an existing reference: any pixel that differs from the saved picture (or between the new
    captures) is added to its mask. For popups drawn over other pages (translucent), run this on the popup in each context
    and the reference ends up matching only the parts that never change. The saved picture itself is kept."""
    import numpy as np  # noqa: F811
    from PIL import Image
    refs = pagerec.cached_references()
    if name not in refs:
        print("no reference named %s (learn it first)" % name)
        return False
    image, mask = refs[name]
    frames = []
    for _ in range(samples):
        frames.append(look(ox, oy))
        time.sleep(0.15)
    stack = np.stack([image] + frames)
    changed = (stack.max(axis=0) - stack.min(axis=0)).max(axis=2) > pagerec.VOLATILE_THRESHOLD
    from PIL import ImageFilter
    grown = np.asarray(Image.fromarray((changed & ~mask) .astype("uint8") * 255).filter(ImageFilter.MaxFilter(5))) > 0
    new_mask = mask | grown
    # the picture is only written where it is the first time (LOCAL_BASELINES); a shipped reference is copied there first
    LOCAL_BASELINES.mkdir(parents=True, exist_ok=True)
    stem = pagerec.file_stem(name)
    Image.fromarray(image.astype("uint8")).save(LOCAL_BASELINES / (stem + ".png"), optimize=True)
    Image.fromarray((new_mask * 255).astype("uint8")).convert("1").save(LOCAL_BASELINES / (stem + ".mask.png"), optimize=True)
    pagerec.register_reference(name)
    kept_before, kept_after = int((~mask).sum()), int((~new_mask).sum())
    print("refined %s: %d of %d kept pixels were stable (%.1f%% of the picture is still compared)" % (
        name, kept_after, kept_before, 100.0 * kept_after / new_mask.size))
    return True


def cmd_index():
    """Work out every missing pair score between the references (offline). Run after learning or refining."""
    t0 = time.time()
    n = pagerec.index_all()
    print("index: %d new pair scores in %.1f s" % (n, time.time() - t0))
    return True



WINDOW_HOME = (20, 20)    # screen position of the game window's outer top-left, away from the bottom-right notification area


def place_window(h=None):
    """Move the game window to the top-left of the screen. Windows notification toasts (OneDrive, updates) appear at the
    bottom right and, with the window at its default place, cover the last 60 pixels of the game's right edge, which breaks page
    recognition. The size and the game itself are untouched; every command finds the window's origin again."""
    h = h or user32.FindWindowW(None, "GTR2")
    if not h:
        return False
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    if (r.left, r.top) != WINDOW_HOME:
        user32.SetWindowPos(h, 0, WINDOW_HOME[0], WINDOW_HOME[1], 0, 0, 0x0001 | 0x0004 | 0x0010)    # NOSIZE | NOZORDER | NOACTIVATE
        time.sleep(0.2)
    return True


def cmd_where(ox, oy):
    t0 = time.time()
    page, best, margin = recognize_now(ox, oy)
    print("page=%s score=%.2f margin=%.2f (%.2f s)" % (page, best, margin, time.time() - t0))
    return page is not None


def cmd_ready(timeout):
    """Wait for the game window, then for the main menu."""
    t0 = time.time()
    blank, recovered, blank_cpu, win_seen = None, False, None, None
    while time.time() - t0 < timeout:
        h = user32.FindWindowW(None, "GTR2")
        if h:
            GAME[0] = h
            refresh_client(h)
            win_seen = win_seen or time.time()
            place_window(h)
            pt = wintypes.POINT(0, 0)
            user32.ClientToScreen(h, ctypes.byref(pt))
            ensure_focus()
            move_to(pt.x, pt.y, *PARK)
            if solid_white(pt.x, pt.y) or (solid_black(pt.x, pt.y) and time.time() - t0 > 8):
                if blank is None:
                    blank, blank_cpu = time.time(), diag.cpu_seconds(diag.pid_of(h))
                if not recovered and time.time() - blank >= 3:
                    recovered = True
                    kind = "white" if solid_white(pt.x, pt.y) else "black"
                    note = diag.blank_window_note(h, time.time() - blank, blank_cpu)
                    step = recover_blank_window(pt.x, pt.y) or "nothing worked"
                    print("window is solid %s; recovery: %s" % (kind, step), flush=True)
                    note += "; solid %s; recovery: %s; %.1f s after the window appeared" % (kind, step, time.time() - win_seen)
                    print("  " + note, flush=True)
                    try:
                        with open(Path(__file__).resolve().parent / "gtr2_ui" / "runs" / "blank_window.log", "a", encoding="utf-8") as f:
                            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), note))
                    except OSError:
                        pass
            else:
                blank = None
            if has_ref("MAIN MENU"):
                shown = wait_for_page(pt.x, pt.y, ["MAIN MENU"], timeout=0.5) is not None
            else:     # no learned reference yet: a lit window whose thumbnail has stopped changing
                first = thumbnail(pt.x, pt.y, *CLIENT); time.sleep(0.5)
                shown = first == thumbnail(pt.x, pt.y, *CLIENT) and sum(capture(pt.x, pt.y)) / (THUMB[0] * THUMB[1] * 4) > 20
            if shown:
                print("main menu ready after %.1f s" % (time.time() - t0))
                return True
        time.sleep(0.1)
    print("main menu not reached after %.0f s" % timeout)
    cmd_diagnose()
    return False


def cmd_diagnose(save=True):
    """What the screen and the windows look like now, so a failure can be explained afterwards. Saves the game window's picture (only the
    game, never the whole desktop) to gtr2_ui/runs/diag_<time>.png when it can be captured."""
    print("diagnose: session %d, active console session %d, screen %dx%d" % (*diag.console_session(), *screen_size()))
    for line in diag.describe_windows(GAME[0] or None):
        print("  " + line)
    for image in ("GTR2.exe", "GTR2Config.exe", "GTR2Dedicated.exe"):
        pids = diag.running(image)
        if pids:
            print("  running: %s %s" % (image, pids))
    problem = diag.session_problem()
    if problem:
        print("  PROBLEM: " + problem)
    h = GAME[0] or user32.FindWindowW(None, "GTR2")
    if not h:
        return
    try:
        pt = wintypes.POINT(0, 0)
        user32.ClientToScreen(h, ctypes.byref(pt))
        frame = grab_client(pt.x, pt.y)
        print("  capture: mean %.0f, std %.1f%s" % (float(frame.mean()), float(frame.std()),
              " (solid white)" if float(frame.mean()) > 250 and float(frame.std()) < 1 else " (solid black)" if float(frame.mean()) < 3 and float(frame.std()) < 1 else ""))
        if save:
            from PIL import Image
            out = Path(__file__).resolve().parent / "gtr2_ui" / "runs" / ("diag_%s.png" % time.strftime("%Y%m%d-%H%M%S"))
            out.parent.mkdir(exist_ok=True)
            Image.fromarray(frame).save(out)
            print("  saved " + str(out))
    except Exception as e:      # a denied capture is itself the finding
        print("  capture failed: %r" % (e,))


def cmd_preflight():
    """Checks before a launch: the screen's session, the config the launcher installs, other GTR2 programs, a leftover launcher lock or backup,
    and whether the screen can be captured. Prints one line per check; returns True if all pass."""
    results = []
    problem = diag.session_problem()
    results.append(("session", problem is None, problem or "this process is in the session that shows the screen"))
    cfg = diag.game_root() / "config" / "Documents-Config.ini"
    try:
        problems = diag.config_problems(cfg.read_bytes().decode("latin1"))
        results.append(("config", not problems, "; ".join(problems) or "%s is windowed with relative data paths" % cfg.name))
    except OSError as e:
        results.append(("config", False, "cannot read %s: %s" % (cfg, e)))
    running = {i: diag.running(i) for i in ("GTR2.exe", "GTR2Config.exe", "GTR2Dedicated.exe")}
    busy = ["%s %s" % (i, p) for i, p in running.items() if p]
    results.append(("no other GTR2", not busy, "running: " + ", ".join(busy) if busy else "no GTR2 program is running"))
    docs = Path.home() / "Documents"
    left = [n for n in ("GTR2.launcher.lock", "GTR2.launcher-backup") if (docs / n).exists()]
    results.append(("launcher", not left, "left over from an interrupted run: %s (run gtr2-launch.ps1 -Restore)" % ", ".join(left) if left
                    else "no lock or backup left in Documents"))
    try:
        with mss.MSS() as s:
            s.grab({"left": 0, "top": 0, "width": 4, "height": 4})
        results.append(("capture", True, "the screen can be captured"))
    except Exception as e:
        results.append(("capture", False, "the screen cannot be captured: %r" % (e,)))
    for name, ok, detail in results:
        print("%-14s %s  %s" % (name, "ok  " if ok else "FAIL", detail))
    return all(ok for _n, ok, _d in results)


EXIT_BUTTON, EXIT_CONFIRM = (82, 572), (660, 299)   # UI canvas units (client (131,687) and (1056,359) at 1280x720); use ui()


def cmd_exit(ox, oy, timeout=20.0):
    """Close the game through its own menu: must be on the main menu; EXIT, then the confirm tick. No kill."""
    if wait_for_page(ox, oy, ["MAIN MENU"], timeout=2.0, need=1) is None:
        print("not on the main menu (screen shows %s); go back first" % recognize_now(ox, oy)[0])
        return False
    # The exit popup never lets the whole screen settle (waiting for that ran into the 3 s timeout every time, measured 2026-11-11:
    # confirm clicked 3.0 s after EXIT). Watch only the thumbnail cells around the confirm tick instead: when they change, the popup
    # is drawn; click after a short beat.
    def tick_cells():
        buf = capture(ox, oy)
        cx, cy = EXIT_CONFIRM[0] * THUMB[0] // 800, EXIT_CONFIRM[1] * THUMB[1] // 600
        return b"".join(bytes(buf[(r * THUMB[0] + cx - 8) * 4:(r * THUMB[0] + cx + 8) * 4]) for r in range(cy - 6, cy + 7))
    before = tick_cells()
    t_press = time.time()
    press(ox, oy, *ui(*EXIT_BUTTON))
    t_pressed = time.time()
    ch = None
    while time.time() - t_pressed < 3.0:
        if tick_cells() != before:
            ch = time.time() - t_pressed
            break
        time.sleep(POLL)
    if ch is None:
        print("the exit popup did not appear")
        return False
    time.sleep(0.12)         # let the popup finish drawing
    _st = None
    t_settled = time.time()
    ensure_focus()
    move_to(ox, oy, *ui(*EXIT_CONFIRM))
    time.sleep(HOVER)
    mouse(0x0002); time.sleep(HOLD); mouse(0x0004)
    # timing of the exit sequence, to find where the delay before the confirm click comes from
    print("exit timing: press took %.2f s, popup first change %.2f s and settled %.2f s after the press, confirm clicked %.2f s after settling" % (
        t_pressed - t_press, ch, _st if _st is not None else -1, time.time() - t_settled))
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not user32.IsWindow(GAME[0]):
            print("exited cleanly after %.1f s" % (time.time() - t0))
            return True
        time.sleep(0.1)
    print("the game did not exit within %.0f s (not killed)" % timeout)
    return False



def serve(idle_limit=1200.0):
    """The background server behind nav_client: runs each command in this process (so imports, decoded references and the
    screen grabber are kept) and streams its output back. One command at a time. Exits after `idle_limit` seconds without
    a command, on `stop`, or when the scripts change (the client then starts a fresh one)."""
    import contextlib
    import io
    import json
    import os
    import socket
    import traceback
    import nav_client

    token = os.urandom(16).hex()
    nav_client.TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    nav_client.TOKEN_FILE.write_text(token)
    my_version = nav_client.version()
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", nav_client.PORT))
    srv.listen(4)
    srv.settimeout(5.0)
    pagerec.cached_references()          # decode nothing yet, just index the files
    last = time.time()

    class Stream(io.TextIOBase):
        def __init__(self, conn):
            self.conn = conn

        def writable(self):
            return True

        def write(self, text):
            self.conn.sendall(text.encode("utf-8", "replace"))
            return len(text)

        def flush(self):
            pass

    while time.time() - last < idle_limit:
        try:
            conn, _addr = srv.accept()
        except socket.timeout:
            continue
        with conn:
            conn.settimeout(10.0)
            try:
                req = json.loads(conn.makefile("rb").readline().decode("utf-8"))
            except (ValueError, OSError):
                continue
            if req.get("token") != token:
                continue
            conn.settimeout(None)
            last = time.time()
            if req.get("stop"):
                conn.sendall(nav_client.END + b"0\n")
                break
            if req.get("version") != my_version:
                conn.sendall(nav_client.END + b"RESTART\n")
                break
            out, code = Stream(conn), 0
            old_argv = sys.argv
            sys.argv = ["gtr2-nav.py"] + list(req["argv"])
            ARRIVED[0] = None
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                    try:
                        main()
                    except SystemExit as e:
                        if e.code is None:
                            code = 0
                        elif isinstance(e.code, int):
                            code = e.code
                        else:
                            print(e.code)
                            code = 1
                    except BaseException:
                        traceback.print_exc()
                        code = 1
            finally:
                sys.argv = old_argv
            try:
                conn.sendall(nav_client.END + str(code).encode() + b"\n")
            except OSError:
                pass
            last = time.time()
    srv.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("click"); c.add_argument("x", type=int); c.add_argument("y", type=int)
    c.add_argument("--no-wait", action="store_true")
    m = sub.add_parser("measure"); m.add_argument("x", type=int); m.add_argument("y", type=int)
    m.add_argument("--runs", type=int, default=3)
    s = sub.add_parser("sweep", help="compare timing sets on two rows, e.g. the Level 4 and Level 5 rows (110 231 and 110 249)")
    s.add_argument("x1", type=int); s.add_argument("y1", type=int); s.add_argument("x2", type=int); s.add_argument("y2", type=int)
    s.add_argument("--n", type=int, default=20)
    s.add_argument("--region", default="478,166,137,18", help="client rectangle x,y,w,h whose content must show the clicked item (default: the level heading)")
    pa = sub.add_parser("path", help="run a file of 'PAGE | LABEL' steps in one process, no pauses between them")
    pa.add_argument("file"); pa.add_argument("--session-step", action="store_true", help="unlock only loading a track and leaving it"); pa.add_argument("--host-step", action="store_true", help="with --lan-step: allow the games list HOST button, which only opens the host setup pages"); pa.add_argument("--lan-step", action="store_true", help="also touch the local multiplayer pages (never host, join, refresh or add a server)"); pa.add_argument("--popup-step", action="store_true", help="also open save/delete/rename/load/exit popups (they are only cancelled)"); pa.add_argument("--season-step", action="store_true", help="also unlock starting a championship season (new season, team and driver confirm, round start)"); pa.add_argument("--drive-step", action="store_true", help="also allow the post-race CONTINUE and the !RACE / !NEXTSESSION steps (drives a race on the game's autopilot)"); pa.add_argument("--setting-step", action="store_true", help="also allow the !CONTROLS step (clicks every checkbox and spinner of a settings page; changes the profile)")
    g = sub.add_parser("goto", help="press a button by its caption on a page of the menu map, then wait for the screen to settle")
    g.add_argument("page"); g.add_argument("label"); g.add_argument("--session-step", action="store_true"); g.add_argument("--season-step", action="store_true"); g.add_argument("--popup-step", action="store_true"); g.add_argument("--lan-step", action="store_true"); g.add_argument("--host-step", action="store_true"); g.add_argument("--drive-step", action="store_true"); g.add_argument("--setting-step", action="store_true"); g.add_argument("--expect", help="destination page(s), comma separated, instead of the map's target")
    le = sub.add_parser("learn", help="walk a path file and save this machine's own reference image for each page it reaches")
    le.add_argument("--session-step", action="store_true"); le.add_argument("--season-step", action="store_true"); le.add_argument("--popup-step", action="store_true"); le.add_argument("--lan-step", action="store_true"); le.add_argument("--host-step", action="store_true"); le.add_argument("--drive-step", action="store_true"); le.add_argument("--setting-step", action="store_true"); le.add_argument("file"); le.add_argument("--start", help="name of the page the game is on now (also learned)")
    le.add_argument("--relearn", default="", help="comma separated pages whose reference is replaced instead of checked")
    sub.add_parser("where", help="say which menu page is on screen (compared with the saved references)")
    r = sub.add_parser("ready", help="wait for the game window and the main menu"); r.add_argument("--timeout", type=float, default=60)
    pm = sub.add_parser("pause", help="read the pause menu's highlighted row; with ROW, step the highlight to that row")
    pm.add_argument("row", nargs="?"); pm.add_argument("--enter", action="store_true", help="press Enter once the highlight is verified on ROW")
    w = sub.add_parser("watch", help="watchdog for a running game: stop it on a display change, the time limit or Ctrl+Alt+End")
    w.add_argument("--limit", type=float, default=1800)
    d = sub.add_parser("drag"); [d.add_argument(n, type=float) for n in ("x1", "y1", "x2", "y2")]
    sl = sub.add_parser("slider"); sl.add_argument("page"); sl.add_argument("index", type=int); sl.add_argument("side", choices=("left", "right"))
    rw = sub.add_parser("row"); rw.add_argument("which", choices=("circuit", "model", "class")); rw.add_argument("index", type=int, nargs="?", default=0)
    sc = sub.add_parser("scroll"); sc.add_argument("which", choices=("circuit", "class")); sc.add_argument("direction", choices=("down", "up"))
    sc.add_argument("count", type=int, nargs="?", default=1)
    rf = sub.add_parser("refine", help="merge the screen into a saved reference: pixels that differ are masked (for popups over other pages)"); rf.add_argument("name")
    sub.add_parser("index", help="compute the page-pair scores used for twin pages (run after learn/refine; no game needed)")
    sub.add_parser("preflight", help="checks before a launch (screen session, config, other GTR2 programs, launcher leftovers, screen capture)")
    sub.add_parser("diagnose", help="describe the screen and windows now (also printed when ready fails)")
    sub.add_parser("place", help="move the game window to the top-left of the screen (done by ready), away from notification toasts")
    sub.add_parser("serve", help="run the background server that the other commands are forwarded to (started automatically)")
    sub.add_parser("stop", help="stop the background server")
    sub.add_parser("exit", help="close the game through the main menu's EXIT and its confirm tick (no kill)")
    a = ap.parse_args()
    SESSION_OK[0] = bool(getattr(a, "session_step", False))
    SEASON_OK[0] = bool(getattr(a, "season_step", False))
    POPUP_OK[0] = bool(getattr(a, "popup_step", False))
    LAN_OK[0] = bool(getattr(a, "lan_step", False))
    HOST_OK[0] = bool(getattr(a, "host_step", False))
    DRIVE_OK[0] = bool(getattr(a, "drive_step", False))
    SETTING_OK[0] = bool(getattr(a, "setting_step", False))
    if a.cmd == "place":
        window_origin()
        print("window placed" if place_window(GAME[0]) else "GTR2 window not found")
        return
    if a.cmd == "preflight":
        sys.exit(0 if cmd_preflight() else 1)
    if a.cmd == "diagnose":
        cmd_diagnose()
        return
    if a.cmd == "index":
        sys.exit(0 if cmd_index() else 2)
    if a.cmd == "refine":
        ox, oy, _ = window_origin()
        sys.exit(0 if cmd_refine(ox, oy, a.name) else 2)
    if a.cmd == "serve":
        serve()
        return
    if a.cmd == "stop":
        print("no server running")
        return
    if a.cmd == "ready":
        sys.exit(0 if cmd_ready(a.timeout) else 2)
    if a.cmd == "where":
        ox, oy, _ = window_origin()
        sys.exit(0 if cmd_where(ox, oy) else 1)
    if a.cmd == "watch":
        sys.exit(0 if cmd_watch(a.limit) else 2)
    if a.cmd == "pause":
        ox, oy, _ = window_origin()
        if a.row is None:
            row = pause_row_now(ox, oy)
            print("pause row=%s" % row)
            sys.exit(0 if row else 1)
        ok, msg = select_pause_row(ox, oy, a.row, enter=a.enter)
        print(msg)
        sys.exit(0 if ok else 2)
    if a.cmd in ("drag", "slider", "row", "scroll"):
        ox, oy, _ = window_origin()
        if a.cmd == "drag":
            drag(ox, oy, a.x1, a.y1, a.x2, a.y2)
            sys.exit(0)
        ok = (cmd_slider(ox, oy, a.page, a.index, a.side) if a.cmd == "slider" else cmd_row(ox, oy, a.which, a.index)
              if a.cmd == "row" else cmd_scroll(ox, oy, a.which, a.direction, a.count))
        sys.exit(0 if ok else 2)
    if a.cmd == "exit":
        ox, oy, _ = window_origin()
        sys.exit(0 if cmd_exit(ox, oy) else 2)
    if a.cmd == "learn":
        ox, oy, _ = window_origin()
        pages, _dups = menumap.load()
        steps = [[c.strip() for c in l.split("|")] for l in Path(a.file).read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.startswith("#")]
        sys.exit(0 if learn(ox, oy, pages, steps, a.start, relearn=[r.strip() for r in a.relearn.split(',') if r.strip()]) else 2)
    if a.cmd == "goto":
        ox, oy, _ = window_origin()
        pages, _dups = menumap.load()
        ok, msg = goto_one(ox, oy, pages, a.page, a.label, a.expect)
        print(msg)
        sys.exit(0 if ok else 2)
    if a.cmd == "path":
        # a whole sequence in one process: no pauses between steps and no return to the caller. Each line of the file is
        # "PAGE | LABEL" or "PAGE | LABEL | EXPECTED PAGE(S)". Every step checks the screen shows PAGE before pressing and that
        # the destination shows afterwards; it stops at the first step that fails (exit 2), so nothing runs blind.
        ox, oy, _ = window_origin()
        pages, _dups = menumap.load()
        steps = [[c.strip() for c in l.split("|")] for l in Path(a.file).read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.startswith("#")]
        t0 = time.time()
        for step in steps:
            page, label = step[0], step[1]
            ok, msg = goto_one(ox, oy, pages, page, label, step[2] if len(step) > 2 else None)
            print(msg, flush=True)
            if not ok:
                print("stopped at: %s | %s" % (page, label))
                sys.exit(2)
        print("path of %d steps done in %.2f s" % (len(steps), time.time() - t0))
        return
    ox, oy, _ = window_origin()
    if a.cmd == "sweep":
        sweep(ox, oy, [(a.x1, a.y1), (a.x2, a.y2)], a.n, tuple(int(v) for v in a.region.split(",")))
        return
    if a.cmd == "click":
        before = thumbnail(ox, oy, *CLIENT)
        press(ox, oy, a.x, a.y)
        if not a.no_wait:
            ch, st = wait_change_then_settle(ox, oy, before)
            print("screen changed after %s s, settled after %s s" % (
                "-" if ch is None else "%.2f" % ch, "-" if st is None else "%.2f" % st))
    elif a.cmd == "measure":
        for r in range(a.runs):
            before = thumbnail(ox, oy, *CLIENT)
            press(ox, oy, a.x, a.y)
            ch, st = wait_change_then_settle(ox, oy, before)
            print("run %d: changed %s s, settled %s s" % (r + 1, "-" if ch is None else "%.2f" % ch,
                                                          "-" if st is None else "%.2f" % st))


if __name__ == "__main__":
    main()
