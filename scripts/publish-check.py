r"""Pre-push privacy and safety check for this repository (see docs/publishing.md for the rules it enforces).

Scans what would be pushed (tracked files and every commit not yet on the remote, or all history with --all-history) for personal
details, secrets and game content, and lists what is blocked, what needs a human decision and what is fine. Read-only: it never
changes the repository and never pushes. Standard library plus git only.

    python -I scripts\publish-check.py                 check commits not yet on origin plus every tracked file
    python -I scripts\publish-check.py --all-history   also scan the whole history (what a new public repository would expose)
    python -I scripts\publish-check.py --identity "Name <noreply-address>"   the author identity that is acceptable to publish

Exit code 0: nothing blocked. 1: at least one BLOCK (do not push). Review items (REVIEW) always need a human yes.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOCK_PATTERNS = [
    (r"[A-Za-z]:\\Users\\[A-Za-z0-9 ._-]+|/c/Users/[A-Za-z0-9._-]+|/home/[a-z0-9._-]+/", "absolute user path"),
    (r"\b[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com|anthropic\.com|github\.com)[A-Za-z0-9.-]+\.(com|ca|net|org|io|dev|me|uk|de|fr)\b", "e-mail address"),
    (r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----", "secret or key"),
    (r"\b(?i:api[_-]?key|secret|passw(?:or)?d)\s*[:=]\s*['\"][^'\"]{6,}", "credential assignment"),
]
# text files that name patterns on purpose (the rules themselves, example addresses)
SELF = {"scripts/publish-check.py", "docs/publishing.md"}
BLOCK_EXT = {".exe", ".dll", ".bik", ".gtr", ".mas", ".gmt", ".dds", ".dmp", ".plr", ".ini", ".sys", ".vdf", ".zip", ".7z", ".rar"}
BIG_BYTES = 1_000_000


def git(*a):
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, errors="replace").stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--all-history", action="store_true")
    ap.add_argument("--identity", default="", help="the one author identity that may be published (name and noreply e-mail)")
    ap.add_argument("--remote", default="origin")
    a = ap.parse_args()
    block, review = [], []

    files = [f for f in git("ls-files").splitlines() if f]
    for f in files:
        p = ROOT / f
        ext = p.suffix.lower()
        if ext in BLOCK_EXT:
            block.append("game or system file type tracked: %s" % f)
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size > BIG_BYTES:
            review.append("large file (%d KB): %s" % (size // 1024, f))
        if ext in {".png", ".jpg", ".bmp", ".gif"}:
            continue
        if f in SELF:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for rx, what in BLOCK_PATTERNS:
            for m in re.finditer(rx, text):
                line = text.count("\n", 0, m.start()) + 1
                block.append("%s in %s:%d: %s" % (what, f, line, m.group(0)[:60]))
                break
    pics = [f for f in files if f.lower().endswith((".png", ".jpg", ".bmp"))]
    if pics:
        review.append("%d picture(s) tracked (reference screenshots of the game's own screens): confirm they are allowed and carry no player name, e.g. %s" % (len(pics), pics[0]))

    rng = []
    if not a.all_history:
        has_remote = git("rev-parse", "--verify", "--quiet", "%s/HEAD" % a.remote).strip()
        rng = ["%s/HEAD..HEAD" % a.remote] if has_remote else []
    revs = git("log", *rng, "--format=%H").split()
    seen = set()
    for h in revs:
        who = git("log", "-1", "--format=%an <%ae>|%cn <%ce>", h).strip()
        for ident in who.split("|"):
            if ident not in seen:
                seen.add(ident)
                ok = ident == a.identity or "noreply@github.com" in ident or "@users.noreply.github.com" in ident
                (review if not ok else []).append("commit identity to be published: %s (first seen at %s)" % (ident, h[:7]))
        msg = git("log", "-1", "--format=%B", h)
        for rx, what in BLOCK_PATTERNS:
            m = re.search(rx, msg)
            if m:
                block.append("%s in the message of %s: %s" % (what, h[:7], m.group(0)[:60]))
        if a.all_history or rng:
            diff = git("show", "--format=", "-U0", h, "--", ".", ":!*.png", ":!scripts/publish-check.py", ":!docs/publishing.md")
            for rx, what in BLOCK_PATTERNS:
                m = next((re.search(rx, l) for l in diff.splitlines() if l.startswith("+") and re.search(rx, l)), None)
                if m:
                    block.append("%s added in commit %s: %s" % (what, h[:7], m.group(0)[:60]))
    print("scanned %d tracked file(s), %d commit(s)%s" % (len(files), len(revs), " (all history)" if a.all_history else " not yet on %s" % a.remote))
    for b in block:
        print("BLOCK  " + b)
    for r in review:
        print("REVIEW " + r)
    if not block and not review:
        print("nothing found")
    print("%d block(s), %d review item(s)" % (len(block), len(review)))
    return 1 if block else 0


if __name__ == "__main__":
    sys.exit(main())
