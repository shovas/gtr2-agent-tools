# Used by scripts/gtr2-file-watch.py.
"""Detect another process opening a file, using a read-handle (RH) oplock. Needs no admin rights.

An RH oplock is broken when another process opens the file to read or write it, so a break means something opened
the file's contents. Existence and attribute checks (`os.path.exists`, `os.stat`, opening for attributes only) do not
break it, so they are not detected.

Measured on this machine (see test_oplock.py): RH and RWH break on Python's open, Win32 CreateFile with several share
modes, the C runtime's fopen and GetPrivateProfileString. The weaker R and RW levels only break on writes, and miss most
reads, so they must not be used for this.

The holder must acknowledge a break straight away, or the other process's open is delayed. This acknowledges at once,
by closing its handle. The first break ends the watch. The file is only ever opened for attribute access plus the
oplock request, and its contents are never read.
"""
import ctypes
import threading
import time
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

FSCTL_REQUEST_OPLOCK = 0x00090240
OPLOCK_LEVEL_CACHE_READ, OPLOCK_LEVEL_CACHE_WRITE, OPLOCK_LEVEL_CACHE_HANDLE = 0x1, 0x2, 0x4
REQUEST_OPLOCK_INPUT_FLAG_REQUEST = 0x1
FILE_READ_ATTRIBUTES, FILE_SHARE_ALL, OPEN_EXISTING, FILE_FLAG_OVERLAPPED = 0x80, 0x7, 3, 0x40000000
ERROR_IO_PENDING, ERROR_OPLOCK_NOT_GRANTED = 997, 464
INFINITE, WAIT_OBJECT_0 = 0xFFFFFFFF, 0
INVALID_HANDLE = ctypes.c_void_p(-1).value


class _Overlapped(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t), ("Offset", wintypes.DWORD),
                ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]


class _RequestIn(ctypes.Structure):
    _fields_ = [("StructureVersion", wintypes.WORD), ("StructureLength", wintypes.WORD),
                ("RequestedOplockLevel", wintypes.DWORD), ("Flags", wintypes.DWORD)]


class _RequestOut(ctypes.Structure):
    _fields_ = [("StructureVersion", wintypes.WORD), ("StructureLength", wintypes.WORD),
                ("OriginalOplockLevel", wintypes.DWORD), ("NewOplockLevel", wintypes.DWORD),
                ("Flags", wintypes.DWORD), ("AccessMode", wintypes.DWORD), ("ShareMode", wintypes.WORD)]


kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                 wintypes.DWORD, wintypes.HANDLE]
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
                                     wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(_Overlapped)]
kernel32.DeviceIoControl.restype = wintypes.BOOL
kernel32.WaitForMultipleObjects.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE), wintypes.BOOL, wintypes.DWORD]
kernel32.WaitForMultipleObjects.restype = wintypes.DWORD
kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Overlapped)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.SetEvent.argtypes = [wintypes.HANDLE]


class Tripwire:
    """Watches one file. `broke_at` is the time of the first open by anything else, or None."""

    def __init__(self, path, level=OPLOCK_LEVEL_CACHE_READ | OPLOCK_LEVEL_CACHE_HANDLE, access=FILE_READ_ATTRIBUTES):
        self.path = str(path)
        self.level, self.access = level, access
        self.broke_at = None
        self.original_level = self.new_level = None
        self._file = None
        self._thread = None

    def arm(self):
        handle = kernel32.CreateFileW(self.path, self.access, FILE_SHARE_ALL, None, OPEN_EXISTING,
                                      FILE_FLAG_OVERLAPPED, None)
        if handle in (None, INVALID_HANDLE):
            raise ctypes.WinError(ctypes.get_last_error())
        self._file = handle
        self._done = kernel32.CreateEventW(None, True, False, None)
        self._stop = kernel32.CreateEventW(None, True, False, None)
        self._overlapped = _Overlapped()
        self._overlapped.hEvent = self._done
        self._in = _RequestIn(1, ctypes.sizeof(_RequestIn), self.level, REQUEST_OPLOCK_INPUT_FLAG_REQUEST)
        self._out = _RequestOut()
        ok = kernel32.DeviceIoControl(handle, FSCTL_REQUEST_OPLOCK, ctypes.byref(self._in), ctypes.sizeof(self._in),
                                      ctypes.byref(self._out), 24, None, ctypes.byref(self._overlapped))
        err = ctypes.get_last_error()
        if ok or err != ERROR_IO_PENDING:
            kernel32.CloseHandle(handle)
            self._file = None
            raise OSError(err, "the exclusive oplock was not granted"
                          + (" (another process already has the file open)" if err == ERROR_OPLOCK_NOT_GRANTED else ""))
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()
        return self

    def _watch(self):
        handles = (wintypes.HANDLE * 2)(self._done, self._stop)
        which = kernel32.WaitForMultipleObjects(2, handles, False, INFINITE)
        if which == WAIT_OBJECT_0:
            self.broke_at = time.time()
            self.original_level, self.new_level = self._out.OriginalOplockLevel, self._out.NewOplockLevel
        else:
            kernel32.CancelIoEx(self._file, ctypes.byref(self._overlapped))
        # Closing the handle acknowledges the break, so the other process's open isn't held up.
        kernel32.CloseHandle(self._file)
        self._file = None

    @property
    def broke(self):
        return self.broke_at is not None

    def disarm(self):
        """Stop watching and say whether anything opened the file."""
        if self._thread is not None:
            kernel32.SetEvent(self._stop)
            self._thread.join(timeout=10)
            self._thread = None
            kernel32.CloseHandle(self._done)
            kernel32.CloseHandle(self._stop)
        return self.broke
