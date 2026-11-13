"""Read UIData/gtr2ui.mnu into a map of pages, buttons and page transitions. Never writes to the game's files.

File structure:
  AttributeSet="X" { Size=(w,h) ... }   shared widget styles, which give a widget its size if it doesn't state one
  Layer="Normal|Modal" {                Normal layers hold full pages, Modal layers hold popups
    Gizmo="T" {...}                     shared by every page in the layer
    Page="NAME" { Pos-w-h=(x,y,w,h) Gizmo="T" { Position=(x,y) Caption1="..." Actions="Release" { Do_Page="P" } } }
  }
A gizmo's Position is relative to its page's Pos-w-h. The canvas is 800x600.

Usage:
  menumap.py report             Summary and the gaps that couldn't be resolved
  menumap.py page NAME          One page's buttons, with screen coordinates and safety
  menumap.py safe               The pages an automated crawl may reach, by safe buttons only
  menumap.py risky              Every page flagged as unsafe, with the reason
"""
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import diag  # noqa: E402
MNU = diag.game_root() / "UIData" / "gtr2ui.mnu"
START_PAGE = "MAIN MENU"

# Pages an automated crawl must not enter. The first matching rule gives the reason.
RISKY_PAGES = [
    (r"DELETE", "deletes data"),
    (r"OVERWRITE", "overwrites data"),
    (r"NEW SEASON|START NEW|RESUMEORNEW", "can reset championship progress"),
    (r"CONFIRM_TO_WINDOWS|CONFIRM_EXIT", "exits the game"),
    (r"CONFIRM_UPDATE|WHATS_NEW", "software update"),
    (r"CDKEY|PASSWORD|REGISTER|LOGIN|GTR_ONLINE|LOBBY|_ONLINE|ONLINE_|GARAGEONLINE", "online service or account"),
    (r"MPHOST|MPCLIENT|_HOST$|CLIENT |MP_SELECT|MPLIST|MPSETTINGS|JOIN_GAME|MULTI|GRIDARRANGE", "multiplayer"),
    (r"ADDPROFILE|PROFILE ADD", "creates a profile"),
    (r"CONFIRM_", "confirms an action"),
    (r"^MONITOR|GRIDMONITOR|POST RACE|POSTRACE|SUMMARY_|FULLGRID|SECTORGRID", "race session flow"),
]
# Button types a crawl may click: these only change page. Anything else may run game logic.
NAV_BUTTON_TYPES = {"GENERIC_BUTTON_NORMAL", "APP_BUTTON_PAGEFADE", "APP_BUTTON_NAV", "APP_BUTTON_RTNAV"}
# A button with one of these words in its caption or name may do more than change page, even if it leads
# to a safe page.
RISKY_WORDS = re.compile(r"\b(DELETE|ADD|NEW|LOAD|UPLOAD|DOWNLOAD|SAVE|RESET|EXIT|QUIT|INSTALL|UPDATE|CONNECT|LOGIN|"
                         r"REGISTER|JOIN|HOST|DRIVE|START|RACE|DEFAULTS?|OK|YES|APPLY|ACCEPT|CONFIRM)\b", re.I)


# Buttons that start or end a session, or change saved progress. press-button refuses these even with
# --allow-risky. Matched by type first, because captions can change at runtime: the type behind the file's RESTART
# caption is shown as START until a season begins. Exiting the game has its own command.
NEVER_PRESS_TYPES = {
    "APP_BUTTON_TOREALTIME", "APP_BUTTON_CIRCUITSELECT", "APP_BUTTON_NEXTSESSION", "APP_BUTTON_READSTATE",
    "APP_BUTTON_CH_NEWSEASON", "APP_BUTTON_CH_RESUMESEASON", "APP_BUTTON_MULTIPLAYER_JOIN",
    "APP_RESTARTRACEBUTTON", "APP_RESTARTRACECONFIRMBUTTON", "APP_FINISHRACE_BUTTON", "APP_BUTTON_EXITGAME",
    "APP_BUTTON_TEAMDRIVER", "APP_BUTTON_ADDPROFILE", "APP_BUTTON_LOADPROFILE",
    "APP_BUTTON_SAVEGAME", "APP_BUTTON_GARAGE_TODELETESETUP", "APP_BUTTON_GARAGE_LOADDEFAULT",
    "APP_BUTTON_GARAGE_LOADSETUP", "APP_BUTTON_GARAGE_SETSETUPASDEFAULT", "APP_BUTTON_GARAGE_ONLINE_EXCHANGE",
    "APP_BUTTON_GARAGE_DATAACQUISITIONTOGGLE", "APP_BUTTONLEAVETRACK",
    "APP_CH_CUSTOMSTART",  # the confirm on "All progress will be lost. Continue?" when starting a new season
    "APP_BUTTON_CH_ADVANCEPRERACECONSTRUCTORSTANDINGS",  # CONTINUE on a championship round's pages: starts the round
}
NEVER_PRESS_CAPTIONS = {"CONTINUE", "CONTINUE TO", "START", "RESTART", "DRIVE", "LOAD LAST SAVED", "SAVE GAME",
                        "SELECT", "LEAVE EVENT", "LEAVE TRACK", "NEXT SESSION:", "RESTART RACE", "FINISH RACE",
                        "SAVE", "FAVORITE", "DEFAULT", "DELETE"}
# The only blocked buttons --session-step may press: loading a track from a setup page, and leaving it.
# Driving, advancing a session and everything else stay blocked with no override.
SESSION_STEP_TYPES = {"APP_BUTTON_CIRCUITSELECT", "APP_BUTTONLEAVETRACK"}


SCHOOL_LEAVE_PAGES = {"MONITOR_SCHOOL", "TRACKINFO_SCHOOL"}


def session_step_ok(b, page):
    """Whether --session-step unlocks this button: loading a track, or leaving one. Leaving is the dedicated leave-track
    kind, or, on the two Driving School session pages only, a generic button captioned LEAVE TRACK whose only target is
    the leave confirmation: the same action, drawn with another gizmo."""
    if b.kind in SESSION_STEP_TYPES:
        return True
    return (page in SCHOOL_LEAVE_PAGES and b.caption.upper() == "LEAVE TRACK" and list(b.targets) == ["CONFIRM_EXIT"])


# The only blocked buttons --season-step may press: starting a new championship season (RESTART on the first page, and
# the warning popup's confirm), and CONTINUE through the team and driver choice. Saving, loading, finishing a race,
# restarting a race, resuming an existing season, and leaving stay as they were.
SEASON_STEP_TYPES = {"APP_BUTTON_CH_NEWSEASON", "APP_CH_CUSTOMSTART", "APP_BUTTON_TEAMDRIVER",
                     "APP_BUTTON_CH_ADVANCEPRERACECONSTRUCTORSTANDINGS"}  # the last starts the round from its info page

# The only blocked buttons --drive-step may press, as well: DRIVE (leaves the garage and takes the car out),
# CONTINUE TO (moves on to the next session) and CONTINUE on the post-race results page. Saving, restarting,
# finishing a race, deleting and exiting stay blocked with no override.
DRIVE_STEP_TYPES = {"APP_BUTTON_TOREALTIME", "APP_BUTTON_NEXTSESSION", "APP_BUTTON_POSTRACENAVIGATION"}


@dataclass
class Node:
    key: str
    value: str
    line: int
    props: list = field(default_factory=list)
    children: list = field(default_factory=list)

    def get(self, key, default=None):
        for k, v in self.props:
            if k == key:
                return v
        return default


@dataclass
class Button:
    page: str
    kind: str
    x: float
    y: float
    w: float | None
    h: float | None
    caption: str
    attribute_set: str
    name: str
    shared: bool
    line: int
    targets: list
    pops: bool = False
    back: bool = False
    simulates: bool = False

    @property
    def center(self):
        """Where to click. None if the file doesn't give this widget a size."""
        if self.w is None or self.h is None:
            return None
        return (self.x + self.w / 2, self.y + self.h / 2)

    @property
    def label(self):
        return self.caption or self.name or self.kind


@dataclass
class Page:
    name: str
    layer: str
    modal: bool
    x: float
    y: float
    w: float
    h: float
    line: int
    buttons: list = field(default_factory=list)
    controls: list = field(default_factory=list)


def strip_comment(line):
    """Remove a // comment, leaving // inside a quoted value alone."""
    quoted = False
    for i, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif ch == "/" and not quoted and line[i:i + 2] == "//":
            return line[:i]
    return line


def parse_tree(text):
    root = Node("root", "", 0)
    stack = [root]
    last = None
    for n, raw in enumerate(text.split("\n"), 1):
        s = strip_comment(raw).strip()
        if not s:
            continue
        if s == "{":
            if last is None:
                raise ValueError(f"line {n}: block with no header")
            stack[-1].children.append(last)
            stack.append(last)
            last = None
        elif s == "}":
            if len(stack) == 1:
                raise ValueError(f"line {n}: unbalanced close")
            stack.pop()
            last = None
        else:
            m = re.match(r'^([^=]+?)\s*=\s*(.*)$', s)
            key, value = (m.group(1), m.group(2).strip('"')) if m else (s, "")
            stack[-1].props.append((key, value))
            last = Node(key, value, n)
    if len(stack) != 1:
        raise ValueError("unbalanced blocks at end of file")
    return root


def numbers(value):
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", value or "")]


def make_button(page_name, gizmo, sizes, offset, shared):
    pos = numbers(gizmo.get("Position"))
    size = numbers(gizmo.get("Width_Height"))
    attr = gizmo.get("AttributeSet", "")
    if len(size) < 2:
        size = sizes.get(attr, [None, None])
    b = Button(page=page_name, kind=gizmo.value, x=offset[0] + (pos[0] if pos else 0),
               y=offset[1] + (pos[1] if len(pos) > 1 else 0), w=size[0], h=size[1],
               caption=gizmo.get("Caption1", "").strip(), attribute_set=attr, name=gizmo.get("Name", ""),
               shared=shared, line=gizmo.line, targets=[])
    for action in gizmo.children:
        if action.key != "Actions":
            continue
        for k, v in action.props:
            if k == "Do_Page":
                b.targets.append(v)
            elif k == "Drop_Popups":
                b.pops = True
            elif k == "Do_Last_Page":
                b.back = True
            elif k == "SimulateClick":
                b.simulates = True
    return b


def is_button(b):
    return bool(b.targets or b.pops or b.back or b.simulates or "BUTTON" in b.kind.upper())


def load(path=MNU):
    text = path.read_bytes().decode("latin1").replace("\r", "")
    root = parse_tree(text)
    sizes = {}
    for node in root.children:
        if node.key == "AttributeSet":
            size = numbers(node.get("Size"))
            if len(size) >= 2:
                sizes[node.value] = size
    pages = {}
    duplicates = []
    for layer in (c for c in root.children if c.key == "Layer"):
        shared = [c for c in layer.children if c.key == "Gizmo"]
        for node in (c for c in layer.children if c.key == "Page"):
            rect = numbers(node.get("Pos-w-h"))
            name = node.value
            page = Page(name, layer.get("Name", ""), layer.value == "Modal", *rect[:4], node.line)
            own = [make_button(name, g, sizes, rect[:2], False) for g in node.children if g.key == "Gizmo"]
            # Shared gizmos use the layer's coordinates, not the page's: the layer covers the whole canvas.
            common = [make_button(name, g, sizes, (0, 0), True) for g in shared]
            page.buttons = [b for b in own + common if is_button(b)]
            page.controls = [b for b in own + common if "SPINBOX" in b.kind or "CHECKBOX" in b.kind]
            if name in pages:
                duplicates.append((name, pages[name].line, node.line))
            pages[name] = page
    return pages, duplicates


@lru_cache(maxsize=1)
def cached_load():
    """The map, parsed once per process. The file is read-only and takes about 90 ms to parse."""
    return load()


def page_risk(name):
    for pattern, reason in RISKY_PAGES:
        if re.search(pattern, name):
            return reason
    return None


def never_press(b):
    """Why this button must never be pressed by automation, or None."""
    if b.kind in NEVER_PRESS_TYPES:
        return f"type {b.kind} starts a session or changes saved progress"
    if b.caption.upper() in NEVER_PRESS_CAPTIONS:
        return f"caption {b.caption!r} starts a session or changes saved progress"
    return None


def button_problem(b, pages):
    """Why a crawl may not click this button, or None if it's safe."""
    if b.center is None:
        return "no known size"
    if b.kind not in NAV_BUTTON_TYPES:
        return f"type {b.kind} may run game logic"
    word = RISKY_WORDS.search(f"{b.caption} {b.name}")
    if word:
        return f"label contains {word.group(0)!r}"
    if not b.targets:
        return "no target page"
    for t in b.targets:
        if t not in pages:
            return f"target {t!r} isn't a page"
        reason = page_risk(t)
        if reason:
            return f"target {t!r}: {reason}"
    return None


def safe_reachable(pages, start=START_PAGE):
    """Pages reachable from the start through safe buttons only."""
    seen = {start: None}
    queue = [start]
    while queue:
        current = queue.pop(0)
        for b in pages[current].buttons:
            if button_problem(b, pages):
                continue
            for t in b.targets:
                if t not in seen:
                    seen[t] = (current, b.label)
                    queue.append(t)
    return seen


def find_button(pages, page, label):
    """Find the button on a page matching a label. Raises if it's missing or ambiguous.

    Two buttons that lead to the same place, like the two MAIN MENU buttons, aren't ambiguous: the top one is used.
    """
    if page not in pages:
        raise KeyError(f"no page {page!r}")
    want = label.casefold()
    for field_name in ("caption", "name", "kind"):
        matches = [b for b in pages[page].buttons if getattr(b, field_name).casefold() == want]
        if matches and len({tuple(b.targets) for b in matches}) == 1 and all(b.targets for b in matches):
            return min(matches, key=lambda b: b.y)
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise KeyError(f"{label!r} matches {len(matches)} different buttons on {page!r}, at lines "
                           f"{[b.line for b in matches]}")
    labels = sorted({b.label for b in pages[page].buttons})
    raise KeyError(f"no button {label!r} on {page!r}. Buttons: {labels}")


def find_control(pages, page, kind):
    """Find a checkbox or spinner on a page by its gizmo type."""
    matches = [c for c in pages[page].controls if c.kind == kind]
    if len(matches) != 1:
        raise KeyError(f"expected one {kind} on {page!r}, found {len(matches)}")
    return matches[0]


def spinner_next(control):
    """Where to click to move a spinner to its next value. The file doesn't say, so these were measured in the game."""
    if control.attribute_set == "SpinBox_Neon":
        return control.x + 361, control.y + 19
    if control.attribute_set == "SpinBox_Neon_Large":
        return control.x + 361, control.y + 20
    if control.attribute_set == "SpinBox_Neon_Small":
        return control.x + 316, control.y + 20
    if control.attribute_set == "SpinBox_Chrome_GaragePMLP":
        return control.x + 28, control.y + 8
    raise KeyError(f"no measured arrow position for {control.attribute_set!r}")


def cmd_report(pages, duplicates):
    buttons = [b for p in pages.values() for b in p.buttons]
    with_targets = [b for b in buttons if b.targets]
    links = Counter(t for b in with_targets for t in b.targets)
    missing = sorted(t for t in links if t not in pages)
    reachable = set()
    queue = [START_PAGE]
    while queue:
        current = queue.pop()
        if current in reachable or current not in pages:
            continue
        reachable.add(current)
        queue += [t for b in pages[current].buttons for t in b.targets]
    safe = safe_reachable(pages)
    print(f"pages={len(pages)} modal={sum(p.modal for p in pages.values())} buttons={len(buttons)} "
          f"with_target={len(with_targets)} links={sum(links.values())} distinct_targets={len(links)}")
    print(f"no_known_size={sum(b.center is None for b in buttons)} "
          f"off_canvas={sum(b.center is not None and not (0 <= b.center[0] <= 800 and 0 <= b.center[1] <= 600) for b in buttons)}")
    print(f"duplicate_page_names={duplicates}")
    print(f"targets_that_are_not_pages ({len(missing)}): {[(t, links[t]) for t in missing]}")
    unlinked = sorted(p for p in pages if p not in reachable)
    print(f"reachable_by_declared_links={len(reachable)}")
    print(f"not_reachable_by_declared_links ({len(unlinked)}): {unlinked}")
    print(f"crawl_safe_pages={len(safe)} risky_pages={sum(bool(page_risk(p)) for p in pages)}")


def cmd_page(pages, name):
    page = pages[name]
    print(f"{name} modal={page.modal} rect=({page.x:g},{page.y:g},{page.w:g},{page.h:g}) line={page.line} "
          f"risk={page_risk(name)}")
    for b in sorted(page.buttons, key=lambda b: (b.y, b.x)):
        c = f"({b.center[0]:g},{b.center[1]:g})" if b.center else "(no size)"
        problem = button_problem(b, pages)
        print(f"  {c:18} {b.label[:28]:28} -> {','.join(b.targets) or '-':32} "
              f"{'pop ' if b.pops else ''}{'back ' if b.back else ''}{'shared ' if b.shared else ''}"
              f"{'SAFE' if not problem else 'skip: ' + problem}")


def main():
    pages, duplicates = load()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "report":
        cmd_report(pages, duplicates)
    elif cmd == "page":
        cmd_page(pages, sys.argv[2])
    elif cmd == "safe":
        for name, via in safe_reachable(pages).items():
            print(f"{name:36} via {via}")
    elif cmd == "risky":
        for name in sorted(pages):
            if page_risk(name):
                print(f"{name:52} {page_risk(name)}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
