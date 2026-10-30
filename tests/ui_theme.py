# X2-01 for Folio Chord: started under a dark desktop theme (app dark, and app set to light) or the
# loud FolioTestColour theme, every view, the small windows and the dialogs keep Chord's own colours.
import os
import sys
import time

sys.path.insert(0, os.environ["FOLIO_TESTS"])
import themecheck  # noqa: E402
from uicommon import FAILS, OUT, check, finish, music, pump, wait  # noqa: E402
from gi.repository import Gtk  # noqa: E402
from folio_chord import dialogs  # noqa: E402

LOOKED = []


def look(w, where):
    pump(0.3)
    probs = themecheck.audit(w, where)
    if probs:
        pump(1.5)
        probs = themecheck.audit(w, where)
    for p in probs:
        print("FAIL " + p)
    if probs or os.environ.get("THEME_SHOTS"):
        themecheck.save(w, os.path.join(OUT, "theme_%s%s_%s.png" % (themecheck.mode(), os.environ.get("FOLIO_THEME", ""),
                                                                    where.replace(" ", "_"))))
    FAILS.extend(probs)
    LOOKED.append(where)
    if not probs:
        print("ok   %s (%s)" % (where, themecheck.mode()))


try:
    w = win  # noqa: F821
    print("theme", os.environ.get("GTK_THEME"), "mode", themecheck.mode(), "app", os.environ.get("FOLIO_THEME", "desktop"))
    seen = set()

    def dlg(d):
        t = d.get_title() or type(d).__name__
        if t not in seen:
            seen.add(t)
            d.show_all()
            pump(0.3)
            look(d, "dialog " + t)
        return Gtk.ResponseType.CANCEL
    for t in ("Get Info", "Multiple Item Information", "Smart Playlist", "View Options", "Options", "Burn Settings",
              "Keyboard Shortcuts", "About Folio Chord", "Subscribe to Podcast", "Podcast Settings", "Open Stream", "Confirm"):
        dialogs.RESPONSE[t] = dlg
    dialogs.RESPONSE["Folio Chord"] = dlg
    d, songs = music(w)
    w.songs.select_ids([w.rows[0]["id"]])
    w.songs.emit("play", 0)
    wait(lambda: app.playback.engine.state == "playing", 4)  # noqa: F821
    look(w, "library list")
    w.run("view:albums")
    look(w, "album list")
    w.run("view:grid")
    look(w, "grid")
    w.run("view:list")
    w.songs.select_ids([w.rows[0]["id"]])
    for c in ("get-info", "new-smart", "view-options", "options", "shortcuts", "about", "open-stream", "subscribe"):
        w.run(c)
    w.songs.select_ids([r["id"] for r in w.rows[:2]])
    w.run("get-info")
    pid = app.lib.new_playlist("Mix", tracks=[r["id"] for r in w.rows[:3]])  # noqa: F821
    w.fill_sources()
    w.select_source("playlist", pid)
    look(w, "playlist")
    os.environ.setdefault("FOLIO_CHORD_WODIM", "/bin/true")
    w.run("burn")
    w.select_source("podcasts")
    look(w, "podcasts (none yet)")
    w.podview.btn["directory"].set_active(True)
    pump(0.3)
    look(w, "podcast directory")
    w.podview.btn["directory"].set_active(False)
    w.select_source("radio")
    look(w, "radio")
    w.select_source("music")
    eq = w.run("equalizer")
    look(eq, "equalizer")
    eq.hide()
    mini = w.run("mini-player")
    look(mini, "mini player")
    w.run("front")
    items = w.run("up-next")
    pump(0.3)
    look(w.up_next_popover, "up next")
    w.up_next_popover.popdown()
    w.run("stop")
    check(len(LOOKED) >= 18, "looked at every view, small window and dialog", LOOKED)
except Exception:
    import traceback
    traceback.print_exc()
    FAILS.append("exception")
print("%d checks" % len(LOOKED))
finish()
