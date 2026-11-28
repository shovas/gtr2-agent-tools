"""Check that CLAUDE.md stays a reliable index: every file it names exists, every docs/ and knowledge/ file is reachable from it, and its size stays near 10 KB.

Usage:  python -I scripts\\check-claude-md.py [--mode quick|normal|full]   (exit 1 on any failure; stdlib only)
Quick (the default here) runs every check; it takes well under a second.
"""
import argparse, glob, os, re, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SIZE_WARN = 10 * 1024
SIZE_FAIL = 12 * 1024


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("quick", "normal", "full"), default="quick")
    args = ap.parse_args()
    text = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    failures, warnings = [], []

    size = len(text.encode("utf-8"))
    if size > SIZE_FAIL:
        failures.append("CLAUDE.md is %d bytes (limit %d)" % (size, SIZE_FAIL))
    elif size > SIZE_WARN:
        warnings.append("CLAUDE.md is %d bytes (aim for about %d)" % (size, SIZE_WARN))

    named = set(re.findall(r"`((?:docs|knowledge|scripts)/[^`]+?\.(?:md|py|ps1))`", text))
    named |= set(re.findall(r"`(docs\\[^`]+?\.md)`", text.replace("/", "\\")))
    named = {p.replace("\\", "/") for p in named}
    for rel in sorted(named):
        if not os.path.exists(os.path.join(ROOT, rel)):
            failures.append("named in CLAUDE.md but missing: %s" % rel)

    # docs/*.md must be named in CLAUDE.md; knowledge files must be named in knowledge/INDEX.md (reached from CLAUDE.md)
    docs = {os.path.relpath(p, ROOT).replace("\\", "/") for p in glob.glob(os.path.join(ROOT, "docs", "*.md"))}
    for rel in sorted(docs - named):
        failures.append("not reachable from CLAUDE.md (orphan): %s" % rel)
    index = open(os.path.join(ROOT, "knowledge", "INDEX.md"), encoding="utf-8").read()
    kn = {os.path.relpath(p, ROOT).replace("\\", "/") for p in glob.glob(os.path.join(ROOT, "knowledge", "**", "*.md"), recursive=True)}
    for rel in sorted(kn - {"knowledge/INDEX.md"}):
        short = rel[len("knowledge/"):]
        if short not in index:
            failures.append("not listed in knowledge/INDEX.md (orphan): %s" % rel)
    on_disk = docs | kn

    for w in warnings:
        print("WARN  " + w)
    for f in failures:
        print("FAIL  " + f)
    print("checked %d named files, %d docs/knowledge files, size %d bytes; %d failure(s), %d warning(s)"
          % (len(named), len(on_disk), size, len(failures), len(warnings)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
