# C4-01 Home Sharing in the window: this library offered to the network, another one found,
# browsed, played from, and left alone — a shared library can't be changed from here.
import os
import sys

sys.path.insert(0, os.environ["FOLIO_TESTS"])
from uicommon import answer, check, music, pump, run, shot, wait  # noqa: E402
from gi.repository import Gtk  # noqa: E402
from folio_chord import dialogs, library as L, sharing  # noqa: E402
import mkaudio  # noqa: E402


def all_rows(store):
    """Every row of the sources tree, children included: [(label, kind, id)]."""
    out = []

    def walk(model, path, it):
        r = model[it]
        out.append((r[1], r[2], r[3]))
        return False
    store.foreach(walk)
    return out


def main():
    w = win  # noqa: F821
    a = app  # noqa: F821
    lib, pb = a.lib, a.playback
    d, songs = music(w, secs=3.0)
    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"), "chord_shared_%d" % os.getpid())
    os.makedirs(tmp, exist_ok=True)

    # ---- a second library on this computer, standing in for the Chord on the other one
    other_dir = os.path.join(tmp, "other")
    mkaudio.make(other_dir, 2.0)
    other = L.Library(os.path.join(tmp, "other.db"))
    other.add_folder(other_dir)
    other.scan()
    theirs = other.tracks()
    pid = other.new_playlist("Their Mix", tracks=[r["id"] for r in theirs[:2]])
    srv = sharing.Share(other, name="Upstairs", port=0, host="127.0.0.1")
    port = srv.start()

    # ---- sharing this library
    on = dialogs.RESPONSE.get("Home Sharing")

    def say_yes(dlg):
        dlg.get_content_area()
        for c in dlg.body.get_children():
            if isinstance(c, Gtk.CheckButton):
                c.set_active(True)
        return Gtk.ResponseType.OK
    answer("Home Sharing", say_yes)
    w.run("share-settings")
    pump(0.3)
    check(w.settings.get("share") and w.share_server is not None, "Share My Library turns sharing on")
    mine = sharing.Remote("127.0.0.1", w.share_server.port)
    check(mine.info()["songs"] == len(lib.tracks()), "and another Chord sees this library's songs", mine.info())
    del on

    # ---- finding the other library and browsing it
    found = w.find_shares(timeout=1.0, port=port, addresses=["127.0.0.1"])
    check(any(f["name"] == "Upstairs" for f in found), "the other library is found on the network", found)
    i = [k for k, f in enumerate(w.shares) if f["name"] == "Upstairs"][0]
    rows = [(a, b) for a, b, _c in all_rows(w.src_store)]
    check(("SHARED", "header") in rows and ("Upstairs", "shared") in rows, "it appears under SHARED", rows)
    w.select_source("shared", i)
    pump(0.4)
    check(len(w.rows) == len(theirs) and {r["title"] for r in w.rows} == {r["title"] for r in theirs},
          "its songs show in the list", len(w.rows))
    check(all(r["path"].startswith("http://127.0.0.1:%d/" % port) for r in w.rows),
          "each song plays from the other computer", w.rows[0]["path"])
    check("song" in w.status.get_text(), "the status line counts them", w.status.get_text())
    shot(w, "shared_library")
    pls = all_rows(w.src_store)
    check(("Their Mix", "sharedpl") in [(a, b) for a, b, _c in pls], "its playlists are under it too", pls)
    key = [c for _a, b, c in pls if b == "sharedpl"][0]
    w.select_source("sharedpl", key)
    pump(0.4)
    check(len(w.rows) == 2, "a shared playlist shows the songs in it", len(w.rows))

    # ---- searching, and playing from it
    w.select_source("shared", i)
    pump(0.3)
    w.search.set_text(theirs[0]["title"].split()[0])
    pump(0.3)
    check(w.rows and all(theirs[0]["title"].split()[0].lower() in (r["title"] or "").lower() for r in w.rows),
          "search works on a shared library", [r["title"] for r in w.rows])
    w.search.set_text("")
    pump(0.3)
    w.play_from_list(0)
    check(wait(lambda: pb.now and (pb.now.get("uri") or "").startswith("http://"), 8),
          "a song plays, streamed from the other computer", pb.now)
    check(pb.now.get("shared") is True and wait(lambda: pb.engine.state == "playing", 8),
          "and it really is playing", (pb.now.get("shared"), pb.engine.state))
    before = {r["id"]: r["play_count"] for r in lib.tracks()}
    pb.next()
    check(wait(lambda: pb.now and (pb.now.get("uri") or "").startswith("http://"), 8),
          "Next plays the next shared song", pb.now and pb.now.get("title"))
    check({r["id"]: r["play_count"] for r in lib.tracks()} == before,
          "playing from a shared library leaves this library's play counts alone")
    pb.stop()

    # ---- what can't be done to someone else's library
    w.last = None
    msgs = []
    real = w.info
    w.info = lambda text, title=None: msgs.append(text)
    tried = []
    for cmd in ("delete", "rate:100", "get-info", "remove-duplicates", "organize", "add-folder"):
        n = len(msgs)
        w.run(cmd)
        tried.append((cmd, w.source[0], len(msgs) - n))
    w.info = real
    check(len(msgs) == 6 and all("not changed" in m for m in msgs),
          "nothing that would change it is offered", (tried, msgs[:1]))
    check(len(other.tracks()) == len(theirs) and all(os.path.exists(r["path"]) for r in theirs),
          "and the other library still has all its songs")

    # ---- it goes away when the other Chord stops sharing
    srv.stop()
    w.select_source("music")
    pump(0.2)
    w.find_shares(timeout=0.5, port=port, addresses=["127.0.0.1"])
    check(not any(f.get("name") == "Upstairs" for f in w.shares), "a library that stops sharing leaves the list", w.shares)
    answer("Home Sharing", lambda dlg: Gtk.ResponseType.CANCEL)
    w.run("share-settings")
    check(w.settings.get("share") and w.share_server is not None, "cancelling the dialog changes nothing")

    def say_no(dlg):
        for c in dlg.body.get_children():
            if isinstance(c, Gtk.CheckButton):
                c.set_active(False)
        return Gtk.ResponseType.OK
    answer("Home Sharing", say_no)
    w.run("share-settings")
    pump(0.2)
    check(not w.settings.get("share") and w.share_server is None, "and turning sharing off stops it")
    dialogs.RESPONSE.pop("Home Sharing", None)


run(main)
