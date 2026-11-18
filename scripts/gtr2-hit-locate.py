r"""Where, on the track, was each hit? Takes the impacts of a lap result (gtr2_ui/runs/lap_results.jsonl, the last line by default; or --xz X Z)
and places every one on the track map: which waypoint chain (racing line or pit lane), the distance along it and the share of the lap, the sideways offset
from the centre line against the road's left and right edges (the AIW widths), and the nearest collision structures of the track's own meshes (the .trk
instance name, the distance and the height of the nearest near-vertical face), so a repeated hit can be traced to a wall, barrier, building or kerb
and avoided in the planner.

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-hit-locate.py [--line N] [--which impacts|kerbs|contacts] [--xz X Z --layout Spa/4Spa.trk] [--radius 12] [--no-mesh]
Needs the game folder and numpy-free Python only (uses gtr2_driving/trackmap.py, garage.py, gmt.py, mas.py).
"""
import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "gtr2_driving"))
sys.path.insert(0, str(HERE / "gtr2_ui"))
import diag  # noqa: E402
import garage  # noqa: E402
import trackmap  # noqa: E402
from gmt import GmtError, parse  # noqa: E402

RESULTS = HERE / "gtr2_ui" / "runs" / "lap_results.jsonl"


def find_file(folder, stem, ext):
    for p in folder.iterdir():
        if p.suffix.lower() == ext and p.stem.lower() == stem.lower():
            return p
    return None


def chain_info(chain):
    cum, d = [0.0], 0.0
    for a, b in zip(chain, chain[1:] + chain[:1]):
        d += math.hypot(b.x - a.x, b.z - a.z)
        cum.append(d)
    return cum


def place(track, cums, x, z, pit_hint):
    best = None
    for name, chain in (("pit", track.pit), ("main", track.main)):
        if not chain:
            continue
        k = track.nearest(chain, x, z)
        w = chain[k]
        d = math.hypot(w.x - x, w.z - z)
        if best is None or d < best[0] - (6.0 if (name == "pit") == pit_hint else 0.0):
            best = (d, name, chain, k)
    d, name, chain, k = best
    w = chain[k]
    lat = track.lateral(w, x, z)
    return {"chain": name, "k": k, "of": len(chain), "dist_m": cums[name][k], "length_m": cums[name][-1], "lat": lat, "left": w.left, "right": w.right,
            "off_centre_edge_m": (w.right - lat) if lat >= 0 else (w.left + lat), "wp_dist": d}


def near_structures(trk, pts, radius):
    """{instance: [(distance, height range, steep?) per point]} from the collision meshes, triangles within `radius` of any point only."""
    arcs = [garage._mas(p) for p in garage.archives(trk)]
    found = [{} for _ in pts]
    for inst, mesh_name in garage.collision_meshes(trk):
        key = mesh_name.upper()
        data = next((a.read(key) for a in arcs if key in a.entries), None)
        if data is None:
            continue
        try:
            meshes = parse(data)
        except GmtError:
            continue
        for mesh in meshes:
            v = mesh["vertices"]
            for i, j, k in mesh["triangles"]:
                tri = (v[i], v[j], v[k])
                for n, (px, pz) in enumerate(pts):
                    if not any(math.hypot(p[0] - px, p[2] - pz) < radius for p in tri):
                        continue
                    poly = [(p[0], p[2]) for p in tri]
                    dd = 0.0 if garage._inside((px, pz), poly) else min(garage._seg_dist((px, pz), poly[a], poly[(a + 1) % 3]) for a in range(3))
                    ys = [p[1] for p in tri]
                    steep = garage.steep(tri)
                    cur = found[n].get(inst)
                    if cur is None or (steep, -dd) > (cur[2], -cur[0]):
                        found[n][inst] = (dd, (min(ys), max(ys)), steep)
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", type=int, default=-1, help="which line of lap_results.jsonl (default the last)")
    ap.add_argument("--which", default="impacts", choices=("impacts", "kerbs", "contacts"))
    ap.add_argument("--xz", type=float, nargs=2)
    ap.add_argument("--layout", help="with --xz: the layout, e.g. Spa/4Spa.trk")
    ap.add_argument("--radius", type=float, default=12.0, help="collision structures within this many metres")
    ap.add_argument("--no-mesh", action="store_true")
    a = ap.parse_args()
    if a.xz:
        layout, hits = a.layout, [{"x": a.xz[0], "z": a.xz[1], "t": 0, "a": 0, "pit": False}]
    else:
        lines = [l for l in RESULTS.read_text(encoding="utf-8").splitlines() if l.strip()]
        rec = json.loads(lines[a.line])
        layout, hits = rec["layout"], (rec.get("result") or {}).get(a.which) or []
        print("%s with %s: %d %s" % (layout, rec.get("car"), len(hits), a.which))
    if not layout or not hits:
        return 0
    trk = trackmap.ROOT / "GameData" / "Locations" / layout
    aiw = find_file(trk.parent, trk.stem, ".aiw") or find_file(trk.parent, trk.stem.lstrip("0123456789"), ".aiw")
    if aiw is None:
        print("no AIW found for", layout)
        return 1
    track = trackmap.Track(str(aiw))
    cums = {"main": chain_info(track.main), "pit": chain_info(track.pit) if track.pit else [0.0]}
    pts = [(h["x"], h["z"]) for h in hits]
    structs = [{}] * len(hits) if a.no_mesh else near_structures(trk, pts, a.radius)
    for h, s in zip(hits, structs):
        p = place(track, cums, h["x"], h["z"], bool(h.get("pit")))
        print("t=%6.1f s  a=%5.1f  (%.1f, %.1f)  %s waypoint %d/%d, %.0f m along (%.0f%% of %.0f m), %.1f m %s of the centre line (road %.1f left / %.1f right), %.1f m to the road edge" % (
            h.get("t", 0), h.get("a", 0), h["x"], h["z"], p["chain"], p["k"], p["of"], p["dist_m"], 100.0 * p["dist_m"] / max(p["length_m"], 1.0), p["length_m"],
            abs(p["lat"]), "right" if p["lat"] >= 0 else "left", p["left"], p["right"], p["off_centre_edge_m"]))
        walls = sorted(((d, i, hr) for i, (d, hr, st) in s.items() if st), key=lambda r: r[0])[:3]
        floors = sorted(((d, i, hr) for i, (d, hr, st) in s.items() if not st), key=lambda r: r[0])[:2]
        for d, inst, hr in walls:
            print("      near-vertical face: %-28s %5.1f m away, height %.1f to %.1f" % (inst, d, hr[0], hr[1]))
        for d, inst, hr in floors:
            print("      surface:            %-28s %5.1f m away, height %.1f to %.1f" % (inst, d, hr[0], hr[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
