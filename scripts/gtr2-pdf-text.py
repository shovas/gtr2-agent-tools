r"""Extract the text of a PDF with the standard library only (FlateDecode streams, Tj/TJ text operators), for reading reference books without installing anything.

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-pdf-text.py BOOK.pdf [--out BOOK.txt] [--limit 6000]

Nothing in the PDF is executed or rendered; only the text-showing operators are read. It works for PDFs with an ordinary text layer (the three books of the
reference folder `..\gtr2-agent-tools-reference` read fine); fonts that use a custom glyph encoding without a ToUnicode map come out as garbage (the Ross Bentley
PDFs from speedsecrets.com do), and scanned pages have no text at all. Page order follows the content streams; headers and footers appear inline. Write the
output outside the repository (a scratch directory): the books are copyrighted and must not be committed (docs/publishing.md).
"""
import argparse
import re
import sys
import zlib
from pathlib import Path

STR = rb"\(((?:\\.|[^\\)])*)\)"


def extract(data):
    out = []
    for m in re.finditer(rb"stream\r?\n", data):
        s = m.end()
        e = data.find(b"endstream", s)
        if e < 0:
            continue
        raw = data[s:e]
        try:
            dec = zlib.decompress(raw)
        except Exception:
            try:
                dec = zlib.decompressobj().decompress(raw)
            except Exception:
                continue
        if b"BT" not in dec:
            continue
        txt = []
        for bt in re.finditer(rb"BT(.*?)ET", dec, re.S):
            blk = bt.group(1)
            for t in re.finditer(rb"\[(.*?)\]\s*TJ|" + STR + rb"\s*Tj", blk, re.S):
                if t.group(1) is not None:
                    s_ = b""
                    for a, n in re.findall(STR + rb"|(-?\d+\.?\d*)", t.group(1)):
                        if a:
                            s_ += a
                        elif n and float(n) < -200:
                            s_ += b" "
                    txt.append(s_)
                else:
                    txt.append(t.group(2))
            txt.append(b"\n")
        out.append(b"".join(txt))
    res = b"\n".join(out).decode("latin1")
    res = re.sub(r"\\([()\\])", r"\1", res)
    return re.sub(r"\n\s*\n+", "\n", res)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pdf")
    ap.add_argument("--out", help="write the whole text to this file (outside the repository)")
    ap.add_argument("--limit", type=int, default=6000, help="characters to print when --out is not given")
    a = ap.parse_args()
    text = extract(Path(a.pdf).read_bytes())
    if not text.strip():
        print("no text layer found in %s" % a.pdf, file=sys.stderr)
        return 1
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print("%d characters written to %s" % (len(text), a.out))
    else:
        print(text[:a.limit])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
