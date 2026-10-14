"""Completion actions, imported only after the route has successfully finished."""
import ctypes
from ctypes import wintypes
import time
import psutil

GAME_NAMES = {"elitedangerous64.exe", "elitedangerous.exe"}


def close_game(control):
    games = [p for p in psutil.process_iter(['name'])
             if (p.info['name'] or '').casefold() in GAME_NAMES]
    print("Closing Elite Dangerous after route completion...", flush=True)
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p, ctypes.c_ssize_t)
    pids = {p.pid for p in games}

    @callback_type
    def close_window(hwnd, parameter):
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        if pid.value in pids:
            with control.lock:
                if control.stopped.is_set():
                    return False
                user32.PostMessageW(ctypes.c_void_p(hwnd), 0x0010, 0, 0)  # WM_CLOSE
        return True

    control.check()
    user32.EnumWindows(close_window, 0)
    deadline = time.monotonic() + 15
    while any(p.is_running() for p in games) and time.monotonic() < deadline:
        control.sleep(0.25)
    for process in games:
        if process.is_running():
            try:
                with control.lock:
                    control.check()
                    process.terminate()
                process.wait(timeout=5)
            except psutil.NoSuchProcess:
                pass  # normal exit raced with the last is_running check
            except psutil.TimeoutExpired:
                raise RuntimeError("Game did not exit; keeping CATS open to report the error")
    print("Elite Dangerous closed.", flush=True)
