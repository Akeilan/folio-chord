# Every menu command, one after another, with dialogs cancelled: none may fail, and only the Store
# (and device sync) may say it isn't available. Writes WALK_OUT (a TSV of command, result).
import os
import sys

sys.path.insert(0, os.environ["FOLIO_TESTS"])
from uicommon import check, finish, music, pump  # noqa: E402
from gi.repository import Gtk  # noqa: E402
from folio_chord import dialogs  # noqa: E402

w = win  # noqa: F821
messages = []
orig_message = dialogs.message


def record(win_, text, title=None):
    messages.append(text)
    return text


dialogs.message = record
for t in ("Get Info", "Multiple Item Information", "Smart Playlist", "View Options", "Options", "Burn Settings",
          "Keyboard Shortcuts", "About Folio Chord", "Subscribe to Podcast", "Podcast Settings", "Open Stream", "Confirm",
          "Choose", "Equalizer"):
    dialogs.RESPONSE[t] = Gtk.ResponseType.CANCEL
for name in ("choose_files", "choose_folder", "save_file"):
    setattr(dialogs, name, (lambda *a, **k: [] if name == "choose_files" else None))
dialogs.choose_files = lambda *a, **k: []
dialogs.choose_folder = lambda *a, **k: None
dialogs.save_file = lambda *a, **k: None
w.close = lambda: None
app.quit = lambda: None  # noqa: F821
d, songs = music(w)
rows = []
errors = []
na = []
NOT_HERE_OK = ("na:",)
for label, cmd in list(w.commands):
    if cmd in ("quit", "close", "minimize"):
        rows.append((label, cmd, "skipped (closes the window)"))
        continue
    w.select_source("music")
    w.set_view("list")
    w.load_songs()
    if w.rows:
        w.songs.select_ids([w.rows[0]["id"]])
    messages.clear()
    n_missing = len(w.missing_log)
    import traceback
    try:
        w.run(cmd)
        pump(0.15)
    except Exception:
        traceback.print_exc()
        errors.append(cmd)
    said = " | ".join(messages)
    if "Something went wrong" in said:
        errors.append(cmd)
    if "isn't available" in said or len(w.missing_log) > n_missing:
        na.append(cmd)
    rows.append((label, cmd, said or "ok"))
    for win_ in Gtk.Window.list_toplevels():
        if win_ is not w and win_.get_visible() and isinstance(win_, Gtk.Window) and win_.get_title() not in (None, ""):
            if win_.get_window_type() == Gtk.WindowType.TOPLEVEL and not isinstance(win_, Gtk.Dialog):
                win_.hide()
    if not w.get_visible():
        w.run("front")
    if w.is_fullscreen():
        w.unfullscreen()
    w.app.playback.stop()
out = os.environ.get("WALK_OUT")
if out:
    with open(out, "w") as f:
        for r in rows:
            f.write("\t".join(r).replace("\n", " ") + "\n")
check(not errors, "every command runs without an error", errors)
check(all(c.startswith(NOT_HERE_OK) for c in na), "only the Store and device sync say they aren't available", na)
check(len([c for c in na if c.startswith("na:")]) == 7, "the Store's commands and device sync each say so", na)
print("WALK OK" if not errors else "WALK ERRORS", len(rows), "commands")
print("not available yet:", len([c for c in na if not c.startswith(NOT_HERE_OK)]))
finish()
