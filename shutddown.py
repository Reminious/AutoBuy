import logging
import os
import signal
import threading
import time

import keyboard

from logutil import clog


_stats_ref = None
_email_sender_ref = None
_EXITING = False
_LOCK = threading.Lock()


def inject_refs(stats, email_sender):
    global _stats_ref, _email_sender_ref
    _stats_ref = stats
    _email_sender_ref = email_sender


def _cleanup_and_exit():
    global _EXITING
    with _LOCK:
        if _EXITING:
            return
        _EXITING = True
    try:
        keyboard.unhook_all()
    except Exception:
        pass

    try:
        if _stats_ref:
            _stats_ref.stop()
    except Exception:
        pass
    try:
        if _email_sender_ref:
            _email_sender_ref.shutdown(wait_seconds=5.0)
    except Exception:
        pass

    clog(logging.INFO, "CORE", ">>> Exiting now...")
    try:
        time.sleep(0.1)
    except Exception:
        pass
    os._exit(0)


def hard_kill():
    clog(logging.WARNING, "CORE", "F12 detected — stopping script immediately.")
    t = threading.Thread(target=_cleanup_and_exit, daemon=True, name="hard_kill")
    t.start()


def register_hotkeys_and_signals():
    keyboard.add_hotkey("f12", hard_kill, suppress=True)


    def _sig_handler(signum, frame):
        clog(logging.WARNING, "CORE", f"Signal {signum} received — stopping script.")
        _cleanup_and_exit()


    try:
        signal.signal(signal.SIGINT, _sig_handler)
    except Exception:
        pass
    try:
        signal.signal(signal.SIGTERM, _sig_handler)
    except Exception:
        pass
