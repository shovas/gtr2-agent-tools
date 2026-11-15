r"""Pick the heading bias for driving straight out of the garage box, from the track's own wall meshes (garage.py).

    plan(trk, start_xz, yaw, run) -> (bias_degrees, gap_m, note)

`run` is how far the driver goes straight before turning onto the pit lane (distance to the pit line minus the merge distance, metres).
Bias 0 is kept whenever it already clears every wall by `COMFORT` m; otherwise the bias in -12..+12 with the largest gap wins (ties go to
the smaller bias). The walls near a start are cached in `scripts/gtr2_ui/runs/box_cache/` (git-ignored), so only the first run of a
layout/start pays the 4 to 7 s of reading the archives. Standard library only; reads game files, writes only the cache.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import garage  # noqa: E402

COMFORT = 0.30      # m of clearance at which the straight heading is left alone
MIN_GAP = 0.05      # m: below this the plan is reported as a failure
CACHE = Path(__file__).resolve().parent.parent / "gtr2_ui" / "runs" / "box_cache"


def walls(trk, start_xz):
    """(2D wall triangles near the start, floor height), cached per layout and start."""
    trk = Path(trk)
    key = "%s_%.1f_%.1f.json" % (trk.stem.lower(), start_xz[0], start_xz[1])
    path = CACHE / key
    try:
        data = json.loads(path.read_text())
        return [(tri, inst) for tri, inst in data["obs"]], data["floor"]
    except (OSError, ValueError, KeyError):
        pass
    obs, floor = garage.obstacles(trk, start_xz)
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"floor": floor, "obs": [[[list(p) for p in tri], inst] for tri, inst in obs]}))
    except OSError:
        pass
    return obs, floor


def plan(trk, start_xz, yaw, run, box=garage.CAR_BOX):
    """Cached by layout, start, heading, run and car box: a repeat costs a file read."""
    key = "%s|%.1f|%.1f|%.0f|%.1f|%s" % (Path(trk).stem.lower(), start_xz[0], start_xz[1], yaw, run, box)
    path = CACHE / "plans.json"
    try:
        plans = json.loads(path.read_text())
    except (OSError, ValueError):
        plans = {}
    if key in plans:
        return tuple(plans[key])
    result = _plan(trk, start_xz, yaw, run, box)
    plans[key] = list(result)
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(plans))
    except OSError:
        pass
    return result


def _plan(trk, start_xz, yaw, run, box):
    obs, _floor = walls(trk, start_xz)
    kw = {"run": max(2.0, run), "width": box[0], "length": box[1], "front": box[2]}
    reach = kw["run"] + box[1] + box[0] + 3.0
    obs = [o for o in obs if any(math.hypot(p[0] - start_xz[0], p[1] - start_xz[1]) < reach for p in o[0])]      # once, not per bias
    here = garage.footprint(start_xz[0], start_xz[1], yaw, box[0], box[1], box[2])
    obs = [o for o in obs if garage.gap(here, [o]) >= 0.15]      # already touching the parked car: the game placed it there
    g0 = garage.swept_clearance(obs, start_xz, yaw, 0.0, **kw)
    if g0 >= COMFORT:
        return 0.0, g0, "straight clears the walls by %.2f m" % g0
    (cg, cb), _ = garage.best_bias(obs, start_xz, yaw, biases=range(-12, 13, 3), **kw)          # coarse, then fine around the best
    (best_gap, best), _rows = garage.best_bias(obs, start_xz, yaw, biases=range(cb - 2, cb + 3), **kw)
    if best_gap < MIN_GAP:
        return 0.0, best_gap, "no heading bias in -12..12 clears the walls (best %+d, gap %.2f m): keeping the straight heading" % (best, best_gap)
    return float(best), best_gap, "straight run %s (gap %.2f m); bias %+d gives %.2f m" % (
        "hits a wall" if g0 < 0 else "clears by only %.2f m" % g0, g0, best, best_gap)
