"""Settings pagerec.py needs.

The window is always 1280x720 windowed (see CLAUDE.md); every capture is shrunk to 800x450 before comparing, and each window size
has its own folder of references under baselines/.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
WINDOW = (1280, 720)
WINDOW_KEY = "%dx%d" % WINDOW
SHRINK_SIZE = (800, round(800 * WINDOW[1] / WINDOW[0]))
MASK_SCALE = SHRINK_SIZE[1] / 450.0
BASELINES = HERE / "baselines" / WINDOW_KEY
LOCAL_BASELINES = HERE / "baselines" / "local" / WINDOW_KEY   # references learned on this machine; override the shipped copies
