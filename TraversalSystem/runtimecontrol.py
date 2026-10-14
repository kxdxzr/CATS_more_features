"""Cancellation shared by navigation, refuelling, waits and game-reopen timers."""
import os
import threading
import time as real_time


class Stopped(BaseException):
    pass


class RuntimeControl:
    def __init__(self):
        self.stopped = threading.Event()
        self.lock = threading.RLock()
        self.held_keys = set()
        self.keyboard = None
        self.save_progress = lambda: None

    def check(self):
        if self.stopped.is_set():
            raise Stopped()

    def sleep(self, seconds):
        if self.stopped.wait(max(0, seconds)):
            raise Stopped()

    def stop_and_exit(self):
        self.stopped.set()
        with self.lock:
            try:
                self.save_progress()
            except Exception as error:
                print("Could not save stopped route: %s" % error, flush=True)
            if self.keyboard is not None:
                for key in list(self.held_keys):
                    try:
                        self.keyboard.keyUp(key, _pause=False)
                    except Exception as error:
                        print("Could not release key %s: %s" % (key, error), flush=True)
            self.held_keys.clear()
            print("Traversal stopped by user. Completion actions cancelled.", flush=True)
            os._exit(3)

    def listen(self, stream):
        def reader():
            for line in stream:
                if line.strip().lower() == "stop":
                    self.stop_and_exit()
            # Losing the controlling GUI also cancels this traversal.
            self.stop_and_exit()
        threading.Thread(target=reader, daemon=True).start()


class ControlledInput:
    def __init__(self, module, control):
        self.module = module
        self.control = control

    def __getattr__(self, name):
        target = getattr(self.module, name)
        if not callable(target):
            return target
        def guarded(*args, **kwargs):
            with self.control.lock:
                self.control.check()
                if name == "keyDown":
                    self.control.held_keys.add(args[0])
                result = target(*args, **kwargs)
                if name == "keyUp":
                    self.control.held_keys.discard(args[0])
                return result
        return guarded


class Clock:
    def __init__(self, control):
        self.sleep = control.sleep

    def __getattr__(self, name):
        return getattr(real_time, name)


control = RuntimeControl()
clock = Clock(control)
