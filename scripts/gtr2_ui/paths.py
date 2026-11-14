"""Settings pagerec.py needs.

The game is always windowed. Every capture is shrunk to 800x450 before comparing, whatever the window size (the UI is an 800x600
canvas stretched over the window), so one set of references, stored in the folder named after the size they were taken at (1280x720),
serves every window size.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
WINDOW = (1280, 720)    # the size the stored references were taken at (names their folder); not a limit on the window
WINDOW_KEY = "%dx%d" % WINDOW
SHRINK_SIZE = (800, 450)
MASK_SCALE = 1.0
BASELINES = HERE / "baselines" / WINDOW_KEY
LOCAL_BASELINES = HERE / "baselines" / "local" / WINDOW_KEY   # references learned on this machine; override the shipped copies
