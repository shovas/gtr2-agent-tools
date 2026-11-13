"""Write the setup-page tours as path files for gtr2-nav.py, from built-in tour definitions, checking every step against UIData\\gtr2ui.mnu and the never-press rules.

Navigation only: nothing here loads a session, starts a season or changes saved progress. A step the rules refuse is reported and
the tour is not written. After the listed stops each tour returns to MAIN MENU by the shortest chain of BACK / MAIN MENU buttons.

Usage:   scripts\\.venv\\Scripts\\python.exe -I scripts\\gen-nav-tours.py [--dry-run]
Example: scripts\\.venv\\Scripts\\python.exe -I scripts\\gen-nav-tours.py --dry-run
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "gtr2_ui"))
import menumap  # noqa: E402

MAP_TOGGLE = "@779.5,120.5"      # the Circuit page's map switch
# The Showroom car/stats switch (@446.5,583, PHOTO SHOP STATS) is left out: here the 3D car does not render, so the two
# pages differ only by the TECH SPECS light and page recognition cannot tell them apart. The switch itself works.
BACK_ONE = "<BACK>"
M = "MAIN MENU"

# (file name, comment, entry button on the main menu, [(page, button that opens it from the page before), ...])
SETUP = [
    ("tour_setup_practice", "Open Practice setup pages: summary, circuit, car, showroom, team",
     "APP_BUTTON_GAMEMODESELECT_PRACTICE",
     [("SUMMARY_PRACTICE", None), ("CIRCUIT_SELECT", "CIRCUIT"), ("CIRCUIT_INFO", MAP_TOGGLE), ("CIRCUIT_SELECT", MAP_TOGGLE),
      ("CLASS_SELECT", "CAR"), ("PHOTO SHOP", "SHOWROOM"), ("CLASS_SELECT", BACK_ONE),
      ("TEAM_SELECT", "MODEL")]),
    ("tour_setup_grandprix", "Race Weekend summary", "APP_BUTTON_GAMEMODESELECT_GRANDPRIX", [("SUMMARY_GRANDPRIX", None)]),
    ("tour_setup_24h", "24 Hour event summary, car, team and events", "APP_BUTTON_ENDURANCE_EVENT",
     [("SUMMARY_ENDURANCE", None), ("CLASS_SELECT_24H", "CAR"), ("TEAM_SELECT_24H", "MODEL"), ("SUMMARY_24H", "EVENTS")]),
    ("tour_setup_timetrial", "Time Trial summary", "APP_BUTTON_GAMEMODESELECT_TIMETRIAL", [("SUMMARY_GHOST", None)]),
    ("tour_setup_school", "Driving School and its theory pages", "APP_BUTTON_GAMEMODESELECT_DRIVINGSCHOOL",
     [("DRIVERSTANDING_SCHOOL", None), ("DRIVERSCHOOL_THEORY", "THEORY"), ("DRIVERSCHOOL_ABOUTFIA", "FIA GT"),
      ("DRIVERSCHOOL_ABOUTASSISTS", "ASSISTS")]),
    ("tour_setup_championship", "Championship first page and the Custom tab (never starts a season)",
     "APP_BUTTON_GAMEMODESELECT_CHAMPIONSHIP",
     [("RESUMEORNEW_CHAMP", None), ("CUSTOM_CHAMP", "CUSTOM")]),
]


def way_home(pages, page):
    """Shortest chain of (page, label, target) from `page` to MAIN MENU through BACK / MAIN MENU buttons."""
    seen, queue = {page: None}, [page]
    while queue:
        cur = queue.pop(0)
        if cur == M:
            break
        for b in pages[cur].buttons:
            if b.caption.upper() not in ("BACK", "MAIN MENU") or menumap.never_press(b):
                continue
            for t in b.targets:
                if t in pages and t not in seen:
                    seen[t] = (cur, b.caption)
                    queue.append(t)
    if M not in seen:
        return None
    chain, cur = [], M
    while seen[cur]:
        prev, cap = seen[cur]
        chain.append((prev, cap, cur))
        cur = prev
    return chain[::-1]


def build(pages, entry, stops):
    steps, problems = [], []

    def add(page, label, target):
        if not label.startswith("@"):
            try:
                b = menumap.find_button(pages, page, label)
            except KeyError as e:
                problems.append("%s | %s: %s" % (page, label, e))
                return
            why = menumap.never_press(b)
            if why:
                problems.append("%s | %s refused: %s" % (page, label, why))
                return
            if b.targets and target not in b.targets:    # a BACK with no map target returns to the page before
                problems.append("%s | %s leads to %s, not %s" % (page, label, sorted(b.targets), target))
                return
        steps.append("%s | %s | %s" % (page, label, target))

    add(M, entry, stops[0][0])
    for (prev, _), (page, label) in zip(stops, stops[1:]):
        if label == BACK_ONE:
            add(prev, "BACK", page)
        else:
            add(prev, label, page)
    last = stops[-1][0] if stops[-1][1] != BACK_ONE else stops[-1][0]
    home = way_home(pages, last)
    if home is None:
        problems.append("no BACK chain from %s to %s" % (last, M))
    else:
        for page, cap, target in home:
            add(page, cap, target)
    return steps, problems


INFO = "@273.5,66"       # the track info button, which shares its name with another gizmo
TT_TAB = "@614,403"      # Time Trial: the tab that opens the lap list
MONITOR_VIEW = "@397,358"
# Session tours: they LOAD a session (the only way in is the setup page's CONTINUE) and leave it. Nothing presses DRIVE, ATTEMPT,
# TRAIN or OBSERVE, so the car stays in the garage. Run only with gtr2-nav.py path --session-step.
# (file, comment, entry, summary page, load button, [(page, button from the previous stop), ...], leave (page, button))
SESSIONS = [
    ("tour_session_timetrial", "Time Trial: load the session, visit the monitor, timing, track info and lap list, leave",
     "APP_BUTTON_GAMEMODESELECT_TIMETRIAL", "SUMMARY_GHOST", "CONTINUE",
     [("MONITOR_TIMETRIAL", None), ("FULLGRID_TIMETRIAL", "TIMING"), ("TRACKINFO_TIMETRIAL", INFO),
      ("MONITOR_TIMETRIAL", "GRID"), ("TIMETRIAL_SELECT", TT_TAB)],
     ("TIMETRIAL_SELECT", "LEAVE EVENT"), None, None),
    ("tour_session_practice", "Open Practice: load the session, visit monitor, options, controls, timing, track info and garage pages, leave",
     "APP_BUTTON_GAMEMODESELECT_PRACTICE", "SUMMARY_PRACTICE", "CONTINUE",
     [("MONITOR_SINGLE", None), ("GRIDMONITOR_NOLIST", MONITOR_VIEW), ("MONITOR_SINGLE", "BACK"),
      ("OPTIONS_BASIC_SIMDYN", "OPTIONS"), ("OPTIONS_DETAIL_SIMDYN", "VIDEO"), ("OPTIONS_AUDIO_SIMDYN", "AUDIO"),
      ("OPTIONS_ADVANCED_SIMDYN", "ADVANCED"), ("OPTIONS_ASSISTS_SIMDYN", "REALISM"),
      ("CONTROL_KEYS_DYNAMIC", "CONTROLS"), ("CONTROL_ONE_DYNAMIC", "ADVANCED"), ("CONTROL_FORCE_DYNAMIC", "FORCE"),
      ("MONITOR_SINGLE", "GRID"), ("FULLGRID_SINGLE", "TIMING"), ("SECTORGRID_SINGLE", "SECTOR"),
      ("FULLGRID_SINGLE", "GENERAL"), ("TRACKINFO_SINGLE", INFO), ("GARAGEPAGE", "GARAGE"),
      ("GEARSGARAGE", "SETUP ONE"), ("SUSPENSIONGARAGE", "SETUP TWO")],
     ("MONITOR_SINGLE", "LEAVE TRACK"), None, None),
    # START on the Driving School page loads the selected technique's track (type APP_BUTTON_CIRCUITSELECT) and shows its
    # challenge list; this tour looks at that and the track info page and leaves. It never presses ATTEMPT, TRAIN or OBSERVE.
    # Leaving a lesson returns to the Driving School page, not the main menu.
    ("tour_session_school", "Driving School: load the selected technique's track (challenge list), track info, leave",
     "APP_BUTTON_GAMEMODESELECT_DRIVINGSCHOOL", "DRIVERSTANDING_SCHOOL", "START",
     [("MONITOR_SCHOOL", None), ("TRACKINFO_SCHOOL", INFO), ("MONITOR_SCHOOL", "TECHNIQUE")],
     ("MONITOR_SCHOOL", "LEAVE TRACK"), "DRIVERSTANDING_SCHOOL", None),
]
# Generic page names in the menu file that the game resolves to the current mode's own page at run time.
GENERIC = {"MONITORPAGE", "MONITOR", "FULLGRID", "SECTORGRID", "TRACKINFO", "OPTIONS_BASIC_DYNAMIC", "GRIDMONITOR"}


def build_session(pages, entry, summary, load, stops, leave, lands_on=None, confirm_ref=None):
    """Steps for a session tour; the load and leave buttons are checked against menumap.session_step_ok."""
    steps, problems = [], []

    def add(page, label, target, session=False):
        if not label.startswith("@"):
            try:
                b = menumap.find_button(pages, page, label)
            except KeyError as e:
                problems.append("%s | %s: %s" % (page, label, e))
                return
            if session:
                if not menumap.session_step_ok(b, page):
                    problems.append("%s | %s is not an allowed session step (type %s)" % (page, label, b.kind))
                    return
            elif menumap.never_press(b):
                problems.append("%s | %s refused: %s" % (page, label, menumap.never_press(b)))
                return
            if b.targets and target not in b.targets and not set(b.targets) <= GENERIC:
                problems.append("%s | %s leads to %s, not %s" % (page, label, sorted(b.targets), target))
                return
        steps.append("%s | %s | %s" % (page, label, target))

    add(M, entry, summary)
    add(summary, load, stops[0][0], session=True)
    for (prev, _), (page, label) in zip(stops, stops[1:]):
        add(prev, "BACK" if label == BACK_ONE else label, page)
    leave_page, leave_label = leave
    # the tour leaves from the last stop's page: GRID/back to the page that has the leave button when it differs
    last = stops[-1][0]
    if last != leave_page:
        add(last, "GRID", leave_page)
    add(leave_page, leave_label, "CONFIRM_EXIT", session=True)
    if confirm_ref:      # this mode's confirm popup has its own reference (it is drawn over the mode's page)
        steps[-1] = steps[-1].rsplit(" | ", 1)[0] + " | " + confirm_ref
    add("CONFIRM_EXIT", "APP_BUTTON_BACKTOMAIN", lands_on or M)
    if confirm_ref:
        # the source of the confirm step is the popup's reference, the button still comes from the CONFIRM_EXIT map page
        steps[-1] = "CONFIRM_EXIT=%s | APP_BUTTON_BACKTOMAIN | %s" % (confirm_ref, lands_on or M)
    if lands_on:
        add(lands_on, "BACK", M)
    return steps, problems


CONTEXT_STOPS = [("OPTIONS_BASIC_{}", "OPTIONS"), ("OPTIONS_DETAIL_{}", "VIDEO"), ("OPTIONS_AUDIO_{}", "AUDIO"),
                 ("OPTIONS_ADVANCED_{}", "ADVANCED"), ("OPTIONS_ASSISTS_{}", "REALISM"),
                 ("CONTROL_KEYS_{}", "CONTROLS"), ("CONTROL_ONE_{}", "ADVANCED"), ("CONTROL_FORCE_{}", "FORCE")]
STOPS = lambda suffix: [(stop.format(suffix), label, None) for stop, label in CONTEXT_STOPS]  # noqa: E731
IN_PROGRESS = "RESUMEORNEW_CHAMP IN PROGRESS"     # the first page once a season is under way: same menu page, another look
BASE_PAGE = {IN_PROGRESS: "RESUMEORNEW_CHAMP"}
NEW_SEASON_WARNING = "CHAMPIONSHIP START NEW SEASON WANING"   # [sic] in the menu file
CANCEL_POPUP = "@137,300"                                    # the X on the game's yes/no popups
# (file, comment, [(page, button from the previous page, flag), ...]); flag "season" marks a step that starts a season. Each tour
# presses BACK from its last page to return to the main menu.
CHAMPS = [
    ("tour_champ_preseason", "Championship pre-season: Custom tab, then the Options, Realism and Controls pages before a season exists",
     # The RESTART on the Custom tab (-> TEAM_SELECT_CUSTOMCHAMP, then BACK) is left out: every custom championship is
     # locked here until 3 Driving School challenges are complete, which greys out START. Add it back after unlocking one.
     [("RESUMEORNEW_CHAMP", None, None), ("CUSTOM_CHAMP", "CUSTOM", None)] + STOPS("PRECHAMP")),
    ("tour_champ_season", "Championship season: STARTS A NEW SEASON, team, round info, standings, in-season Options and Controls, cancel a restart",
     [("RESUMEORNEW_CHAMP", None, None), ("SUMMARY_CHAMP", "RESTART", "season"), ("TEAM_SELECT_CHAMP", "CAR", None),
      ("SUMMARY_CHAMP", "SUMMARY", None), ("NEXTROUND_CHAMP", "CONTINUE", "season"), ("DRIVERSTANDING_CHAMP", "STANDINGS", None),
      ("TEAMSTANDINGS_CHAMP", "TEAM", None), ("NEXTROUND_CHAMP", "ROUND INFO", None)] + STOPS("CHAMP")
     + [("NEXTROUND_CHAMP", "ROUND INFO", None), (IN_PROGRESS, "LEAVE CHAMPIONSHIP", None),
        (NEW_SEASON_WARNING, "RESTART", "season"), (IN_PROGRESS, CANCEL_POPUP, None)]),
]


def build_champ(pages, stops):
    """Steps for a championship tour. A step's source is the previous stop (an alias page maps to its menu page for the buttons)."""
    steps, problems = [], []
    base = lambda pg: BASE_PAGE.get(pg, pg)  # noqa: E731

    def add(src, label, dest, flag):
        shown_src = src if base(src) == src else "%s=%s" % (base(src), src)
        if not label.startswith("@"):
            try:
                b = menumap.find_button(pages, base(src), label)
            except KeyError as e:
                problems.append("%s | %s: %s" % (src, label, e))
                return
            blocked = menumap.never_press(b)
            if blocked and not (flag == "season" and b.kind in menumap.SEASON_STEP_TYPES):
                problems.append("%s | %s refused: %s%s" % (src, label, blocked, " (flagged season, but kind %s is not a season kind)" % b.kind if flag else ""))
                return
            # a RESTART with a season in progress opens the "progress will be lost" popup instead of the map's target
            if b.targets and base(dest) not in b.targets and not set(b.targets) <= GENERIC and dest != NEW_SEASON_WARNING:
                problems.append("%s | %s leads to %s, not %s" % (src, label, sorted(b.targets), dest))
                return
        steps.append("%s | %s | %s" % (shown_src, label, dest))

    add(M, "APP_BUTTON_GAMEMODESELECT_CHAMPIONSHIP", stops[0][0], None)
    for (prev, _, _), (page, label, flag) in zip(stops, stops[1:]):
        add(prev, "BACK" if label == BACK_ONE else label, page, flag)
    add(stops[-1][0], "BACK", M, None)
    return steps, problems



# ---- the Options "MULTIPLAYER" tab pages (named OPTIONS_GAME_*, plain settings pages) for every mode's copy of the Options pages
# (mode entry, its first page or None, suffix of its Options pages). Pure navigation.
GAME_CONTEXTS = [
    ("tour_options_game_main", None, None, "SIMMAIN"),
    ("tour_options_game_school", "APP_BUTTON_GAMEMODESELECT_DRIVINGSCHOOL", "DRIVERSTANDING_SCHOOL", "SCHOOL"),
    ("tour_options_game_practice", "APP_BUTTON_GAMEMODESELECT_PRACTICE", "SUMMARY_PRACTICE", "SUMMARY"),
    ("tour_options_game_24h", "APP_BUTTON_ENDURANCE_EVENT", "SUMMARY_ENDURANCE", "24H"),
    ("tour_options_game_prechamp", "APP_BUTTON_GAMEMODESELECT_CHAMPIONSHIP", "CUSTOM_CHAMP", "PRECHAMP"),
]


def build_game(pages, entry, start, suffix):
    steps, problems = [], []

    def add(src, label, dest):
        try:
            b = menumap.find_button(pages, src, label)
        except KeyError as e:
            problems.append("%s | %s: %s" % (src, label, e))
            return
        if menumap.never_press(b):
            problems.append("%s | %s refused: %s" % (src, label, menumap.never_press(b)))
            return
        if b.targets and dest not in b.targets and not set(b.targets) <= GENERIC:
            problems.append("%s | %s leads to %s, not %s" % (src, label, sorted(b.targets), dest))
            return
        steps.append("%s | %s | %s" % (src, label, dest))

    basic, game = "OPTIONS_BASIC_" + suffix, "OPTIONS_GAME_" + suffix
    if entry is None:
        add(M, "OPTIONS", basic)
    else:
        first = "RESUMEORNEW_CHAMP" if suffix == "PRECHAMP" else start
        add(M, entry, first)
        if suffix == "PRECHAMP":
            add("RESUMEORNEW_CHAMP", "CUSTOM", start)
        add(start, "OPTIONS", basic)
    add(basic, "MULTIPLAYER", game)
    add(game, "GAME", basic)
    home = way_home(pages, basic)
    if home is None:
        problems.append("no BACK chain from %s" % basic)
    else:
        for page, cap, target in home:
            add(page, cap, target)
    return steps, problems


# ---- popup tours: open a save/delete/rename/load/exit popup, check it, cancel it with the X. Run with --popup-step (and --session-step
# for the ones that load a session). A path can only cancel a popup, never confirm (gtr2-nav.py refuses a press on the tick side).
X = "@137,300"
# JOY1 and JOY3 ("No Controller Detected") don't react without a device, so CONFIRM_CONTROL1 and 3 can't be opened here; the popup they
# open is the same "You will lose any controller changes you have made. Continue?" dialog as the other two.
CTRL_NAMES = [("KEYBOARD", "CONFIRM_KEYBOARD"), ("Logitech WingMan Attack 2", "CONFIRM_CONTROL2")]
POPUP_TOURS = [
    ("tour_popup_menu", "Controller-confirm, Exit, Profiles (new, delete) and Replay (rename, delete) popups from the main-menu pages; each is cancelled",
     "popup", [
         (M, "CONTROLS", "CONTROL_KEYS_SIMMAIN")]
     + [step for name, pop in CTRL_NAMES for step in (("CONTROL_KEYS_SIMMAIN", name, pop), (pop, X, "CONTROL_KEYS_SIMMAIN"))]
     + [("CONTROL_KEYS_SIMMAIN", "MAIN MENU", M),
        (M, "EXIT", "CONFIRM_TO_WINDOWS"), ("CONFIRM_TO_WINDOWS", X, M),
        (M, "PROFILES", "PROFILE_SELECT_SIMMAIN"),
        ("PROFILE_SELECT_SIMMAIN", "NEW", "PROFILE ADD"), ("PROFILE ADD", X, "PROFILE_SELECT_SIMMAIN"),
        # DELETE (-> DELETE PROFILE) is greyed while the only profile is the active one, so it is not in the tour.
        ("PROFILE_SELECT_SIMMAIN", "REPLAY", "REPLAY_STUDIO_SIMMAIN"),
        ("REPLAY_STUDIO_SIMMAIN", "@316,257", "REPLAY_STUDIO_SIMMAIN"),
        ("REPLAY_STUDIO_SIMMAIN", "RENAME", "RENAME REPLAY"), ("RENAME REPLAY", X, "REPLAY_STUDIO_SIMMAIN"),
        ("REPLAY_STUDIO_SIMMAIN", "DELETE", "DELETE REPLAY"), ("DELETE REPLAY", X, "REPLAY_STUDIO_SIMMAIN"),
        ("REPLAY_STUDIO_SIMMAIN", "MAIN MENU", M)]),
    ("tour_popup_session_timetrial", "Time Trial session: lap list rename and delete popups; each is cancelled",
     "popup+session", [
         (M, "APP_BUTTON_GAMEMODESELECT_TIMETRIAL", "SUMMARY_GHOST"), ("SUMMARY_GHOST", "CONTINUE", "MONITOR_TIMETRIAL"),
         ("MONITOR_TIMETRIAL", "@614,403", "TIMETRIAL_SELECT"), ("TIMETRIAL_SELECT", "@181,185", "TIMETRIAL_SELECT"),
         ("TIMETRIAL_SELECT", "RENAME", "RENAME TIMETRIAL"), ("RENAME TIMETRIAL", X, "TIMETRIAL_SELECT"),
         # SAVE (-> SAVE TIMETRIAL) is greyed until a lap has been driven, so it is not in the tour.
         # LOAD opens no popup: it loads the selected lap into the list's detail pane, so it is not in the tour.
         ("TIMETRIAL_SELECT", "DELETE", "DELETE TIMETRIAL"), ("DELETE TIMETRIAL", X, "TIMETRIAL_SELECT"),
         # SAVE GAME does nothing in a Time Trial session (it is for sessions with saved progress), so it is not in the tour.
         ("TIMETRIAL_SELECT", "LEAVE EVENT", "CONFIRM_EXIT"), ("CONFIRM_EXIT", "APP_BUTTON_BACKTOMAIN", M)]),
    ("tour_popup_session_practice", "Open Practice: Load Last Saved popup (cancelled), Save Game (SAVES the game; its notice is closed with the tick), garage setup save/delete popups (cancelled)",
     "popup+session", [
         (M, "APP_BUTTON_GAMEMODESELECT_PRACTICE", "SUMMARY_PRACTICE"),
         ("SUMMARY_PRACTICE", "LOAD LAST SAVED", "LOAD GAME"), ("LOAD GAME", X, "SUMMARY_PRACTICE"),
         ("SUMMARY_PRACTICE", "CONTINUE", "MONITOR_SINGLE"),
         ("MONITOR_SINGLE", "SAVE GAME", "SAVEGAME"), ("SAVEGAME", "@660,300", "MONITOR_SINGLE"),     # saves the game at once; the notice has a tick only
         ("MONITOR_SINGLE", "GARAGE", "GARAGEPAGE"),
         ("GARAGEPAGE", "SAVE", "SAVE GARAGE SETUP"), ("SAVE GARAGE SETUP", X, "GARAGEPAGE"),
         # DELETE (-> DELETE GARAGE SETUP) is greyed until a setup has been saved, so it is not in the tour.
         ("GARAGEPAGE", "LEAVE EVENT", "CONFIRM_EXIT"), ("CONFIRM_EXIT", "APP_BUTTON_BACKTOMAIN", M)]),
]

# LAN multiplayer (the Local Network games list and the pages around it). Needs --lan-step and --popup-step. Never presses HOST, JOIN, REFRESH,
# STOP or the Add-server confirm; leaves through the Leave Multiplayer popup (its tick only leaves the empty lobby).
MP = "SUMMARY_MPLIST"
POPUP_TOURS.append(
    ("tour_lan", "LAN multiplayer: games list, Add IP address popup (cancelled), the multiplayer copies of the Options and Controls pages, leave",
     "lan+popup", [
         (M, "APP_BUTTON_MP_DIRECT", MP),
         (MP, "ADD IP ADDRESS", "MP_ADDGAME"), ("MP_ADDGAME", X, MP),
         (MP, "OPTIONS", "OPTIONS_BASIC_MULTIPLAYER"), ("OPTIONS_BASIC_MULTIPLAYER", "VIDEO", "OPTIONS_DETAIL_MULTIPLAYER"),
         ("OPTIONS_DETAIL_MULTIPLAYER", "AUDIO", "OPTIONS_AUDIO_MULTIPLAYER"),
         ("OPTIONS_AUDIO_MULTIPLAYER", "ADVANCED", "OPTIONS_ADVANCED_MULTIPLAYER"),
         ("OPTIONS_ADVANCED_MULTIPLAYER", "MULTIPLAYER", "OPTIONS_GAME_MULTIPLAYER"),
         ("OPTIONS_GAME_MULTIPLAYER", "REALISM", "OPTIONS_ASSISTS_MULTIPLAYER"),
         ("OPTIONS_ASSISTS_MULTIPLAYER", "CONTROLS", "CONTROL_KEYS_MULTIPLAYER"),
         ("CONTROL_KEYS_MULTIPLAYER", "ADVANCED", "CONTROL_ONE_MULTIPLAYER"),
         ("CONTROL_ONE_MULTIPLAYER", "FORCE", "CONTROL_FORCE_MULTIPLAYER"),
         ("CONTROL_FORCE_MULTIPLAYER", "LEAVE MULTIPLAYER", "LEAVE LOBBY"), ("LEAVE LOBBY", "@660,300", M)]))

# LAN host SETUP pages: the games list's HOST opens them (--host-step allows only that press); the setup page's own HOST (which would create the game) is never in a path.
H = "SUMMARY_MPCLIENT"
POPUP_TOURS.append(
    ("tour_lan_host", "LAN host setup pages (nothing is hosted): settings, car class and model, circuit and its info, restriction, and the host copies of Options and Controls",
     "lan+host+popup", [
         (M, "APP_BUTTON_MP_DIRECT", MP), (MP, "HOST", H),
         (H, "CAR", "CLASS_SELECT_HOST"), ("CLASS_SELECT_HOST", "MODEL", "TEAM_SELECT_HOST"),
         ("TEAM_SELECT_HOST", "CIRCUIT", "CIRCUIT_SELECT_HOST"), ("CIRCUIT_SELECT_HOST", "@779.5,120.5", "CIRCUIT_INFO_HOST"),
         ("CIRCUIT_INFO_HOST", "@779.5,120.5", "CIRCUIT_SELECT_HOST"),
         ("CIRCUIT_SELECT_HOST", "RESTRICTION", "SUMMARY_MPSETTINGS"),
         ("SUMMARY_MPSETTINGS", "OPTIONS", "OPTIONS_BASIC_HOST"), ("OPTIONS_BASIC_HOST", "VIDEO", "OPTIONS_DETAIL_HOST"),
         ("OPTIONS_DETAIL_HOST", "AUDIO", "OPTIONS_AUDIO_HOST"), ("OPTIONS_AUDIO_HOST", "ADVANCED", "OPTIONS_ADVANCED_HOST"),
         ("OPTIONS_ADVANCED_HOST", "MULTIPLAYER", "OPTIONS_GAME_HOST"), ("OPTIONS_GAME_HOST", "REALISM", "OPTIONS_ASSISTS_HOST"),
         ("OPTIONS_ASSISTS_HOST", "CONTROLS", "CONTROL_KEYS_HOST"), ("CONTROL_KEYS_HOST", "ADVANCED", "CONTROL_ONE_HOST"),
         ("CONTROL_ONE_HOST", "FORCE", "CONTROL_FORCE_HOST"),
         ("CONTROL_FORCE_HOST", "BACK", MP),
         (MP, "LEAVE MULTIPLAYER", "LEAVE LOBBY"), ("LEAVE LOBBY", "@660,300", M)]))


def build_popup(pages, steps_in):
    steps, problems = [], []
    for src, label, dest in steps_in:
        if not label.startswith("@"):
            try:
                b = menumap.find_button(pages, src, label)
            except KeyError as e:
                problems.append("%s | %s: %s" % (src, label, e))
                continue
            blocked = menumap.never_press(b) or ("EXIT" if "EXIT" in b.label.upper() else None)
            allowed = menumap.session_step_ok(b, src) or dest in POPUP_NAMES
            if blocked and not allowed:
                problems.append("%s | %s refused: %s" % (src, label, blocked))
                continue
            if b.targets and dest not in b.targets and not set(b.targets) <= GENERIC:
                problems.append("%s | %s leads to %s, not %s" % (src, label, sorted(b.targets), dest))
                continue
        steps.append("%s | %s | %s" % (src, label, dest))
    return steps, problems


POPUP_NAMES = {"SUMMARY_MPCLIENT", "MP_ADDGAME", "LEAVE LOBBY", "CONFIRM_KEYBOARD", "CONFIRM_CONTROL1", "CONFIRM_CONTROL2", "CONFIRM_CONTROL3", "CONFIRM_TO_WINDOWS", "PROFILE ADD",
               "DELETE PROFILE", "RENAME REPLAY", "DELETE REPLAY", "RENAME TIMETRIAL", "SAVE TIMETRIAL", "LOAD TIMETRIAL",
               "DELETE TIMETRIAL", "SAVE GARAGE SETUP", "DELETE GARAGE SETUP", "SAVEGAME", "LOAD GAME"}


def write_tour(dry, name, header, steps):
    text = header + "# Format: PAGE | LABEL | EXPECTED PAGE   (a label '@x,y' is a canvas position)\n" + "\n".join(steps) + "\n"
    print("%s: %d steps%s" % (name, len(steps), " (dry run)" if dry else ""))
    if not dry:
        (HERE / "nav_paths" / (name + ".txt")).write_text(text, encoding="utf-8", newline="\n")


def main():
    dry = "--dry-run" in sys.argv
    pages, _ = menumap.load()
    bad = 0
    gen = ("# Generated by scripts/gen-nav-tours.py, each button checked against\n"
           "# UIData/gtr2ui.mnu. Start on MAIN MENU.\n")
    for name, comment, entry, stops in SETUP:
        steps, problems = build(pages, entry, stops)
        if problems:
            bad += 1
            print("%s: NOT written" % name)
            for p in problems:
                print("   -", p)
            continue
        write_tour(dry, name, "# %s\n%s# Navigation only: starts no session and saves nothing.\n" % (comment, gen), steps)
    for name, comment, entry, summary, load, stops, leave, lands_on, confirm_ref in SESSIONS:
        steps, problems = build_session(pages, entry, summary, load, stops, leave, lands_on, confirm_ref)
        if problems:
            bad += 1
            print("%s: NOT written" % name)
            for p in problems:
                print("   -", p)
            continue
        write_tour(dry, name, "# %s\n%s# SESSION TOUR: loads a session. Run only with:  gtr2-nav.py path --session-step FILE\n"
                   "# (a plain run refuses the load button). Presses no DRIVE, ATTEMPT, TRAIN or OBSERVE: the car stays in the garage.\n" % (comment, gen), steps)
    for name, comment, stops in CHAMPS:
        steps, problems = build_champ(pages, stops)
        if problems:
            bad += 1
            print("%s: NOT written" % name)
            for p in problems:
                print("   -", p)
            continue
        write_tour(dry, name, "# %s\n%s# SEASON TOUR: starts or changes championship progress. Run only with:  gtr2-nav.py path --season-step FILE\n"
                   "# (a plain run refuses). Revert the profile afterwards with git (UserData/<profile>, Championships). 'A=B' = buttons of map page A, screen checked against reference B.\n" % (comment, gen), steps)
    for name, entry, start, suffix in GAME_CONTEXTS:
        steps, problems = build_game(pages, entry, start, suffix)
        if problems:
            bad += 1
            print("%s: NOT written" % name)
            for p in problems:
                print("   -", p)
            continue
        write_tour(dry, name, "# Options 'MULTIPLAYER' tab (OPTIONS_GAME_%s): a plain settings page. Navigation only.\n%s" % (suffix, gen), steps)
    for name, comment, flags, steps_in in POPUP_TOURS:
        steps, problems = build_popup(pages, steps_in)
        if problems:
            bad += 1
            print("%s: NOT written" % name)
            for p in problems:
                print("   -", p)
            continue
        write_tour(dry, name, "# %s\n%s# POPUP TOUR: run with  gtr2-nav.py path --%s-step FILE  (opens popups and cancels them with the X; never confirms).\n" % (
            comment, gen, flags.replace("+", "-step --")), steps)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
