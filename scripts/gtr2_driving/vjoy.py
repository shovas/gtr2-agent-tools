"""Minimal vJoy wrapper (ctypes; standard library only today, adding dependencies is fine: pin them in scripts/requirements.txt, see CLAUDE.md): drive a virtual joystick's axes.

Purpose: let the driving scripts send analog steering/throttle/brake instead of
keyboard pulses. Needs the vJoy driver (kernel, installed once with admin) and
its interface DLL; using it afterwards needs no admin.

Usage:  from gtr2_driving.vjoy import VJoy
        with VJoy(1) as j: j.axis('X', 0.5)   # 0.0 .. 1.0 (0.5 = centre)
Example: python -I scripts/gtr2_driving/vjoy.py sweep X   (test sweep)
"""
import ctypes, os, sys, time

DLL = r"C:\Program Files\vJoy\%s\vJoyInterface.dll" % ("x64" if sys.maxsize > 2**32 else "x86")
AXES = {"X": 0x30, "Y": 0x31, "Z": 0x32, "RX": 0x33, "RY": 0x34, "RZ": 0x35, "SL0": 0x36, "SL1": 0x37}
MAXV = 32767


class VJoy:
    def __init__(self, dev=1):
        if not os.path.exists(DLL):
            raise RuntimeError("vJoy interface DLL not found: " + DLL)
        self.d = ctypes.WinDLL(DLL)
        self.dev = dev
        self.d.SetAxis.argtypes = [ctypes.c_long, ctypes.c_uint, ctypes.c_uint]
        self.d.SetBtn.argtypes = [ctypes.c_int, ctypes.c_uint, ctypes.c_ubyte]
        self.d.GetVJDStatus.argtypes = [ctypes.c_uint]
        self.d.AcquireVJD.argtypes = [ctypes.c_uint]
        self.d.RelinquishVJD.argtypes = [ctypes.c_uint]
        self.d.ResetVJD.argtypes = [ctypes.c_uint]

    def __enter__(self):
        if not self.d.vJoyEnabled():
            raise RuntimeError("vJoy driver not enabled")
        st = self.d.GetVJDStatus(self.dev)
        if st not in (0, 1):  # 0 owned, 1 free
            raise RuntimeError("vJoy device %d not available (status %d)" % (self.dev, st))
        if not self.d.AcquireVJD(self.dev):
            raise RuntimeError("could not acquire vJoy device %d" % self.dev)
        self.d.ResetVJD(self.dev)
        for a in AXES:  # reset leaves sliders at 0; centre all so the game sees no phantom input
            self.axis(a, 0.5)
        return self

    def __exit__(self, *a):
        for a in AXES:
            self.axis(a, 0.5)
        self.d.RelinquishVJD(self.dev)

    def axis(self, name, frac):
        """Set an axis from 0.0 to 1.0."""
        frac = min(1.0, max(0.0, frac))
        if not self.d.SetAxis(int(frac * MAXV), self.dev, AXES[name.upper()]):
            raise RuntimeError("SetAxis failed for " + name)

    def button(self, n, down):
        self.d.SetBtn(1 if down else 0, self.dev, n)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "sweep":
        with VJoy(1) as j:
            for v in [0.5, 0.0, 0.5, 1.0, 0.5]:
                j.axis(sys.argv[2], v); print(sys.argv[2], v); time.sleep(1.0)
