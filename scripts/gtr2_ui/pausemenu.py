"""Read the in-game pause menu's highlighted row from a frame (PAUSE_ROWS, pause_row_of); frames are RGB numpy arrays of the game's client area (any size).
Test: scripts/.venv/Scripts/python.exe -I scripts/gtr2_ui/pausemenu.py   (checks the four real captures in fixtures/)."""
from pathlib import Path

# Rows as canvas y (800x600), top to bottom. The fourth says Return to Garage in a practice session and Quit in a race;
# it is highlighted when the menu opens in both.
PAUSE_ROWS = [("Continue", 137), ("Restart", 167), ("Save", 200), ("Return to Garage", 233), ("Replay", 265),
              ("Autopilot", 297), ("Hide Menu", 329)]


def pause_row_of(frame):
    """Name of the highlighted (orange) row, or None if the menu isn't showing. A garage session (qualifying, warm-up,
    Time Trial) has six rows and no Autopilot: there the sixth row is Hide Menu."""
    fh, fw = frame.shape[:2]
    found, text = {}, {}
    for name, y in PAUSE_ROWS:
        band = frame[int((y - 9) * fh / 600):int((y + 9) * fh / 600), int(230 * fw / 800):int(570 * fw / 800)]
        r, gr, b = band[..., 0], band[..., 1], band[..., 2]
        orange = (r > 220) & (gr > 130) & (gr < 200) & (b < 60)
        found[name] = int(orange.sum())
        text[name] = float((orange | ((r > 235) & (gr > 235) & (b > 235))).mean())
    best = max(found, key=found.get)
    if found[best] <= 150 * fw * fh / (1280 * 720):      # a pixel count: smaller windows show fewer orange pixels
        return None
    if best == "Autopilot" and text["Hide Menu"] < 0.04:
        return "Hide Menu"
    return best


if __name__ == "__main__":
    import numpy as np
    from PIL import Image
    here = Path(__file__).resolve().parent / "fixtures"
    want = {"pause_garage_session.png": "Return to Garage", "pause_race.png": "Return to Garage",
            "pause_six_rows.png": "Hide Menu", "pause_not_showing.png": None}
    bad = 0
    for name, expected in want.items():
        got = pause_row_of(np.asarray(Image.open(here / name).convert("RGB"), dtype=np.int16))
        print("%-26s %-18s %s" % (name, got, "ok" if got == expected else "WRONG (wanted %s)" % expected))
        bad += got != expected
    raise SystemExit(1 if bad else 0)
