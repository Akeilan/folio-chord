"""Shared helpers for the UI tests, run inside Folio Chord (FOLIO_TEST_SCRIPT):
check, pump, wait, answer dialogs, and test music."""
import os
import sys
import time
import traceback

from gi.repository import Gtk

HERE = os.environ.get("FOLIO_TESTS") or os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.environ.get("UI_OUT", "/tmp/ui_out")
os.makedirs(OUT, exist_ok=True)
FAILS = []
N = [0]
try:        # messages are answered at once in the tests (each is still recorded as win.last_message)
    from folio_chord import dialogs as _d
    _d.RESPONSE.setdefault("Folio Chord", 1)
except Exception:
    pass


def check(ok, what, info=None):
    N[0] += 1
    print(("ok   " if ok else "FAIL ") + what + ("" if ok or info is None else "  -- %r" % (info,)))
    sys.stdout.flush()
    if not ok:
        FAILS.append(what)
    return ok


def pump(t=0.2):
    end = time.time() + t
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.004)


def wait(cond, secs=10):
    end = time.time() + secs
    while time.time() < end:
        pump(0.05)
        try:
            if cond():
                return True
        except Exception:
            pass
    try:
        return bool(cond())
    except Exception:
        return False


def answer(title, fn):
    """Answer the dialog with this title: fn(dialog) -> response (or a response)."""
    from folio_chord import dialogs
    dialogs.RESPONSE[title] = fn


def music(win, secs=2.0):
    """The test songs in a music folder added to the library; returns {title: path}."""
    import mkaudio
    d = os.path.join(os.environ.get("TMPDIR", "/tmp"), "chord_ui_music_%d" % os.getpid())
    songs = mkaudio.make(d, secs)
    win.add_paths([d])
    win.select_source("music")
    win.load_songs()
    pump(0.3)
    return d, songs


def finish():
    print("%d checks, %d failed" % (N[0], len(FAILS)))
    print("UI all passed" if not FAILS else "UI FAILS: " + "; ".join(FAILS))
    sys.stdout.flush()
    os._exit(1 if FAILS else 0)


def run(fn):
    try:
        fn()
    except Exception:
        traceback.print_exc()
        FAILS.append("exception")
    finish()


def shot(win, name):
    try:
        import themecheck
        themecheck.save(win, os.path.join(OUT, "%s.png" % name))
    except Exception:
        pass
