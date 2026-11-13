"""Read a Windows minidump (.dmp) with the standard library only: what crashed, where, and what was loaded.

Needs only the standard library (adding dependencies is fine: pin them in scripts/requirements.txt, see CLAUDE.md); capstone and pefile (scripts/requirements.txt) add disassembly and section names when installed.
Purpose: GTR2 writes UserData/Log/Minidump/GTR2_*.dmp when it crashes. This reads the exception, the faulting thread's
registers, the loaded modules, the OS and a best-effort call stack, without a debugger. The game is a 32-bit process, so
the x86 register layout is decoded; an x64 context is decoded for its instruction, stack and frame pointers only.
Usage:   from minidump import MiniDump; d = MiniDump(path); print(d.report())
Example: python -I scripts/gtr2-crash-report.py <dump>
"""
import mmap
import struct
from datetime import datetime, timezone

STREAM_THREADS, STREAM_MODULES, STREAM_MEMORY, STREAM_EXCEPTION, STREAM_SYSTEM, STREAM_MEMORY64 = 3, 4, 5, 6, 7, 9

EXCEPTIONS = {
    0xC0000005: "ACCESS_VIOLATION", 0xC000001D: "ILLEGAL_INSTRUCTION", 0xC0000094: "INTEGER_DIVIDE_BY_ZERO",
    0xC00000FD: "STACK_OVERFLOW", 0xC0000374: "HEAP_CORRUPTION", 0xC0000409: "STACK_BUFFER_OVERRUN / fail-fast",
    0xC0000025: "NONCONTINUABLE_EXCEPTION", 0x80000003: "BREAKPOINT", 0xC0000096: "PRIVILEGED_INSTRUCTION",
    0xE06D7363: "C++ exception (throw)", 0xC000008C: "ARRAY_BOUNDS_EXCEEDED", 0xC0000006: "IN_PAGE_ERROR",
}
ARCH = {0: "x86", 5: "ARM", 9: "x64", 12: "ARM64"}


class MiniDump:
    def __init__(self, path):
        self.path = str(path)
        self._f = open(self.path, "rb")
        self.m = mmap.mmap(self._f.fileno(), 0, access=mmap.ACCESS_READ)
        sig, ver, nstreams, dir_rva, _chk, stamp, _flags = struct.unpack_from("<4sIIIIIQ", self.m, 0)
        if sig != b"MDMP":
            raise ValueError("not a minidump: " + self.path)
        self.time = datetime.fromtimestamp(stamp, timezone.utc) if stamp else None
        self.streams = {}
        for i in range(nstreams):
            t, size, rva = struct.unpack_from("<III", self.m, dir_rva + 12 * i)
            self.streams[t] = (size, rva)
        self.modules = self._read_modules()
        self.ranges = self._read_memory()
        self.system = self._read_system()
        self.exception = self._read_exception()

    def close(self):
        self.m.close()
        self._f.close()

    def _string(self, rva):
        n, = struct.unpack_from("<I", self.m, rva)
        return self.m[rva + 4: rva + 4 + n].decode("utf-16-le", "replace")

    def _read_modules(self):
        out = []
        if STREAM_MODULES not in self.streams:
            return out
        rva = self.streams[STREAM_MODULES][1]
        n, = struct.unpack_from("<I", self.m, rva)
        for i in range(n):
            o = rva + 4 + 108 * i
            base, size, _chk, stamp, name_rva = struct.unpack_from("<QIIII", self.m, o)
            sig, _sv, fv_hi, fv_lo = struct.unpack_from("<IIII", self.m, o + 24)
            ver = "%d.%d.%d.%d" % (fv_hi >> 16, fv_hi & 0xFFFF, fv_lo >> 16, fv_lo & 0xFFFF) if sig == 0xFEEF04BD else ""
            out.append({"base": base, "size": size, "name": self._string(name_rva), "version": ver, "stamp": stamp})
        return out

    def _read_memory(self):
        out = []   # (start, size, file offset)
        if STREAM_MEMORY64 in self.streams:
            rva = self.streams[STREAM_MEMORY64][1]
            n, base_rva = struct.unpack_from("<QQ", self.m, rva)
            off = base_rva
            for i in range(n):
                start, size = struct.unpack_from("<QQ", self.m, rva + 16 + 16 * i)
                out.append((start, size, off))
                off += size
        if STREAM_MEMORY in self.streams:
            rva = self.streams[STREAM_MEMORY][1]
            n, = struct.unpack_from("<I", self.m, rva)
            for i in range(n):
                start, size, drva = struct.unpack_from("<QII", self.m, rva + 4 + 16 * i)
                out.append((start, size, drva))
        return sorted(out)

    def _read_system(self):
        if STREAM_SYSTEM not in self.streams:
            return {}
        rva = self.streams[STREAM_SYSTEM][1]
        arch, level, rev, ncpu, ptype, major, minor, build, platform, csd_rva = struct.unpack_from("<HHHBBIIIII", self.m, rva)
        return {"arch": ARCH.get(arch, str(arch)), "cpus": ncpu, "os": "%d.%d build %d" % (major, minor, build),
                "service_pack": self._string(csd_rva) if csd_rva else ""}

    def _read_exception(self):
        if STREAM_EXCEPTION not in self.streams:
            return None
        rva = self.streams[STREAM_EXCEPTION][1]
        tid, _pad, code, flags, _chain, addr, nparams, _u = struct.unpack_from("<IIIIQQII", self.m, rva)
        params = list(struct.unpack_from("<%dQ" % min(nparams, 15), self.m, rva + 40))
        ctx_size, ctx_rva = struct.unpack_from("<II", self.m, rva + 8 + 152)
        ctx = self.m[ctx_rva: ctx_rva + ctx_size]
        return {"thread": tid, "code": code, "flags": flags, "address": addr, "params": params, "context": self._decode_context(ctx)}

    def _decode_context(self, c):
        arch = self.system.get("arch")
        if arch == "x64" and len(c) >= 256:
            ip, sp, bp = struct.unpack_from("<QQQ", c, 248)[0], struct.unpack_from("<Q", c, 152)[0], struct.unpack_from("<Q", c, 160)[0]
            return {"bits": 64, "eip": ip, "esp": sp, "ebp": bp, "regs": {}}
        if len(c) < 204:
            return {"bits": 32, "eip": 0, "esp": 0, "ebp": 0, "regs": {}}
        names = ("edi", "esi", "ebx", "edx", "ecx", "eax", "ebp", "eip", "cs", "eflags", "esp", "ss")
        vals = struct.unpack_from("<12I", c, 156)
        regs = dict(zip(names, vals))
        return {"bits": 32, "eip": regs["eip"], "esp": regs["esp"], "ebp": regs["ebp"], "regs": regs}

    def read(self, addr, n):
        """n bytes of the dumped process memory at addr, or None if not in the dump."""
        for start, size, off in self.ranges:
            if start <= addr and addr + n <= start + size:
                return bytes(self.m[off + addr - start: off + addr - start + n])
        return None

    def module_at(self, addr):
        for mod in self.modules:
            if mod["base"] <= addr < mod["base"] + mod["size"]:
                return mod
        return None

    def where(self, addr):
        mod = self.module_at(addr)
        if not mod:
            return "0x%08X (no module)" % addr
        return "%s+0x%X (0x%08X)" % (mod["name"].replace("\\", "/").rsplit("/", 1)[-1], addr - mod["base"], addr)

    def disasm(self, addr, before=96, after=24):
        """x86 instructions around addr read from the dump's memory, with the instruction at addr marked ('>>').
        Needs capstone (optional); returns [] without it. The start is the earliest byte offset whose linear decode lands
        exactly on addr, preferring one right after int3 padding (a function start)."""
        try:
            import capstone
        except ImportError:
            return []
        data = self.read(addr - before, before + after)
        if not data:
            return []
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        best = None
        for off in range(0, before):
            pos, ok = off, False
            while pos < before:
                ins = next(md.disasm(data[pos:pos + 16], addr - before + pos), None)
                if not ins:
                    break
                pos += ins.size
            if pos == before:
                ok = True
            if ok:
                if best is None:
                    best = off
                if off > 0 and data[off - 1] == 0xCC:
                    best = off
        if best is None:
            return []
        out, pos = [], best
        while pos < before + after:
            ins = next(md.disasm(data[pos:pos + 16], addr - before + pos), None)
            if not ins:
                break
            a = addr - before + pos
            out.append("%s %08X  %-24s %s %s" % (">>" if a == addr else "  ", a, data[pos:pos + ins.size].hex(" "), ins.mnemonic, ins.op_str))
            pos += ins.size
        return out

    def section_of(self, addr):
        """(section name, rva) of an address inside a module's image, from the module's PE header in the dump (pefile optional)."""
        mod = self.module_at(addr)
        if not mod:
            return None
        hdr = self.read(mod["base"], 0x400)
        try:
            import pefile
            pe = pefile.PE(data=hdr, fast_load=True)
            rva = addr - mod["base"]
            for s in pe.sections:
                if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
                    return s.Name.rstrip(b"\0").decode("latin1"), rva
        except Exception:
            pass
        return None

    def stack(self, limit=24):
        """Best-effort x86 call stack: the faulting address, then the frame-pointer chain, then return-address-looking
        words on the stack (words that point into a module and follow a call instruction)."""
        e = self.exception
        if not e or e["context"]["bits"] != 32:
            return []
        ctx = e["context"]
        frames = [("fault", e["address"] or ctx["eip"])]
        ebp, seen = ctx["ebp"], set()
        while ebp and ebp not in seen and len(frames) < limit:
            seen.add(ebp)
            w = self.read(ebp, 8)
            if not w:
                break
            nxt, ret = struct.unpack("<II", w)
            if not self.module_at(ret):
                break
            frames.append(("frame", ret))
            if nxt <= ebp:
                break
            ebp = nxt
        sp = ctx["esp"]
        data = self.read(sp, 4096) or b""
        have = {a for _k, a in frames}
        for i in range(0, len(data) - 3, 4):
            v, = struct.unpack_from("<I", data, i)
            if v in have or not self.module_at(v):
                continue
            before = self.read(v - 5, 5)
            if before and (before[0] == 0xE8 or before[3:5] in (b"\xFF\xD0", b"\xFF\xD1", b"\xFF\xD2", b"\xFF\xD3") or before[1] == 0xFF):
                frames.append(("scan", v))
                have.add(v)
            if len(frames) >= limit:
                break
        return frames

    def report(self):
        L = ["dump: %s" % self.path, "written: %s" % (self.time.isoformat() if self.time else "?"),
             "os: %s %s %s" % (self.system.get("arch", "?"), self.system.get("os", "?"), self.system.get("service_pack", ""))]
        e = self.exception
        if not e:
            L.append("no exception stream (a manual dump?)")
        else:
            name = EXCEPTIONS.get(e["code"], "unknown")
            L.append("exception: 0x%08X %s at %s, thread %d" % (e["code"], name, self.where(e["address"]), e["thread"]))
            p = e["params"]
            if e["code"] == 0xC0000005 and len(p) >= 2:
                L.append("  access violation: %s address 0x%08X" % ({0: "reading", 1: "writing", 8: "executing (DEP)"}.get(p[0], "kind %d" % p[0]), p[1]))
            elif e["code"] == 0xC0000006 and len(p) >= 3:
                L.append("  in-page error: ntstatus 0x%08X" % p[2])
            ctx = e["context"]
            if ctx["regs"]:
                r = ctx["regs"]
                L.append("  regs: " + " ".join("%s=%08X" % (k, r[k]) for k in ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp", "esp", "eip")))
            code = self.read(ctx["eip"], 16)
            if code:
                L.append("  bytes at eip: " + code.hex(" "))
            sec = self.section_of(e["address"])
            if sec:
                L.append("  fault is in section %s, rva 0x%X" % sec)
            dis = self.disasm(e["address"])
            if dis:
                L.append("instructions around the fault (capstone):")
                L.extend("  " + l for l in dis)
            L.append("call stack (best effort):")
            for kind, a in self.stack():
                L.append("  %-5s %s" % (kind, self.where(a)))
        L.append("modules (%d):" % len(self.modules))
        for mod in sorted(self.modules, key=lambda m: m["base"]):
            L.append("  0x%08X %8d  %s %s" % (mod["base"], mod["size"], mod["name"].replace("\\", "/").rsplit("/", 1)[-1], mod["version"]))
        return "\n".join(L)
