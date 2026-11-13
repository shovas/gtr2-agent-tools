# uses only the standard library today (adding dependencies is fine: pin them in scripts/requirements.txt, see CLAUDE.md).
"""Read the car's telemetry from the rFactor shared-memory plugin (Plugins/rFactorSharedMemoryMap.dll), which this install loads.

The mapping "$rFactorShared$" (40960 bytes) starts with the rFactor 1 TelemInfoV2 fields (packing 4):
    0 float deltaTime, 4 long lap number, 8 float lap start time, 12 char[64] vehicle name, 76 char[64] track name,
    140 float[3] position, 152 float[3] local velocity (m/s, z negative forward), 164 float[3] local acceleration,
    176 float[9] orientation matrix (floats, not rFactor 1's doubles: found by watching which floats change while driving)
Offsets past the names are checked against the game by `python telemetry.py` (a live read) before anything relies on them.
Gear (int) at 240 and engine rpm (float) at 244 (found by pressing Alt once and watching what changed).
The four wheels' ground names are at 366, 433, 500 and 567 (67 bytes apart; "ROAD,CONC" in the pit lane).
Only reads; the plugin owns the memory.
"""
import ctypes
import math
import struct

k32 = ctypes.windll.kernel32
k32.OpenFileMappingW.restype = ctypes.c_void_p
k32.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
k32.MapViewOfFile.restype = ctypes.c_void_p
k32.MapViewOfFile.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t]
SIZE = 40960


class Telemetry:
    def __init__(self):
        self.view = None

    def open(self):
        handle = k32.OpenFileMappingW(4, False, "$rFactorShared$")
        if handle:
            self.view = k32.MapViewOfFile(handle, 4, 0, 0, 0)
        return bool(self.view)

    def raw(self):
        if self.view is None and not self.open():
            return None
        return ctypes.string_at(self.view, SIZE)

    def doubles(self, at, n):
        raw = self.raw()
        return list(struct.unpack_from("<%dd" % n, raw, at)) if raw else None

    def read(self):
        raw = self.raw()
        if raw is None:
            return None
        lap, = struct.unpack_from("<i", raw, 4)
        pos = struct.unpack_from("<3f", raw, 140)
        vel = struct.unpack_from("<3f", raw, 152)
        speed = (vel[0] ** 2 + vel[1] ** 2 + vel[2] ** 2) ** 0.5
        gear, = struct.unpack_from("<i", raw, 240)
        rpm, = struct.unpack_from("<f", raw, 244)
        o = struct.unpack_from("<9f", raw, 176)
        accel = struct.unpack_from("<3f", raw, 164)   # local acceleration m/s^2 (x lateral, y vertical, z longitudinal): spikes show impacts
        yaw = math.degrees(math.atan2(o[2], o[0]))     # heading; turning left makes it smaller
        surfaces = [raw[at:at + 16].split(b"\0")[0].decode("latin1") for at in (366, 433, 500, 567)]
        return {"lap": lap, "pos": pos, "vel": vel, "speed": speed, "yaw": yaw, "surfaces": surfaces, "gear": gear, "rpm": rpm, "accel": accel,
                "vehicle": raw[12:76].split(b"\0")[0].decode("latin1"), "track": raw[76:140].split(b"\0")[0].decode("latin1")}


if __name__ == "__main__":
    import time
    t = Telemetry()
    for _ in range(10):
        print(t.read())
        time.sleep(0.5)
