"""Completion actions, imported only after the route has successfully finished."""
import ctypes
from ctypes import wintypes
import time
import psutil
import os
from leigod_pause import pause as pause_leigod

GAME_NAMES = {"elitedangerous64.exe", "elitedangerous.exe"}


def execute_completion(action, pause_enabled, control, dry_run=False, screen_off=False, test_real_pause=False):
    """Run completion actions, or the same decision path with all effects suppressed."""
    if action not in ('keep-open', 'close-apps', 'shutdown'):
        raise ValueError('Invalid completion action')
    control.check()
    if dry_run:
        print('TEST: route completed; would restore display brightness.', flush=True)
    if pause_enabled:
        control.check()
        try:
            paused = pause_leigod(control, dry_run=dry_run and not test_real_pause)
        except Exception as error:
            paused = False
            print('WARNING: LeiGod pause failed: %s' % error, flush=True)
        if not paused:
            print('WARNING: LeiGod pause unconfirmed; continuing completion action.', flush=True)
    else:
        print(('TEST: ' if dry_run else '') + 'LeiGod pause disabled.', flush=True)
    control.check()
    if action == 'close-apps':
        if dry_run:
            print('TEST: would close Elite Dangerous and CATS.', flush=True)
            if screen_off:
                print('TEST: would request display power-off after CATS exits.', flush=True)
        else:
            close_game(control)
            control.check()
            print('CATS_COMPLETION_CLOSE', flush=True)
    elif action == 'shutdown':
        if dry_run:
            print('TEST: would schedule shutdown in 30 seconds. No shutdown requested.', flush=True)
        else:
            print("Shutting down system in 30 seconds... (run 'shutdown /a' to cancel)", flush=True)
            control.sleep(5)
            with control.lock:
                control.check()
                if os.system('shutdown /s /t 30') != 0:
                    print('Failed to schedule shutdown.', flush=True)
                    return False
    else:
        print(('TEST: ' if dry_run else '') + 'Keep game and CATS open.', flush=True)
    return True


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
