"""Settings pagerec.py needs.

The game is always windowed, at the test size chosen at setup (`resolution` in gtr2-tools.json; the GTR2_RESOLUTION environment
variable overrides it; default 1280x720). Every capture is shrunk to 800x450 before comparing, and each test size has its own folder
of references: 1280x720 ships with the repository (baselines/1280x720 and baselines/local/1280x720); any other size has to be
learned on the machine once (`gtr2-nav-suite.py --learn`, which writes baselines/local/<size> and pair_scores_<size>.json; git-ignored).
The size is the test window, not the screen: pick one that fits the screen with its title bar (1280x720 on a 1080p screen, 640x480 for
a 4:3 screen).
"""
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SIZE = (1280, 720)    # the size the shipped references were taken at


def _configured_size():
    text = os.environ.get("GTR2_RESOLUTION", "")
    if not text:
        try:
            text = json.loads((HERE.parent.parent / "gtr2-tools.json").read_text(encoding="utf-8")).get("resolution", "")
        except (OSError, ValueError):
            text = ""
    m = re.fullmatch(r"\s*(\d+)\s*x\s*(\d+)\s*", str(text))
    return (int(m.group(1)), int(m.group(2))) if m else DEFAULT_SIZE


WINDOW = _configured_size()
WINDOW_KEY = "%dx%d" % WINDOW
SHRINK_SIZE = (800, 450)      # whatever the window's shape, so the pictures and the mask boxes use one coordinate system
MASK_SCALE = 1.0
BASELINES = HERE / "baselines" / WINDOW_KEY                   # shipped (only 1280x720 exists)
LOCAL_BASELINES = HERE / "baselines" / "local" / WINDOW_KEY   # references learned on this machine; override the shipped copies
