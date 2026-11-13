"""Offline tests for the navigation tool's safety rules. No game, no screen and no mouse is touched.

Purpose: the opt-in flags of gtr2-nav.py (--session-step, --season-step, --drive-step, --popup-step, --lan-step, --host-step) each unlock a
narrow set of blocked buttons, and some buttons (finish race, restart race, exit, join, host a game, profile and save-load buttons) must never be
pressed by a path whatever the flags. These tests try every button of the menu map against every flag and check that nothing else gets through,
that every tour in scripts/nav_paths only uses buttons its own header flags allow, and that the input helpers behave (a drag always releases
the mouse). Written for this tool.
Usage:   scripts\\.venv\\Scripts\\python.exe -I scripts\\test_nav_guards.py          (about 3 s)
Example: scripts\\.venv\\Scripts\\python.exe -I scripts\\test_nav_guards.py -v NeverUnlocked
Any input call during a test (mouse, key, drag) raises: a guard that fails open can't click anything.
"""
import importlib.util
import re
import sys
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS / "gtr2_ui"))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


nav = load("gtr2_nav", "gtr2-nav.py")
suite = load("gtr2_nav_suite", "gtr2-nav-suite.py")
menumap, coords = nav.menumap, nav.coords
PAGES, _DUPS = menumap.load()
FLAGS = ("SESSION_OK", "SEASON_OK", "POPUP_OK", "LAN_OK", "HOST_OK", "DRIVE_OK", "SETTING_OK")


class Forbidden(AssertionError):
    pass


def forbid(*_a, **_k):
    raise Forbidden("an input function was called")


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = {n: getattr(nav, n) for n in ("press", "move_to", "mouse", "press_key", "drag", "ensure_focus")}
        for n in ("press", "move_to", "mouse", "press_key", "drag", "ensure_focus"):
            setattr(nav, n, forbid)
        self.set_flags()

    def tearDown(self):
        for n, f in self.saved.items():
            setattr(nav, n, f)
        self.set_flags()

    @staticmethod
    def set_flags(*on):
        for n in FLAGS:
            getattr(nav, n)[0] = n in on

    @staticmethod
    def blocked():
        """Every (page, button) of the menu map that the plain rules refuse."""
        return [(p.name, b) for p in PAGES.values() for b in p.buttons if menumap.never_press(b)]

    @staticmethod
    def policy(page, b):
        return nav.step_policy(b, page, [str(t) for t in b.targets])


class Responsive(unittest.TestCase):
    def test_busy_game_is_not_responsive_and_live_one_is(self):
        real = nav.user32
        class Fake:
            def __init__(self, ok): self.ok = ok; self.SendMessageTimeoutW = self
            def __call__(self, *a): return 1 if self.ok else 0
        try:
            nav.GAME[0] = 1
            nav.user32 = Fake(False)
            self.assertFalse(nav.game_responsive(0, 0, probes=2))
            nav.user32 = Fake(True)
            self.assertTrue(nav.game_responsive(0, 0, probes=2))
        finally:
            nav.user32 = real


class NoFlags(Base):
    def test_every_flag_starts_off(self):
        self.assertEqual([n for n in FLAGS if getattr(nav, n)[0]], [])

    def test_every_blocked_button_is_refused_without_flags(self):
        loose = [(p, b.label) for p, b in self.blocked() if self.policy(p, b)[0] is None]
        self.assertEqual(loose, [])

    def test_there_are_blocked_buttons_to_test(self):
        self.assertGreater(len(self.blocked()), 100)


class EachFlagUnlocksOnlyItsOwnKinds(Base):
    def unlocked(self, flag):
        self.set_flags(flag)
        return {(p, b.kind, b.label) for p, b in self.blocked() if self.policy(p, b)[0] is None}

    def test_session_step_unlocks_loading_and_leaving_a_track_only(self):
        got = self.unlocked("SESSION_OK")
        self.assertTrue(got)
        for page, kind, label in got:
            self.assertTrue(kind in menumap.SESSION_STEP_TYPES or (page in menumap.SCHOOL_LEAVE_PAGES and label.upper() == "LEAVE TRACK"), (page, kind, label))

    def test_season_step_unlocks_the_season_kinds_only(self):
        got = self.unlocked("SEASON_OK")
        self.assertTrue(got)
        self.assertEqual({k for _p, k, _l in got} - menumap.SEASON_STEP_TYPES, set())

    def test_drive_step_unlocks_only_the_post_race_continue_in_a_path(self):
        got = self.unlocked("DRIVE_OK")
        self.assertEqual({k for _p, k, _l in got}, {"APP_BUTTON_POSTRACENAVIGATION"})

    def test_drive_and_next_session_are_never_pressed_by_a_plain_path_step(self):
        self.set_flags("DRIVE_OK", "SESSION_OK", "SEASON_OK")
        for kind in ("APP_BUTTON_TOREALTIME", "APP_BUTTON_NEXTSESSION"):
            self.assertIn(kind, menumap.DRIVE_STEP_TYPES)
            hits = [(p, b) for p, b in self.blocked() if b.kind == kind]
            self.assertTrue(hits)
            for page, b in hits:
                self.assertIsNotNone(self.policy(page, b)[0], (page, kind))

    def test_goto_one_refuses_drive_before_touching_the_game(self):
        self.set_flags("DRIVE_OK", "SESSION_OK", "SEASON_OK")
        ok, msg = nav.goto_one(0, 0, PAGES, "MONITOR_SINGLE", "DRIVE")
        self.assertFalse(ok)
        self.assertTrue(msg.startswith("refused"), msg)


class NeverUnlocked(Base):
    """Buttons no combination of flags may let a path press."""
    KINDS = {"APP_FINISHRACE_BUTTON", "APP_RESTARTRACEBUTTON", "APP_RESTARTRACECONFIRMBUTTON", "APP_BUTTON_EXITGAME",
             "APP_BUTTON_ADDPROFILE", "APP_BUTTON_LOADPROFILE", "APP_BUTTON_CH_RESUMESEASON",
             "APP_BUTTON_MULTIPLAYER_JOIN", "APP_BUTTON_GARAGE_TODELETESETUP", "APP_BUTTON_GARAGE_LOADSETUP",
             "APP_BUTTON_GARAGE_LOADDEFAULT", "APP_BUTTON_GARAGE_SETSETUPASDEFAULT", "APP_BUTTON_GARAGE_ONLINE_EXCHANGE",
             "APP_BUTTON_GARAGE_DATAACQUISITIONTOGGLE"}

    def test_with_every_flag_on(self):
        seen = 0
        for with_popup in (False, True):
            self.set_flags(*[f for f in FLAGS if with_popup or f != "POPUP_OK"])
            for page, b in ((p, b) for p in PAGES.values() for b in p.buttons if b.kind in self.KINDS):
                seen += 1
                problem = self.policy(page.name, b)[0]
                targets = [str(t) for t in b.targets]
                # --popup-step opens a popup (delete, load, set as default), which a path can only cancel; the button itself acts
                # only after the popup's tick, and that is refused (test_a_confirm_tick_position_is_refused...)
                opens_only_popups = bool(targets) and all(t in coords.POPUP_PAGES for t in targets) and not nav.net_risk(page.name)
                if with_popup and opens_only_popups:
                    continue
                self.assertIsNotNone(problem, (page.name, b.kind, b.label, targets, with_popup))
        self.assertGreater(seen, 20)

    def test_the_kinds_are_really_in_the_blocked_set(self):
        for kind in self.KINDS - {"APP_BUTTON_MULTIPLAYER_JOIN", "APP_BUTTON_GARAGE_ONLINE_EXCHANGE"}:
            self.assertIn(kind, menumap.NEVER_PRESS_TYPES, kind)

    def test_exit_buttons_are_refused_unless_they_only_open_the_exit_popup(self):
        self.set_flags(*FLAGS)
        for p in PAGES.values():
            for b in p.buttons:
                if "EXIT" in b.label.upper() and b.kind not in ("GENERIC_BUTTON_NORMAL", "APP_BUTTON_NAV", "APP_BUTTON_PAGEFADE"):
                    targets = [str(t) for t in b.targets]
                    if not (targets and all(t in coords.POPUP_PAGES for t in targets)):
                        self.assertIsNotNone(self.policy(p.name, b)[0], (p.name, b.label))


class PositionSteps(Base):
    """A path step given as '@x,y' gets the rules of the mapped button at that position: coordinates are no way round the guards."""

    def test_every_blocked_button_is_refused_by_its_position_without_flags(self):
        hits = 0
        for page, b in self.blocked():
            if not b.center:
                continue
            hits += 1
            problem = nav.position_policy(PAGES, page, b.center, [str(t) for t in b.targets])[0]
            self.assertIsNotNone(problem, (page, b.label, b.center))
        self.assertGreater(hits, 100)

    def test_the_new_season_warnings_confirm_is_refused_by_position_but_unlocked_by_the_season_flag(self):
        page = "CHAMPIONSHIP START NEW SEASON WANING"
        confirm = [b for b in PAGES[page].buttons if b.kind == "APP_CH_CUSTOMSTART"]
        self.assertEqual(len(confirm), 1)
        spot, want = confirm[0].center, ["RESUMEORNEW_CHAMP"]
        self.assertIsNotNone(nav.position_policy(PAGES, page, spot, want)[0])
        self.set_flags("SEASON_OK")
        self.assertIsNone(nav.position_policy(PAGES, page, spot, want)[0])
        self.set_flags("SESSION_OK", "DRIVE_OK", "LAN_OK")
        self.assertIsNotNone(nav.position_policy(PAGES, page, spot, want)[0])

    def test_goto_one_refuses_a_blocked_position_before_touching_the_game(self):
        page = "CHAMPIONSHIP START NEW SEASON WANING"
        confirm = [b for b in PAGES[page].buttons if b.kind == "APP_CH_CUSTOMSTART"][0]
        ok, msg = nav.goto_one(0, 0, PAGES, page, "@%g,%g" % confirm.center, "RESUMEORNEW_CHAMP")
        self.assertFalse(ok)
        self.assertTrue(msg.startswith("refused"), msg)

    def test_a_position_on_nothing_mapped_is_allowed(self):
        self.assertIsNone(nav.position_policy(PAGES, "REPLAY_STUDIO_SIMMAIN", (316.0, 257.0), ["REPLAY_STUDIO_SIMMAIN"])[0])


class PopupStep(Base):
    def test_a_popup_opener_needs_the_flag(self):
        openers = [(p, b) for p, b in self.blocked() if b.targets and all(str(t) in coords.POPUP_PAGES for t in b.targets)
                   and not nav.net_risk(p)]          # a popup opener on a multiplayer or online page also needs --lan-step
        self.assertTrue(openers)
        self.assertTrue(all(self.policy(p, b)[0] for p, b in openers))
        self.set_flags("POPUP_OK")
        self.assertEqual([(p, b.label) for p, b in openers if self.policy(p, b)[0]], [])

    def test_online_save_game_stays_refused_with_only_the_popup_flag(self):
        self.set_flags("POPUP_OK")
        hits = [(p.name, b) for p in PAGES.values() if nav.net_risk(p.name) for b in p.buttons if b.kind == "APP_BUTTON_SAVEGAME"]
        self.assertTrue(hits)
        for name, b in hits:
            self.assertIsNotNone(self.policy(name, b)[0], name)

    def test_the_flag_does_not_unlock_buttons_that_open_other_pages(self):
        self.set_flags("POPUP_OK")
        for p, b in self.blocked():
            if not (b.targets and all(str(t) in coords.POPUP_PAGES for t in b.targets)):
                self.assertIsNotNone(self.policy(p, b)[0], (p, b.label))

    def test_a_confirm_tick_position_is_refused_but_an_acknowledgement_tick_is_not(self):
        for page in coords.POPUP_PAGES - coords.ACK_POPUPS:
            ok, msg = nav.goto_one(0, 0, PAGES, page, "@660,300", "MAIN MENU")
            self.assertFalse(ok, page)
            self.assertIn("refused", msg)
        self.assertLessEqual(coords.ACK_POPUPS, coords.POPUP_PAGES)

    def test_the_confirm_tick_of_a_popup_is_the_game_side_of_the_screen(self):
        self.assertGreater(coords.CONFIRM_POPUP[0], 400)
        self.assertLess(coords.CANCEL_POPUP[0], 400)


class LanAndHost(Base):
    def test_page_sets_are_consistent(self):
        self.assertLessEqual(coords.HOST_SETUP_PAGES, coords.LAN_PAGES)
        for name in coords.LAN_PAGES | coords.POPUP_PAGES:
            self.assertIn(name, PAGES, name)

    def test_multiplayer_pages_need_the_flag(self):
        risky = [(p.name, b) for p in PAGES.values() if nav.net_risk(p.name) for b in p.buttons]
        self.assertTrue(risky)
        for name, b in risky:
            self.assertIsNotNone(nav.lan_problem(b, name, [str(t) for t in b.targets]), (name, b.label))

    def test_hosting_joining_refreshing_are_refused_with_every_flag(self):
        self.set_flags(*FLAGS)
        hits = 0
        for p in PAGES.values():
            for b in p.buttons:
                cap = b.caption.upper()
                if not nav.net_risk(p.name):
                    continue
                if b.kind in coords.LAN_NEVER_KINDS or cap in coords.LAN_NEVER_CAPTIONS:
                    hits += 1
                    targets = [str(t) for t in b.targets]
                    allowed = (p.name == "SUMMARY_MPLIST" and cap == "HOST" and targets == ["SUMMARY_MPCLIENT"])
                    problem = nav.lan_problem(b, p.name, targets)
                    if allowed:
                        self.assertIsNone(problem)
                    else:
                        self.assertIsNotNone(problem, (p.name, b.label, b.kind))
        self.assertGreater(hits, 5)

    def test_the_one_allowed_host_press_needs_both_flags(self):
        host = [b for b in PAGES["SUMMARY_MPLIST"].buttons if b.caption.upper() == "HOST"]
        self.assertEqual(len(host), 1)
        b = host[0]
        want = [str(t) for t in b.targets]
        self.assertEqual(want, ["SUMMARY_MPCLIENT"])
        self.set_flags("HOST_OK")
        self.assertIsNotNone(nav.lan_problem(b, "SUMMARY_MPLIST", want))
        self.set_flags("LAN_OK")
        self.assertIsNotNone(nav.lan_problem(b, "SUMMARY_MPLIST", want))
        self.set_flags("LAN_OK", "HOST_OK")
        self.assertIsNone(nav.lan_problem(b, "SUMMARY_MPLIST", want))
        self.assertIsNotNone(nav.lan_problem(b, "SUMMARY_MPLIST", ["SUMMARY_MPCLIENT", "MAIN MENU"]))

    def test_creating_the_game_is_refused_on_the_setup_pages(self):
        self.set_flags(*FLAGS)
        creators = [(p.name, b) for p in PAGES.values() if p.name in coords.HOST_SETUP_PAGES for b in p.buttons
                    if b.kind == "APP_MP_TRACKLOCKEDBUTTON" or b.caption.upper() == "HOST"]
        self.assertTrue(creators)
        for name, b in creators:
            self.assertIsNotNone(self.policy(name, b)[0], (name, b.label))

    def test_online_and_account_pages_are_not_reachable(self):
        self.set_flags(*FLAGS)
        online = [p for p in PAGES.values() if menumap.page_risk(p.name) == "online service or account"]
        self.assertTrue(online)
        for p in online:
            if p.name in coords.LAN_PAGES:
                self.assertIn(p.name, coords.POPUP_PAGES)       # LEAVE LOBBY: the popup that leaves the empty LAN lobby
                continue
            for b in p.buttons:
                self.assertIsNotNone(nav.lan_problem(b, p.name, [str(t) for t in b.targets]), (p.name, b.label))


class SettingStep(Base):
    def test_controls_step_needs_the_setting_flag(self):
        ok, msg = nav.goto_one(0, 0, PAGES, "OPTIONS_BASIC_SIMMAIN", "!CONTROLS")
        self.assertFalse(ok)
        self.assertIn("--setting-step", msg)

    def test_controls_step_refuses_pages_outside_the_settings_pages(self):
        self.set_flags("SETTING_OK")
        for page in ("MAIN MENU", "SUMMARY_GRANDPRIX", "MONITOR_SINGLE", "OPTIONS_DETAIL_SIMMAIN", "CONTROL_KEYS_SIMMAIN", "PROFILE_SELECT_SIMMAIN"):
            ok, msg = nav.goto_one(0, 0, PAGES, page, "!CONTROLS")
            self.assertFalse(ok, page)
            self.assertIn("refused", msg)

    def test_the_flag_unlocks_no_blocked_button(self):
        self.set_flags("SETTING_OK")
        self.assertEqual([(p, b.label) for p, b in self.blocked() if self.policy(p, b)[0] is None], [])

    def test_every_expected_control_exists_on_its_page(self):
        for main, kinds in coords.CONTROL_PAGES.items():
            have = {c.kind for c in PAGES[main].controls}
            self.assertEqual(sorted(set(kinds) - have), [], main)
            for inert in coords.INERT_CONTROLS.get(main, []):
                self.assertIn(inert, have, (main, inert))

    def test_every_clicked_control_has_a_measured_arrow_or_is_a_checkbox(self):
        for main in coords.CONTROL_PAGES:
            for c in PAGES[main].controls:
                if c.attribute_set.startswith("SpinBox"):
                    self.assertIsNotNone(menumap.spinner_next(c), (main, c.kind))

    def test_control_expectation_covers_every_mode_copy(self):
        for suffix in ("SIMMAIN", "SUMMARY", "SCHOOL", "24H"):
            for base in coords.CONTROL_BASES:
                self.assertIsNotNone(coords.control_expectation("%s_%s" % (base, suffix)), (base, suffix))
        self.assertIsNone(coords.control_expectation("OPTIONS_DETAIL_SIMMAIN"))


class HoverStep(Base):
    def test_hover_refuses_a_page_that_is_not_in_the_menu_map(self):
        ok, msg = nav.goto_one(0, 0, PAGES, "NO SUCH PAGE", "!HOVER")
        self.assertFalse(ok)
        self.assertIn("not a page", msg)

    def test_hover_needs_no_flag_and_is_allowed_in_a_tour_without_flags(self):
        self.assertIn("HOVER", "HOVER")           # the verb is read-only: moves the mouse, never clicks or presses a key
        import inspect
        src = inspect.getsource(nav.step_hover)
        for forbidden in ("press(", "press_key(", "mouse(", "drag("):
            self.assertNotIn(forbidden, src.replace("ensure_focus()", ""), forbidden)

    def test_the_recorded_results_are_well_formed(self):
        import json
        data = json.loads((SCRIPTS / "gtr2_ui" / "hover_silent.json").read_text(encoding="utf-8"))
        self.assertGreater(len(data), 100)
        for page, entry in data.items():
            self.assertIn(page, PAGES)
            self.assertGreaterEqual(entry["buttons"], len(entry["silent"]))


class SpecialSteps(Base):
    def test_race_and_next_session_need_the_drive_flag(self):
        for label in ("!RACE", "!NEXTSESSION", "!DRIVE", "!LEAVEDRIVE"):
            self.set_flags("SESSION_OK", "SEASON_OK", "POPUP_OK")
            ok, msg = nav.goto_one(0, 0, PAGES, "MONITOR_SINGLE", label)
            self.assertFalse(ok)
            self.assertIn("--drive-step", msg)

    def test_an_unknown_bang_step_is_refused(self):
        ok, msg = nav.goto_one(0, 0, PAGES, "MONITOR_SINGLE", "!FORMAT")
        self.assertFalse(ok)
        self.assertIn("refused", msg)

    def test_the_race_button_is_unique_on_the_monitor_pages(self):
        for page in ("MONITOR_SINGLE",):
            self.assertEqual(len([b for b in PAGES[page].buttons if b.kind == "APP_BUTTON_TOREALTIME"]), 1)
            self.assertEqual(len([b for b in PAGES[page].buttons if b.kind == "APP_BUTTON_NEXTSESSION"]), 1)

    def test_the_summary_sliders_are_inside_the_canvas(self):
        for pos in (coords.GP_DISTANCE, coords.GP_OPPONENTS, coords.GP_PRACTICE, coords.GP_QUALIFYING,
                    coords.ENDURANCE_LENGTH_DOWN, coords.ENDURANCE_OPPONENTS):
            self.assertTrue(0 <= pos[0] <= 800 and 0 <= pos[1] <= 600, pos)


class Tours(Base):
    """Every step of every tour passes the policy with exactly the flags the tour's own header names."""

    def steps(self, file):
        out = []
        for line in file.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                out.append([c.strip() for c in line.split("|")])
        return out

    def test_every_tour_is_in_the_suite(self):
        every = {p.stem for p in (SCRIPTS / "nav_paths").glob("tour_*.txt")}
        self.assertEqual(sorted(every - set(suite.ORDER)), [])
        self.assertEqual(sorted(set(suite.ORDER) - every), [])

    def test_each_tour_only_presses_what_its_flags_allow(self):
        names = {"session": "SESSION_OK", "season": "SEASON_OK", "popup": "POPUP_OK", "lan": "LAN_OK", "host": "HOST_OK", "drive": "DRIVE_OK",
                 "setting": "SETTING_OK"}
        checked = 0
        for name in suite.ORDER + sorted(p.stem for p in (SCRIPTS / "nav_paths").glob("controls_*.txt")):
            flags = suite.flags_of(name)
            self.set_flags(*[names[f[2:-5]] for f in flags])
            for page, label, *rest in self.steps(suite.PATHS / (name + ".txt")):
                expect = rest[0] if rest else None
                map_page = page.split("=", 1)[0]
                if label.startswith("@"):
                    spot = tuple(float(v) for v in label[1:].split(","))
                    problem = nav.position_policy(PAGES, map_page, spot, [d.strip() for d in (expect or "").split(",") if d.strip()])[0]
                    self.assertIsNone(problem, (name, page, label, problem))
                    checked += 1
                    continue
                if label.startswith("!"):
                    if label.startswith("!"):
                        self.assertTrue(label[1:].upper() in ("SHORTRACE", "SHORTENDURANCE", "SHORTCHAMP", "NEXTSESSION", "RACE", "CONTROLS", "HOVER", "DRIVE", "LEAVEDRIVE"), (name, label))
                        if label[1:].upper() == "CONTROLS":
                            self.assertIn("--setting-step", flags, (name, label))
                        if label[1:].upper() in ("NEXTSESSION", "RACE", "DRIVE", "LEAVEDRIVE"):
                            self.assertIn("--drive-step", flags, (name, label))
                    continue
                try:
                    b = menumap.find_button(PAGES, map_page, label)
                except KeyError:
                    continue            # an alias page resolved at run time
                want = [d.strip() for d in expect.split(",")] if expect else [str(t) for t in b.targets]
                problem, _s, _p = nav.step_policy(b, map_page, want)
                self.assertIsNone(problem, (name, page, label, problem))
                checked += 1
        self.assertGreater(checked, 150)

    def test_no_tour_flag_is_unknown(self):
        for name in suite.ORDER:
            for f in suite.flags_of(name):
                self.assertIn(f, ("--session-step", "--season-step", "--popup-step", "--lan-step", "--host-step", "--drive-step", "--setting-step"), (name, f))

    def test_tours_that_race_say_so_in_their_header(self):
        for name in suite.ORDER:
            text = (suite.PATHS / (name + ".txt")).read_text(encoding="utf-8")
            if "| !RACE" in text or "| !NEXTSESSION" in text or "APP_BUTTON_POSTRACENAVIGATION" in text:
                self.assertIn("--drive-step", suite.flags_of(name), name)


class InputHelpers(Base):
    def test_a_drag_always_releases_the_mouse(self):
        events, calls = [], []
        nav.drag = self.saved["drag"]               # the real drag, with every input primitive below replaced
        nav.ensure_focus = lambda *a, **k: True
        nav.mouse = lambda flag: events.append(flag)

        def move(ox, oy, x, y):
            calls.append((x, y))
            if len(calls) == 4:
                raise RuntimeError("the game window was lost")
        nav.move_to = move
        orig_sleep = nav.time.sleep
        nav.time.sleep = lambda s: None
        try:
            with self.assertRaises(RuntimeError):
                nav.drag(0, 0, 100, 100, 500, 100)
        finally:
            nav.time.sleep = orig_sleep
        self.assertEqual(events, [0x0002, 0x0004])

    def test_plr_value_reads_the_profile_as_the_game_wrote_it(self):
        self.assertIn(nav.plr_value("Run Practice1"), ("0", "1"))
        self.assertIsNone(nav.plr_value("No Such Setting"))

    def test_ui_coordinates_map_the_canvas_to_the_client(self):
        self.assertEqual(nav.ui(800, 600), (1280, 720))
        self.assertEqual(nav.ui(0, 0), (0, 0))
        self.assertEqual(nav.ui(500, 250), (800, 300))


class PauseMenu(unittest.TestCase):
    def test_the_highlighted_row_is_read_from_real_captures(self):
        import numpy as np
        from PIL import Image
        here = SCRIPTS / "gtr2_ui" / "fixtures"
        want = {"pause_garage_session.png": "Return to Garage", "pause_race.png": "Return to Garage",
                "pause_six_rows.png": "Hide Menu", "pause_not_showing.png": None}
        for name, expected in want.items():
            frame = np.asarray(Image.open(here / name).convert("RGB"), dtype=np.int16)
            self.assertEqual(nav.pause_row_of(frame), expected, name)

    def test_the_autopilot_row_is_one_of_the_rows(self):
        from pausemenu import PAUSE_ROWS
        self.assertIn("Autopilot", [n for n, _ in PAUSE_ROWS])
        self.assertIn("Continue", [n for n, _ in PAUSE_ROWS])


class Diagnostics(unittest.TestCase):
    GOOD = ("[COMPONENTS]\nLOGDIR=USERDATA\\LOG\\\nREPLAYDIR=REPLAYDATA\\\nTIMETRIALDIR=TIMETRIAL\\\nDRIVINGSCHOOLDIR=GAMEDATA\\DRIVINGSCHOOL\\\n"
            "VIDEOGUID=A1B2C3D4-0000-0000-0000-000000000000\nVIDEOMODE=72\nWINDOWEDMODE=1\n")

    def test_the_launchers_own_config_has_no_problems(self):
        self.assertEqual(nav.diag.config_problems((nav.diag.game_root() / "config" / "Documents-Config.ini").read_bytes().decode("latin1")), [])
        self.assertEqual(nav.diag.config_problems(self.GOOD), [])

    def test_the_fullscreen_default_the_game_writes_is_refused(self):
        text = self.GOOD.replace("VIDEOGUID=A1B2C3D4-0000-0000-0000-000000000000", "VIDEOGUID=").replace("VIDEOMODE=72", "VIDEOMODE=0").replace(
            "WINDOWEDMODE=1", "WINDOWEDMODE=0")
        self.assertEqual(len(nav.diag.config_problems(text)), 3)

    def test_each_unsafe_setting_is_refused_alone(self):
        for old, new in (("WINDOWEDMODE=1", "WINDOWEDMODE=0"), ("VIDEOMODE=72", "VIDEOMODE=0"),
                         ("VIDEOGUID=A1B2C3D4-0000-0000-0000-000000000000", "VIDEOGUID="),
                         ("LOGDIR=USERDATA\\LOG\\", "LOGDIR=C:\\Users\\x\\Documents\\GTR2\\userdata\\Log\\"), ("REPLAYDIR=REPLAYDATA\\", "REPLAYDIR=")):
            self.assertEqual(len(nav.diag.config_problems(self.GOOD.replace(old, new))), 1, new)

    def test_the_nul_header_of_a_real_config_is_ignored(self):
        self.assertEqual(nav.diag.config_problems("\x00\x00//[[gMa]]\n" + self.GOOD), [])

    def test_a_session_that_is_not_the_console_is_reported(self):
        real = nav.diag.console_session
        try:
            nav.diag.console_session = lambda: (3, 3)
            self.assertIsNone(nav.diag.session_problem())
            nav.diag.console_session = lambda: (3, 5)
            self.assertIn("session 3", nav.diag.session_problem())
            self.assertIn("GTR2Config", nav.diag.session_problem())
            nav.diag.console_session = lambda: (3, 0xFFFFFFFF)
            self.assertIsNone(nav.diag.session_problem())
        finally:
            nav.diag.console_session = real

    def test_preflight_and_diagnose_press_nothing(self):
        class Quiet(Base):
            def runTest(self):                  # every input function raises in a Base test; these two only read
                nav.cmd_diagnose(save=False)
                nav.cmd_preflight()
        result = unittest.TestResult()
        Quiet().run(result)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)


class Weather(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = load("gtr2_weather", "gtr2-weather.py")
        cls.data = cls.w.PLR.read_bytes()

    def test_every_mode_has_exactly_one_weather_line(self):
        for k in self.w.MODES:
            self.assertIn(self.w.get_value(self.data, k), ("0", "1", "2", "3", "4", "5"), k)

    def test_setting_a_value_changes_only_that_line_and_keeps_every_other_byte(self):
        new = self.w.set_value(self.data, "FRACE", 0)
        self.assertEqual(len(new), len(self.data))
        diff = [i for i, (a, b) in enumerate(zip(self.data, new)) if a != b]
        self.assertLessEqual(len(diff), 1)
        self.assertEqual(new[:16], self.data[:16])             # the NUL-byte header
        self.assertEqual(self.w.get_value(new, "FRACE"), "0")
        self.assertEqual(self.w.get_value(new, "PRACT"), self.w.get_value(self.data, "PRACT"))

    def test_apply_then_restore_values_is_byte_identical(self):
        data = self.data
        old = {k: self.w.get_value(data, k) for k in self.w.MODES}
        for k in self.w.MODES:
            data = self.w.set_value(data, k, 0)
        for k, v in old.items():
            data = self.w.set_value(data, k, v)
        self.assertEqual(data, self.data)

    def test_a_missing_or_repeated_line_is_an_error(self):
        with self.assertRaises(ValueError):
            self.w.set_value(self.data, "NOSUCH", 0)
        with self.assertRaises(ValueError):
            self.w.set_value(self.data + b'\nFRACE Weather="2"\n', "FRACE", 0)

    def test_the_weekend_files_exist_and_look_like_weather_files(self):
        for name in ("sunny", "rainy", "stormy"):
            text = (self.w.SOURCES / ("weather_weekend_%s.txt" % name)).read_text(encoding="latin1")
            self.assertTrue(text.lstrip().startswith("Weather"), name)
            self.assertIn("AmbientTemp", text)

    def test_nothing_is_left_applied(self):
        self.assertFalse(self.w.STATE.exists(), "weather is applied: run gtr2-weather.py restore")


class FileWatch(unittest.TestCase):
    def test_the_watcher_and_oplock_modules_import(self):
        mod = load("gtr2_file_watch", "gtr2-file-watch.py")
        self.assertTrue(hasattr(mod, "main"))
        self.assertTrue(hasattr(mod.oplock, "Tripwire"))

    def test_a_tripwire_breaks_when_another_handle_reads_the_file(self):
        import tempfile
        import oplock
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "watched.txt"
            f.write_text("x")
            w = oplock.Tripwire(f).arm()
            try:
                self.assertFalse(w.broke)
                f.read_text()
                for _ in range(100):
                    if w.broke:
                        break
                    time.sleep(0.02)
                self.assertTrue(w.broke)
            finally:
                w.disarm()


class LapCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lc = load("gtr2_lap_check", "gtr2-lap-check.py")
        cls.items, cls.cars = cls.lc.layouts(), cls.lc.cars()

    def test_the_install_has_34_layouts_and_24_cars_and_the_default_car(self):
        self.assertEqual(len(self.items), 34)
        self.assertEqual(len(self.cars), 24)
        self.assertIn(self.lc.DEFAULT_CAR, self.cars)

    def test_every_layout_is_picked_uniquely_by_venue_plus_file(self):
        for v, t, _ in self.items:
            self.assertEqual(self.lc.pick_layout(v + t, self.items)[:2], (v, t))

    def test_an_ambiguous_or_unknown_name_is_refused_and_says_what_matched(self):
        with self.assertRaises(ValueError) as e:
            self.lc.pick_layout("Monza", self.items)
        self.assertIn("matches", str(e.exception))
        with self.assertRaises(ValueError):
            self.lc.pick_layout("NoSuchTrack", self.items)

    def test_a_lap_is_clean_only_when_completed_and_under_the_off_road_limit(self):
        j = self.lc.judge
        self.assertTrue(j({"outcome": "completed", "off_road_share": 0.0})[0])
        self.assertFalse(j({"outcome": "completed", "off_road_share": 0.005})[0])
        self.assertFalse(j({"outcome": "timeout", "off_road_share": 0.0})[0])
        self.assertFalse(j({"outcome": "completed"})[0])
        self.assertTrue(j({"outcome": "completed", "off_road_share": 0.007}, limit=0.01)[0])

    def test_the_profile_edit_changes_only_the_named_lines_and_every_key_exists(self):
        data = self.lc.PLR.read_bytes()
        v, t, a = self.lc.pick_layout("Imola4Imol", self.items)
        values = self.lc.profile_values(v, t, a, self.cars["gt/ferrari_550"])
        new = self.lc.set_values(data, values)
        old_lines, new_lines = data.split(bytes([10])), new.split(bytes([10]))
        self.assertEqual(len(old_lines), len(new_lines))
        self.assertLessEqual(sum(x != y for x, y in zip(old_lines, new_lines)), len(values))
        self.assertEqual(new[:16], data[:16])                       # the NUL-byte header
        self.assertIn(b'Vehicle File="GAMEDATA\\TEAMS\\GT\\FERRARI 550 TEAMS', new)
        with self.assertRaises(ValueError):
            self.lc.set_values(data, {"No Such Key": "1"})

    def test_the_driving_profile_uses_the_keys_the_driver_presses(self):
        d = self.lc.DRIVING_PROFILE
        self.assertEqual(d["Control - Accelerate"], "(0, 30)")           # scancode 0x1E = A
        self.assertEqual(d["Control - Brake"], "(0, 44)")                # 0x2C = Z
        self.assertEqual((d["Control - Steer Left"], d["Control - Steer Right"]), ("(0, 51)", "(0, 52)"))   # comma, period
        self.assertEqual(d["Control - Shift Up"], "(0, 56)")             # 0x38 = Alt

    def test_all_cars_and_resume_plan_without_touching_the_game(self):
        lc, calls = self.lc, []
        fake = lambda venue, trk, aiw, car_key, car_path, fast, *rest: (calls.append((venue, trk, car_key)) or {"outcome": "completed", "off_road_share": 0.0}, "")  # noqa: E731
        saved = {n: getattr(lc, n) for n in ("one_run", "RESULTS")}
        suite_saved = {n: getattr(lc.suite, n) for n in ("game_running", "dirty_tracked", "untracked", "nav")}
        import tempfile
        try:
            lc.one_run = fake
            lc.suite.game_running = lambda: False
            lc.suite.dirty_tracked = lambda: []
            lc.suite.untracked = lambda: set()
            lc.suite.nav = lambda *a, **k: type("R", (), {"stdout": "preflight stub", "stderr": "", "returncode": 0})()
            with tempfile.TemporaryDirectory() as d:
                lc.RESULTS = Path(d) / "lap_results.jsonl"
                saved_argv = sys.argv
                sys.argv = ["x", "Imola4Imol", "--all-cars"]
                try:
                    self.assertEqual(lc.main(), 0)
                finally:
                    sys.argv = saved_argv
                self.assertEqual(len(calls), 24)
                self.assertEqual(len({c[2] for c in calls}), 24)
                calls.clear()
                sys.argv = ["x", "Imola4Imol", "--all-cars", "--resume"]
                try:
                    self.assertEqual(lc.main(), 0)           # all 24 are clean now: nothing is driven
                finally:
                    sys.argv = saved_argv
                self.assertEqual(calls, [])
        finally:
            for n, f in saved.items():
                setattr(lc, n, f)
            for n, f in suite_saved.items():
                setattr(lc.suite, n, f)


class Suite(unittest.TestCase):
    def test_flags_are_read_from_the_tour_headers(self):
        self.assertIn("--session-step", suite.flags_of("tour_session_practice"))
        self.assertEqual(suite.flags_of("tour_options_main"), [])

    def test_the_suite_cleanup_only_names_profile_folders(self):
        self.assertEqual(suite.WATCHED, ["UserData", "ReplayData"])


class ScrubbedNames(unittest.TestCase):
    """Saved page references must not carry the player name from the header band."""

    def setUp(self):
        import numpy as np
        import pagerec
        self.np, self.pagerec = np, pagerec
        self.image = np.full((450, 800, 3), 40, dtype=np.int16)
        self.mask = np.zeros((450, 800), dtype=bool)

    def test_text_in_the_name_box_is_painted_out_and_masked(self):
        x0, y0, x1, y1 = self.pagerec.NAME_BOX
        self.image[y0 + 2:y1 - 3, x0 + 8:x1 - 8] = 255        # white "text"
        picture, mask = self.pagerec.scrub_name(self.image, self.mask)
        self.assertLess(int(picture[y0:y1, x0:x1].max()), 60)
        self.assertTrue(mask[y0:y1, x0:x1].all())
        self.assertFalse(mask[y1 + 5:, :].any())
        self.assertEqual(int(self.image[y0 + 2, x0 + 10, 0]), 255)    # the input is not changed

    def test_a_picture_without_text_there_is_left_alone(self):
        picture, mask = self.pagerec.scrub_name(self.image, self.mask)
        self.assertTrue((picture == self.image).all())
        self.assertFalse(mask.any())

    def test_other_picture_sizes_are_left_alone(self):
        x0, y0, x1, y1 = self.pagerec.NAME_BOX
        small = self.np.full((225, 400, 3), 40, dtype=self.np.int16)
        small[y0 + 2:y1 - 3, 5:20] = 255
        picture, _mask = self.pagerec.scrub_name(small, self.np.zeros((225, 400), dtype=bool))
        self.assertTrue((picture == small).all())

    def test_the_shipped_references_show_no_text_in_the_name_box(self):
        from PIL import Image
        x0, y0, x1, y1 = self.pagerec.NAME_BOX
        for path in sorted((SCRIPTS / "gtr2_ui" / "baselines").rglob("*.png")):
            if path.name.endswith(".mask.png") or path.name.startswith("PHOTO+SHOP"):
                continue
            lum = self.np.asarray(Image.open(path).convert("L"), dtype=self.np.int16)[y0:y1, x0:x1]
            self.assertLess(int(lum.max() - lum.min()), 30, str(path))


if __name__ == "__main__":
    unittest.main()
