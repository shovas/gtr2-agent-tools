"""Measured control positions that are NOT in UIData\\gtr2ui.mnu (sliders, list rows, scrollbar arrows, a few switches).

All positions are UI canvas units
(800x600); gtr2-nav.py maps them to the 1280x720 client by x*1.6, y*1.2. They were measured on another machine and profile
by dragging every slider past both ends and reading the profile; the sizes of the lists depend on which tracks and cars the
install has, so row positions assume the same install layout (the shipped UIData layout).

Not re-measured here unless the docs (CLAUDE.md, "Slider and list coordinates") say so.
"""

# Sliders on the Options pages: (profile key, saved value at the left end, at the right end). Order = order on the page, top to bottom.
SLIDERS = {
    "OPTIONS_AUDIO_SIMMAIN": [
        ("Music Volume", 0.0, 1.0), ("SoundFX Volume", 0.0, 1.0), ("Engine Volume", 0.0, 1.0),
        ("Radio Comms Volume", 0.0, 1.0), ("Other Volume Ratio", 0.0, 2.0), ("Player Volume Ratio", 0.0, 2.0),
        ("Vehicle Scrubbing VolMult", 0.0000610352, 0.0001220704),
        ("Vehicle Skidding VolMult", 0.0001220703, 0.0002441406),
        ("Vehicle Roadnoise VolMult", 0.0000150000, 0.0000300000)],
    "OPTIONS_ADVANCED_SIMMAIN": [
        ("LOD Multiplier Multiplier", 0.75, 1.25), ("Head Physics", 0.0, 1.0), ("Lookahead Angle", 0.0, 1.0),
        ("World Movement", 0.0, 1.0)],
    "OPTIONS_ASSISTS_SIMMAIN": [("Damage Multiplier", 100, 200)],
}
# (start x of a drag, x past the left end, x past the right end) of the track on each page
AUDIO_TRACK = (460, 360, 575)
ADVANCED_TRACK = (290, 190, 395)
# Per slider: (UI y, start x, left x, right x). The same positions apply on a mode's own copy of the page (..._SUMMARY, ..._SCHOOL, ...).
SLIDER_GEOMETRY = {
    "OPTIONS_AUDIO_SIMMAIN": [(188 + 35.0 * i, *AUDIO_TRACK) for i in range(9)],
    "OPTIONS_ADVANCED_SIMMAIN": [(378 + 30.0 * i, *ADVANCED_TRACK) for i in range(4)],
    "OPTIONS_ASSISTS_SIMMAIN": [(281.0, 490, 395, 585)],
}

# Lists (rows are not in the menu file)
CIRCUIT_ROWS = {"x": 200, "first": 187.3, "step": 15.1}      # Circuit page: names start at "Donington Park GP"
CIRCUIT_LIST = (195, 190, 285, 300)                           # region (x, y, w, h) of the circuit names
CIRCUIT_SCROLL_DOWN, CIRCUIT_SCROLL_UP = (340, 431), (340, 183)
CLASS_LIST = (160, 150, 140, 190)                             # region of the class names
CLASS_SCROLL_DOWN, CLASS_SCROLL_UP = (331, 453), (331, 206)
CLASS_RADIO = (293, 215)                                      # first class on the Car page's Class tab (a left click adds it)
MODEL_FIRST_ROW = (175, 312)                                  # first car on the Model tab

# Switches and thumbs
MAP_TOGGLE = (779.5, 120.5)                                   # Circuit page: circuit list <-> info page
PAGE_FADE = (446.5, 583)                                      # Showroom: car page <-> stats page
INFO_POS = (273.5, 66)                                        # track info button (shares its name with another gizmo)
TT_TAB = (614, 403)                                           # Time Trial: tab that opens the lap list
MONITOR_VIEW_BUTTON = (397, 358)                              # first red button under the monitor's camera view
CANCEL_POPUP, CONFIRM_POPUP = (137, 300), (660, 300)          # X and tick of the game's yes/no popups
# Race Weekend summary, shortest race (thumbs at their saved 10% and 20; dragging far left gives 3 laps and no opponents):
GP_DISTANCE, GP_OPPONENTS = (511, 262.7), (604, 412.7)
GP_PRACTICE, GP_QUALIFYING = (290, 259.3), (290, 358.7)       # Friday practice and Saturday qualifying checkboxes
# 24 Hour summary: race length spinner's left arrow (eight presses reach 24 minutes) and the Opponents thumb (saved 35)
ENDURANCE_LENGTH_DOWN, ENDURANCE_OPPONENTS = (386, 248), (526, 343)
# Replay studio
REPLAY_ROW = (316, 257)                                       # first replay in the list
REPLAY_LEAVE_FULL_SCREEN = (398, 298)                         # one button: a click anywhere returns
REPLAY_INSTANT_SLIDER = {"start": (408, 197), "end": (540, 197), "region": (380, 185, 170, 25)}   # instant replay length, 30 s to max


def circuit_row(index):
    """UI point of the nth circuit name (0 = first name shown)."""
    return CIRCUIT_ROWS["x"], CIRCUIT_ROWS["first"] + CIRCUIT_ROWS["step"] * index


# Pages that are yes/no or name-entry popups (drawn over another page; X cancels at CANCEL_POPUP, the tick confirms at CONFIRM_POPUP).
# `gtr2-nav.py ... --popup-step` may press a blocked button (SAVE, DELETE, RENAME, LOAD, NEW, EXIT, a controller name) only when the
# page it opens is one of these, and a path may press only the X on them, never the tick.
POPUP_PAGES = {
    "CONFIRM_KEYBOARD", "CONFIRM_CONTROL1", "CONFIRM_CONTROL2", "CONFIRM_CONTROL3", "CONFIRM_TO_WINDOWS",
    "PROFILE ADD", "DELETE PROFILE", "RENAME REPLAY", "DELETE REPLAY", "RENAME TIMETRIAL", "SAVE TIMETRIAL", "LOAD TIMETRIAL",
    "DELETE TIMETRIAL", "SAVE GARAGE SETUP", "DELETE GARAGE SETUP", "SAVEGAME", "LOAD GAME",
}

# `!SELECTWHEEL` (gtr2-nav.py, needs --setting-step): on this page the JOY1 slot's name (the first game controller; the caption in the menu map is
# a static device name, the game shows the real device there, "vJoy Device" here) opens CONFIRM_CONTROL1 ("You will lose any controller changes you
# have made. Continue?"); the tick (at CONFIRM_TICK, canvas units) selects that controller as the basic control device: the game then writes
# `Basic Controls="2"` and resets the pedal bindings to its wheel defaults (Accelerate Y-, Brake Y+). Measured 2026-11-14 with vJoy.
WHEEL_PAGE = "CONTROL_KEYS_SIMMAIN"
WHEEL_SLOT_LABEL = "WingMan RumblePad USB"
WHEEL_CONFIRM_TICK = (642, 302)

# Popups with a tick only (an acknowledgement, nothing left to decide): a path may press their tick. "Game Saved" appears after SAVE GAME
# has already saved the game, so pressing the tick only closes the notice.
ACK_POPUPS = {"SAVEGAME"}


# LAN multiplayer: the pages `--lan-step` may touch. Only the local games list and the pages around it; nothing that hosts, joins, refreshes the
# list or adds a server is ever pressed (those kinds are refused with no override), and the Internet and account pages are not here.
LAN_PAGES = {
    "SUMMARY_MPLIST", "MP_ADDGAME", "LEAVE LOBBY",
    "OPTIONS_BASIC_MULTIPLAYER", "OPTIONS_DETAIL_MULTIPLAYER", "OPTIONS_AUDIO_MULTIPLAYER", "OPTIONS_ADVANCED_MULTIPLAYER",
    "OPTIONS_GAME_MULTIPLAYER", "OPTIONS_ASSISTS_MULTIPLAYER",
    "CONTROL_KEYS_MULTIPLAYER", "CONTROL_ONE_MULTIPLAYER", "CONTROL_FORCE_MULTIPLAYER",
}
LAN_NEVER_KINDS = {"APP_BUTTON_MULTIPLAYER_JOIN", "APP_BUTTON_MULTIPLAYER_REFRESHGAMELIST", "APP_BUTTON_MULTIPLAYER_ADDSERVER",
                   "APP_BUTTON_MULTIPLAYER_HOST"}
LAN_NEVER_CAPTIONS = {"HOST", "JOIN", "REFRESH", "STOP", "DRIVE", "MP_ADDSERVER"}
POPUP_PAGES |= {"MP_ADDGAME", "LEAVE LOBBY"}
ACK_POPUPS |= {"LEAVE LOBBY"}      # the tick leaves the (empty) LAN lobby; nothing is lost


# The host SETUP pages (reached from the games list's HOST button; nothing is hosted until the setup page's own HOST button, which is never
# pressed). `--host-step` allows only that first press: SUMMARY_MPLIST / HOST -> SUMMARY_MPCLIENT.
HOST_SETUP_PAGES = {
    "SUMMARY_MPCLIENT", "SUMMARY_MPSETTINGS", "CLASS_SELECT_HOST", "TEAM_SELECT_HOST", "CIRCUIT_SELECT_HOST", "CIRCUIT_INFO_HOST",
    "OPTIONS_BASIC_HOST", "OPTIONS_DETAIL_HOST", "OPTIONS_AUDIO_HOST", "OPTIONS_ADVANCED_HOST", "OPTIONS_GAME_HOST", "OPTIONS_ASSISTS_HOST",
    "CONTROL_KEYS_HOST", "CONTROL_ONE_HOST", "CONTROL_FORCE_HOST",
}
LAN_PAGES |= HOST_SETUP_PAGES


# Checkboxes and spinners of the four settings pages: gizmo type -> the profile key (or the end of one: a key may carry a mode prefix such as
# FRACE or QUICK, and one control may write several) it saves to. They were found
# by clicking every control and reading the profile; there with Simulation difficulty. "Inert" controls never change on screen in that state:
# locked by the difficulty, or only acting in a state the tests don't set up. The profile here is in Novice mode, so these sets are
# the starting point and `gtr2-control-check.py` re-measures them.
CONTROL_PAGES = {
    "OPTIONS_BASIC_SIMMAIN": {
        "APP_SPINBOX_GRAPHOPT_STARTINGVIEW": "Starting View", "APP_CHECKBOX_LETTERBOX": "Letterbox Mode",
        "APP_SPINBOX_GAMEOPT_HUD": "HUD", "APP_SPINBOX_GAMEOPT_KPH_OR_MPH": "Speed Units",
        "APP_SPINBOX_GAMEOPT_UNITS": "Measurement Units", "APP_SPINBOX_MIRRORS": "Virtual Mirrors|Rearview",
        "APP_SPINBOX_GAMEOPT_RACE_DISTANCE": "Race Distance in Laps"},
    "OPTIONS_AUDIO_SIMMAIN": {
        "APP_SPINBOX_INCARMUSIC": "Music On Track (Sim)", "APP_CHECKBOX_MENUSOUNDS": "Menu Mouse Sounds"},
    "OPTIONS_ADVANCED_SIMMAIN": {
        "APP_CHECKBOX_VISIBLESTEERINGWHEEL": "Steering Wheel Visible In Cockpit",
        "APP_CHECKBOX_VERTEXDAMAGE": "Vertex Damage", "APP_CHECKBOX_WINDSCREEN": "Windscreen dirt buildup",
        "APP_CHECKBOX_MOTECADL": "Show MoTeC in Cockpit", "APP_CHECKBOX_HDWHEELS": "High Detail Wheels",
        "APP_CHECKBOX_ULTRAREZ": "Livery UltraRez", "APP_CHECKBOX_COCKPIT_ULTRAREZ": "Cockpit UltraRez",
        "APP_SPINBOX_VIDEO_TEXTUREDETAIL": "Reduced Track Textures", "APP_CHECKBOX_PRESETTYRES": "Preset Tyres",
        "APP_CHECKBOX_HUDCOCKPIT": "Allow HUD in cockpit", "APP_CHECKBOX_PITEXITARROW": "Pit Direction Indicator",
        "APP_CHECKBOX_DATAACQUISITION": "Data Acquisition In Race", "APP_SPINBOX_STARTINGDRIVER": "Starting Driver",
        "APP_CHECKBOX_SIMPLECOLLISION": "Simple Debris Collisions", "APP_CHECKBOX_CRASHRECOVERY": "Crash Recovery",
        "APP_SPINBOX_AICONTROLSDRIVER2": "AI Controls Driver #2",
        "APP_CHECKBOX_PITLANECONTROL": "Pitlane Control System"},
    "OPTIONS_ASSISTS_SIMMAIN": {
        "APP_SPINBOX_DRIVINGAID_AUTOCLUTCH": "Auto Clutch", "APP_SPINBOX_DRIVINGAID_AUTOREVERSE": "Auto Reverse",
        "APP_SPINBOX_DRIVINGAID_STEERINGHELP": "Steering Help",
        "APP_SPINBOX_DRIVINGAID_SHIFTMODE": "Shift Mode", "APP_SPINBOX_RACECOND_FLAGRULES": "Flag Rules",
        "APP_CHECKBOX_CORNERMARKERS": "Corner Markers", "APP_SPINBOX_RACECOND_FULLCOURSEYELLOW": "Full Course Yellows",
        "APP_SPINBOX_MECHFAIL_MECHFAILURE": "Failure Rate", "APP_SPINBOX_GAMEOPT_FUELUSAGE": "Fuel Consumption Multiplier",
        "APP_SPINBOX_GAMEOPT_TIREWEAR": "Tire Wear Multiplier", "APP_SPINBOXLIGHTINGACCELERATION": "Time Scale Factor",
        "APP_CHECKBOX_TIMESCALEDWEATHER": "TimeScaledWeather"},
}
INERT_CONTROLS = {
    "OPTIONS_AUDIO_SIMMAIN": ["APP_SPINBOX_SOUND_CHANNELS"],
    "OPTIONS_ADVANCED_SIMMAIN": ["APP_SPINBOX_SPLITTIME", "APP_SPINBOX_MINIMALHUDPOSITION"],
    "OPTIONS_ASSISTS_SIMMAIN": [
        "APP_SPINBOX_GAMEOPT_DIFFICULTY", "APP_SPINBOX_DRIVINGAID_ANTILOCKBRAKES", "APP_SPINBOX_DRIVINGAID_THROTTLECONTROL",
        "APP_SPINBOX_DRIVINGAID_BRAKINGPOINT", "APP_SPINBOX_DRIVINGAID_DRIVINGASSIST",
        "APP_SPINBOX_DRIVINGAID_SPINRECOVERY", "APP_SPINBOX_DRIVINGAID_INVULNERABILITY"],
}
# Controls that work on the main pages but not in one mode's copy, by (mode suffix, page base): in Driving School the time scaled weather
# checkbox doesn't change on screen.
CONTEXT_EXTRA_INERT = {("SCHOOL", "OPTIONS_ASSISTS"): {"APP_CHECKBOX_TIMESCALEDWEATHER"}}
# Profile keys that change when the settings pages are swept but that no single control is known to write (seen 2026-11-11 in every sweep of the
# main pages here: the preset levels Basic Display and Basic Audio, Maximum Effects with the sound pages, and Online Server, which the game
# rewrites on some exits). Listed so that the check can tell them from a control saving to an unexpected key.
SIDE_EFFECT_KEYS = {"Basic Display", "Basic Audio", "Maximum Effects", "Online Server"}
CONTROL_BASES = ("OPTIONS_BASIC", "OPTIONS_AUDIO", "OPTIONS_ADVANCED", "OPTIONS_ASSISTS")
# Measured here (2026-11-11, `gtr2-control-check.py`, profile in Novice mode): controls found inert (Simulation difficulty locks them)
# that do change on screen here, with the profile key each saved. A key may list alternatives with "|" (the mirrors spinner saves Rearview in this profile).
LOCAL_WORKING = {
    "OPTIONS_ASSISTS_SIMMAIN": {
        "APP_SPINBOX_DRIVINGAID_BRAKINGPOINT": "Brake Help", "APP_SPINBOX_DRIVINGAID_DRIVINGASSIST": "Stability Control|Opposite Lock",
        "APP_SPINBOX_DRIVINGAID_INVULNERABILITY": "Invulnerability", "APP_SPINBOX_DRIVINGAID_SPINRECOVERY": "Spin Recovery",
        "APP_SPINBOX_GAMEOPT_DIFFICULTY": "Difficulty Type"},
}


def control_expectation(page):
    """For a settings page (`OPTIONS_BASIC_SIMMAIN` or the same page of a mode, `OPTIONS_BASIC_SUMMARY`...): ({control type: profile key}
    expected to change on screen and in the profile when clicked, the set of types expected not to change), or None for any other page."""
    for base in CONTROL_BASES:
        if page.startswith(base + "_"):
            suffix = page[len(base) + 1:]
            main = base + "_SIMMAIN"
            if main not in CONTROL_PAGES:
                return None
            local = LOCAL_WORKING.get(main, {})
            inert = (set(INERT_CONTROLS.get(main, [])) - set(local)) | CONTEXT_EXTRA_INERT.get((suffix, base), set())
            working = {**CONTROL_PAGES[main], **local}
            return {k: v for k, v in working.items() if k not in inert}, inert
    return None
