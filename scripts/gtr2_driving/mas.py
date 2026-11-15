r"""Reader for the game's `.gtr` archives (ISI "GMOTORMAS10" containers, the same family as rFactor MAS files).

Layout (checked against Anderstorp.gtr; the field order follows Grumbel's rfactortools mas.bms, type 0):
    0x00  16 bytes   "GMOTORMAS10" + NULs
    0x10  uint32     number of files
    0x14  uint32     total data size
    0x18  directory: one 256-byte record per file = dummy(4), offset(4, from the end of the directory), size(4, unpacked),
          zsize(4, stored; equal to size or 0 = stored as is), name(240, NUL padded)
    after the directory: the file data, each file stored with zlib when zsize differs from size.
Standard library only. Only reads.

    python -I scripts\gtr2_driving\mas.py list  ARCHIVE.gtr [PATTERN]
    python -I scripts\gtr2_driving\mas.py cat   ARCHIVE.gtr NAME            (raw bytes to stdout, hex dump when a terminal)
    python -I scripts\gtr2_driving\mas.py extract ARCHIVE.gtr OUTDIR [PATTERN]
"""
import re
import struct
import sys
import zlib
from pathlib import Path

HEADER = 0x18
RECORD = 256
MAGIC = b"GMOTORMAS10"


class Entry:
    def __init__(self, name, offset, size, zsize):
        self.name, self.offset, self.size, self.zsize = name, offset, size, zsize

    def __repr__(self):
        return "Entry(%s, size %d, stored %d)" % (self.name, self.size, self.zsize)


class Mas:
    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        if not self.data.startswith(MAGIC):
            raise ValueError("%s is not a GMOTORMAS10 archive (starts with %r)" % (path, self.data[:12]))
        self.count, self.data_size = struct.unpack_from("<II", self.data, 0x10)
        self.base = HEADER + self.count * RECORD
        self.entries = {}
        for i in range(self.count):
            at = HEADER + i * RECORD
            _dummy, offset, size, zsize = struct.unpack_from("<IIII", self.data, at)
            name = self.data[at + 16: at + RECORD].split(b"\0")[0].decode("latin1")
            self.entries[name.upper()] = Entry(name, offset, size, zsize or size)

    def names(self, pattern=None):
        rx = re.compile(pattern, re.I) if pattern else None
        return [e.name for e in self.entries.values() if rx is None or rx.search(e.name)]

    def read(self, name):
        e = self.entries[name.upper()]
        raw = self.data[self.base + e.offset: self.base + e.offset + e.zsize]
        if e.zsize == e.size:
            return raw
        out = zlib.decompress(raw)
        if len(out) != e.size:
            raise ValueError("%s: unpacked %d bytes, expected %d" % (name, len(out), e.size))
        return out


def main(argv):
    if len(argv) < 3 or argv[1] not in ("list", "cat", "extract"):
        print(__doc__)
        return 2
    mas = Mas(argv[2])
    if argv[1] == "list":
        for n in mas.names(argv[3] if len(argv) > 3 else None):
            e = mas.entries[n.upper()]
            print("%-40s %9d %9d" % (e.name, e.size, e.zsize))
    elif argv[1] == "cat":
        data = mas.read(argv[3])
        if sys.stdout.isatty():
            for i in range(0, min(len(data), 512), 16):
                print("%06x  %s" % (i, data[i:i + 16].hex(" ")))
        else:
            sys.stdout.buffer.write(data)
    else:
        out = Path(argv[3])
        out.mkdir(parents=True, exist_ok=True)
        n = 0
        for name in mas.names(argv[4] if len(argv) > 4 else None):
            (out / name).write_bytes(mas.read(name))
            n += 1
        print("extracted %d files to %s" % (n, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
