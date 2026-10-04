"""A command run as if from a real terminal, for the few tools whose sign-in refuses to start without one.

The Atlas CLI's `atlas auth login` begins with an interactive menu ("Select authentication type"), and without a
terminal it exits on the spot ("Incorrect function"): a plain pipe is not enough, on any platform. So this gives the
command a pseudo-terminal (ConPTY on Windows, `pty` elsewhere) and presents it the way the sign-ins in `cli_signin.py`
already expect a process to look: `.stdout` yields its lines (with the terminal's colour and cursor codes removed),
`.poll()` / `.returncode` say whether it has finished, and `.send()` types an answer to a prompt.
"""
from __future__ import annotations

import codecs
import os
import queue
import re
import subprocess
import threading
from typing import Callable, Iterator

# Colour, cursor movement and title codes a terminal program prints; they are for a screen, not for reading.
_ESCAPES = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][A-Za-z0-9]|\x1b[=>MN78]")
# A terminal moves to the next line with a cursor code rather than a newline; keep those as line breaks, or the
# end of one sentence runs into the start of the next.
_MOVES_DOWN = re.compile(r"\x1b\[[0-9;]*[BEHfJ]")
_MOVES_RIGHT = re.compile(r"\x1b\[[0-9;]*C")
_LINE_END = re.compile(r"\r\n|\r|\n")
# Wide, so a long link is not broken across two lines by the terminal.
COLUMNS, ROWS = 250, 50


class PtyProcess:
    """A running command and its terminal. Build one with `spawn()`."""

    def __init__(self, pid: int, poll: Callable[[], int | None], write: Callable[[bytes], None],
                 kill: Callable[[], None]) -> None:
        self.pid = pid
        self._poll, self._write, self._kill = poll, write, kill
        self._lines: queue.Queue[str | None] = queue.Queue()
        self.stdout: Iterator[str] = iter(self._lines.get, None)

    @property
    def returncode(self) -> int | None:
        return self._poll()

    def poll(self) -> int | None:
        return self._poll()

    def send(self, text: str) -> None:
        """Type `text` into the terminal ("\\r" is the Enter key)."""
        try:
            self._write(text.encode("utf-8"))
        except OSError:
            pass  # it has already finished

    def kill(self) -> None:
        try:
            self._kill()
        except OSError:
            pass

    # Called by the reader thread with raw terminal output; the end of the output is None.
    def _feed(self, pending: str, text: str | None) -> str:
        if text is None:
            if pending.strip():
                self._lines.put(pending.strip())
            self._lines.put(None)
            return ""
        pending += _ESCAPES.sub("", _MOVES_RIGHT.sub(" ", _MOVES_DOWN.sub("\n", text)))
        *done, pending = _LINE_END.split(pending)
        for line in done:
            if line.strip():
                self._lines.put(line.strip())
        return pending


def _reader(process: PtyProcess, read: Callable[[], bytes]) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    pending = ""
    while True:
        try:
            chunk = read()
        except OSError:
            chunk = b""
        if not chunk:
            break
        pending = process._feed(pending, decoder.decode(chunk))
    process._feed(pending, None)


def spawn(command: list[str], env: dict[str, str] | None = None) -> PtyProcess:
    """Start `command` in a pseudo-terminal."""
    env = {**os.environ, **(env or {})}
    return _spawn_windows(command, env) if os.name == "nt" else _spawn_posix(command, env)


# --- Unix ----------------------------------------------------------------------------------------

def _spawn_posix(command: list[str], env: dict[str, str]) -> PtyProcess:
    import fcntl
    import pty
    import struct
    import termios

    master, slave = pty.openpty()
    try:
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLUMNS, 0, 0))
        child = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, env=env,
                                 start_new_session=True, close_fds=True)
    finally:
        os.close(slave)
    process = PtyProcess(child.pid, child.poll, lambda data: os.write(master, data), child.kill)
    threading.Thread(target=_reader, args=(process, lambda: os.read(master, 4096)), daemon=True).start()
    return process


# --- Windows (ConPTY) ----------------------------------------------------------------------------

def _spawn_windows(command: list[str], env: dict[str, str]) -> PtyProcess:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    HANDLE, DWORD, BOOL = wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL
    EXTENDED_STARTUPINFO_PRESENT, CREATE_UNICODE_ENVIRONMENT = 0x00080000, 0x00000400
    PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
    INFINITE = 0xFFFFFFFF

    class COORD(ctypes.Structure):
        _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [("cb", DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                    ("lpTitle", wintypes.LPWSTR), ("dwX", DWORD), ("dwY", DWORD), ("dwXSize", DWORD),
                    ("dwYSize", DWORD), ("dwXCountChars", DWORD), ("dwYCountChars", DWORD),
                    ("dwFillAttribute", DWORD), ("dwFlags", DWORD), ("wShowWindow", wintypes.WORD),
                    ("cbReserved2", wintypes.WORD), ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
                    ("hStdInput", HANDLE), ("hStdOutput", HANDLE), ("hStdError", HANDLE)]

    class STARTUPINFOEXW(ctypes.Structure):
        _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [("hProcess", HANDLE), ("hThread", HANDLE), ("dwProcessId", DWORD), ("dwThreadId", DWORD)]

    kernel32.CreatePipe.argtypes = [ctypes.POINTER(HANDLE), ctypes.POINTER(HANDLE), ctypes.c_void_p, DWORD]
    kernel32.CreatePipe.restype = BOOL
    kernel32.CreatePseudoConsole.argtypes = [COORD, HANDLE, HANDLE, DWORD, ctypes.POINTER(ctypes.c_void_p)]
    kernel32.CreatePseudoConsole.restype = ctypes.c_long
    kernel32.ClosePseudoConsole.argtypes = [ctypes.c_void_p]
    kernel32.ClosePseudoConsole.restype = None
    kernel32.InitializeProcThreadAttributeList.argtypes = [ctypes.c_void_p, DWORD, DWORD, ctypes.POINTER(ctypes.c_size_t)]
    kernel32.InitializeProcThreadAttributeList.restype = BOOL
    kernel32.UpdateProcThreadAttribute.argtypes = [ctypes.c_void_p, DWORD, ctypes.c_size_t, ctypes.c_void_p,
                                                   ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    kernel32.UpdateProcThreadAttribute.restype = BOOL
    kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    kernel32.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, BOOL,
                                        DWORD, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFOEXW),
                                        ctypes.POINTER(PROCESS_INFORMATION)]
    kernel32.CreateProcessW.restype = BOOL
    kernel32.ReadFile.argtypes = [HANDLE, ctypes.c_void_p, DWORD, ctypes.POINTER(DWORD), ctypes.c_void_p]
    kernel32.ReadFile.restype = BOOL
    kernel32.WriteFile.argtypes = [HANDLE, ctypes.c_char_p, DWORD, ctypes.POINTER(DWORD), ctypes.c_void_p]
    kernel32.WriteFile.restype = BOOL
    kernel32.CloseHandle.argtypes = [HANDLE]
    kernel32.CloseHandle.restype = BOOL
    kernel32.WaitForSingleObject.argtypes = [HANDLE, DWORD]
    kernel32.WaitForSingleObject.restype = DWORD
    kernel32.GetExitCodeProcess.argtypes = [HANDLE, ctypes.POINTER(DWORD)]
    kernel32.GetExitCodeProcess.restype = BOOL
    kernel32.TerminateProcess.argtypes = [HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = BOOL

    def fail(what: str) -> OSError:
        return OSError(f"{what} failed (Windows error {ctypes.get_last_error()})")

    in_read, in_write, out_read, out_write = HANDLE(), HANDLE(), HANDLE(), HANDLE()
    if not kernel32.CreatePipe(ctypes.byref(in_read), ctypes.byref(in_write), None, 0) \
            or not kernel32.CreatePipe(ctypes.byref(out_read), ctypes.byref(out_write), None, 0):
        raise fail("CreatePipe")
    console = ctypes.c_void_p()
    made = kernel32.CreatePseudoConsole(COORD(COLUMNS, ROWS), in_read, out_write, 0, ctypes.byref(console))
    # The terminal now owns its ends of the pipes.
    kernel32.CloseHandle(in_read)
    kernel32.CloseHandle(out_write)
    if made != 0:
        kernel32.CloseHandle(in_write)
        kernel32.CloseHandle(out_read)
        raise OSError(f"A terminal could not be created for the sign-in (HRESULT {made & 0xFFFFFFFF:#x}).")

    size = ctypes.c_size_t()
    kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    attributes = ctypes.create_string_buffer(size.value)
    if not kernel32.InitializeProcThreadAttributeList(attributes, 1, 0, ctypes.byref(size)) \
            or not kernel32.UpdateProcThreadAttribute(attributes, 0, PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE, console,
                                                      ctypes.sizeof(ctypes.c_void_p), None, None):
        kernel32.ClosePseudoConsole(console)
        raise fail("Setting up the terminal")

    startup = STARTUPINFOEXW()
    startup.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
    # Without this the child inherits this process's own (here redirected) standard handles and never sees the
    # terminal; with it, and no handles given, it takes them from the terminal.
    startup.StartupInfo.dwFlags = 0x00000100  # STARTF_USESTDHANDLES
    startup.lpAttributeList = ctypes.cast(attributes, ctypes.c_void_p)
    block = ctypes.create_unicode_buffer("".join(f"{k}={v}\0" for k, v in env.items()) + "\0")
    line = ctypes.create_unicode_buffer(subprocess.list2cmdline(command))
    info = PROCESS_INFORMATION()
    started = kernel32.CreateProcessW(None, line, None, None, False,
                                      EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,
                                      ctypes.cast(block, ctypes.c_void_p), None, ctypes.byref(startup), ctypes.byref(info))
    error = ctypes.get_last_error()
    kernel32.DeleteProcThreadAttributeList(attributes)
    if not started:
        kernel32.ClosePseudoConsole(console)
        kernel32.CloseHandle(in_write)
        kernel32.CloseHandle(out_read)
        raise OSError(f"{command[0]} could not be started (Windows error {error})")
    kernel32.CloseHandle(info.hThread)

    finished = threading.Event()
    result: dict[str, int] = {}

    def poll() -> int | None:
        return result.get("code") if finished.is_set() else None

    def write(data: bytes) -> None:
        count = DWORD()
        if finished.is_set() or not kernel32.WriteFile(in_write, data, len(data), ctypes.byref(count), None):
            raise OSError("The terminal is closed.")

    def kill() -> None:
        if not finished.is_set():
            kernel32.TerminateProcess(info.hProcess, 1)

    def read() -> bytes:
        buffer = ctypes.create_string_buffer(4096)
        count = DWORD()
        if not kernel32.ReadFile(out_read, buffer, 4096, ctypes.byref(count), None):
            kernel32.CloseHandle(out_read)  # the terminal has closed: this was the last read
            return b""
        return buffer.raw[:count.value]

    process = PtyProcess(int(info.dwProcessId), poll, write, kill)

    def wait() -> None:
        kernel32.WaitForSingleObject(info.hProcess, INFINITE)
        code = DWORD()
        kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
        result["code"] = int(code.value)
        finished.set()
        # Closing the terminal is what ends the reader's pipe, once the last output has been read.
        kernel32.ClosePseudoConsole(console)
        kernel32.CloseHandle(info.hProcess)
        kernel32.CloseHandle(in_write)

    threading.Thread(target=_reader, args=(process, read), daemon=True).start()
    threading.Thread(target=wait, daemon=True).start()
    return process
