"""Explain a GTR2 crash dump: exception, faulting module, call stack, loaded modules (works on the standard library alone; adding dependencies is fine: pin them in scripts/requirements.txt, see CLAUDE.md; capstone and pefile are optional extras already used).

Purpose: the game writes UserData/Log/Minidump/GTR2_*.dmp when it crashes; nothing else reads them. This prints a report,
optionally only the short summary, and can save the dump and its report before a test's clean-up deletes it.
Usage:   python -I scripts/gtr2-crash-report.py DUMP [--short] [--save-dir DIR]
         python -I scripts/gtr2-crash-report.py --latest        (newest dump under <game folder>/UserData/Log/Minidump)
Example: python -I scripts/gtr2-crash-report.py --latest --short
"""
import argparse
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS / "gtr2_ui"))
import diag  # noqa: E402
from minidump import MiniDump  # noqa: E402


def summary(d):
    e = d.exception
    if not e:
        return "no exception record"
    from minidump import EXCEPTIONS
    first = [d.where(a) for _k, a in d.stack(4)]
    return "0x%08X %s at %s; stack: %s" % (e["code"], EXCEPTIONS.get(e["code"], "unknown"), d.where(e["address"]), " <- ".join(first[1:4]) or "-")


def save(dump, outdir):
    """Write the dump's report (never the dump itself: they are about 230 MB) into outdir as <dump name>.txt; returns its path."""
    outdir.mkdir(parents=True, exist_ok=True)
    d = MiniDump(dump)
    rep = outdir / (Path(dump).stem + ".txt")
    rep.write_text(d.report() + "\n", encoding="utf-8")
    d.close()
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dump", nargs="?", help="the .dmp file")
    ap.add_argument("--latest", action="store_true", help="use the newest dump in the game folder's UserData/Log/Minidump")
    ap.add_argument("--short", action="store_true", help="one line: exception, fault location, top of the stack")
    ap.add_argument("--save-dir", help="also write the report as <dump name>.txt here (the dump itself is never copied)")
    a = ap.parse_args()
    if a.latest:
        dumps = sorted((diag.game_root() / "UserData" / "Log" / "Minidump").glob("*.dmp"), key=lambda p: p.stat().st_mtime)
        if not dumps:
            print("no dump found under %s" % (diag.game_root() / "UserData" / "Log" / "Minidump"))
            return 1
        path = dumps[-1]
    elif a.dump:
        path = Path(a.dump)
    else:
        ap.error("give a dump or --latest")
    d = MiniDump(path)
    print(summary(d) if a.short else d.report())
    d.close()
    if a.save_dir:
        print("saved:", save(path, Path(a.save_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
