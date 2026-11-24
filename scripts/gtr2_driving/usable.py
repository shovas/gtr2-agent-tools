"""How far sideways can the car go at each waypoint before it touches a structure of the track's own collision meshes (kerb blocks, bollards, walls, tyre
stacks) that lies INSIDE the road width? The AIW gives only the road edges; the line optimiser and the line smoothing used them as the limit, so a line could be
planned through a kerb the game builds as a near-vertical block (Imola's apex kerb `Kerbs21` at 3126 m, 4.5 m from the centre line on a road 5.8 to 7.1 m wide).

    ul, ur = usable_widths(track, trk_path, aiw_stem)       # per main waypoint: the left and right half widths, as if the road ended at the structure
    apply(track, ul, ur)                                     # sets w.uleft / w.uright; racingline.geometry and Track.smooth_line use them when present

The track-limit judging (limits.py) does not use these: it keeps the road edges as the file gives them. A free width is the largest sideways distance (0.5 m
steps from the centre line, left = positive as Track.lateral) at which the car's outline stays `gap` metres clear of every near-vertical face
(hitgeom.WallIndex.clearance); the usable half width is that plus the side margin the callers subtract (1.6 m), so the line keeps `gap` m off the face.
Computed once per track (about 2 s per 100 m) and cached in line_cache/ (git-ignored, per machine).
"""
import hashlib
import json
import math
from pathlib import Path

import hitgeom

CACHE = Path(__file__).resolve().parent / "line_cache"
STEP = 0.5
REACH = 9.0      # no need to look further than the widest roads
SIDE_MARGIN = 1.6      # what racingline.optimise (--line-opt-margin) subtracts from a width


def _free(idx, w, sign, gap):
    yaw = math.degrees(math.atan2(-w.hx, -w.hz))
    s, last = 0.0, 0.0
    while s <= REACH:
        x, z = w.x + sign * s * -w.hz, w.z + sign * s * w.hx
        g, _ = idx.clearance(x, w.y, z, yaw)
        if g is not None and g < gap:
            break
        last = s
        s += STEP
    return last


def _key(track, trk_path, gap):
    h = hashlib.sha1()
    h.update(("v1|%.2f|%d|%d|" % (gap, len(track.main), Path(trk_path).stat().st_size)).encode())
    for w in track.main[:: max(1, len(track.main) // 40)]:
        h.update(("%.1f,%.1f;" % (w.x, w.z)).encode())
    return h.hexdigest()[:16]


def usable_widths(track, trk_path, aiw_stem, gap=0.3, log=print):
    """(left list, right list) of usable half widths for track.main; cached."""
    CACHE.mkdir(exist_ok=True)
    f = CACHE / ("%s_usable_%s.json" % (aiw_stem.lower(), _key(track, trk_path, gap)))
    if f.exists():
        d = json.loads(f.read_text())
        return d["left"], d["right"]
    idx = hitgeom.WallIndex(trk_path)
    log("usable widths: probing %d waypoints against %d wall faces (once per track)" % (len(track.main), idx.count))
    left, right = [], []
    for w in track.main:
        # sign +1 is the side the optimiser limits by the LEFT width (see racingline.optimise), -1 by the RIGHT width
        left.append(round(min(w.left, _free(idx, w, 1.0, gap) + SIDE_MARGIN), 2))
        right.append(round(min(w.right, _free(idx, w, -1.0, gap) + SIDE_MARGIN), 2))
    f.write_text(json.dumps({"left": left, "right": right}))
    return left, right


def apply(track, left, right, log=print):
    narrowed = 0
    for w, l_, r_ in zip(track.main, left, right):
        w.uleft, w.uright = l_, r_
        if l_ < w.left - 0.05 or r_ < w.right - 0.05:
            narrowed += 1
    log("usable widths: %d of %d waypoints have a structure inside the road width" % (narrowed, len(track.main)))
    return narrowed
