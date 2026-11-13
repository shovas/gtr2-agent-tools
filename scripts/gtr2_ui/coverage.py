"""How much of the menu map is covered: pages in the menu file, pages with a saved reference image, pages a tour path visits.
Usage: scripts/.venv/Scripts/python.exe -I scripts/gtr2_ui/coverage.py [--list]"""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import menumap  # noqa: E402
from paths import BASELINES, LOCAL_BASELINES  # noqa: E402


def names(d):
    return {f.name[:-4].replace("+", " ") for f in d.glob("*.png") if not f.name.endswith(".mask.png")}


def main():
    pages, _ = menumap.load()
    sib, loc = names(BASELINES), names(LOCAL_BASELINES)
    refs = sib | loc
    toured = set()
    for f in (HERE.parent / "nav_paths").glob("*.txt"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                c = [x.strip() for x in line.split("|")]
                toured.add(c[0].split("=")[-1])
                if len(c) > 2:
                    toured.update(x.strip() for x in c[2].split(","))
    allp = set(pages)
    safe = menumap.safe_reachable(pages)
    modal = {n for n, p in pages.items() if getattr(p, "modal", False)}
    print("pages in the menu map          : %d (%d modal popups)" % (len(allp), len(modal)))
    print("reachable by plain nav buttons : %d" % len(set(safe) & allp))
    print("with a reference image         : %d of %d (shipped %d, local overrides %d)" % (len(refs & allp), len(allp), len(sib & allp), len(loc & allp)))
    print("visited by a tour path         : %d" % len(toured & allp))
    print("references not in the map      : %d" % len(refs - allp))
    if "--list" in sys.argv:
        print("\nNO REFERENCE:"); [print("  ", n) for n in sorted(allp - refs)]
        print("\nREFERENCE BUT NO TOUR:"); [print("  ", n) for n in sorted((refs & allp) - toured)]
        print("\nTOUR BUT NO REFERENCE:"); [print("  ", n) for n in sorted((toured & allp) - refs)]


def entry_points():
    """Pages with no reference, and the buttons on referenced pages that lead to them (what a new tour would press)."""
    pages, _ = menumap.load()
    refs = names(BASELINES) | names(LOCAL_BASELINES)
    out = {}
    for pn, page in pages.items():
        if pn not in refs:
            continue
        for b in page.buttons:
            for t in b.targets:
                if t in pages and t not in refs:
                    risk = menumap.never_press(b) or menumap.page_risk(t) or ""
                    out.setdefault(t, []).append("%s | %s%s" % (pn, b.label, "  [%s]" % risk if risk else ""))
    return out


if "--entries" in sys.argv:
    for t, srcs in sorted(entry_points().items()):
        print("%-40s <- %s" % (t, "; ".join(srcs[:3])))
    sys.exit(0)
main()
