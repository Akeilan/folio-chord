# Backlog 8 in the window (C8-39): what Chord's own checks never caught before — with the pointer
# and keyboard where it matters (menus, renaming, dragging, files from the file manager).
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.environ["FOLIO_TESTS"])
from uicommon import answer, check, music, pump, run, wait  # noqa: E402
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402
from folio_chord import dialogs, library as L, radio as R, sharing, theme, views  # noqa: E402
import mkaudio  # noqa: E402
import netstub  # noqa: E402

XDO = shutil.which("xdotool") and os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")


def xdo(*args):
    subprocess.run(["xdotool"] + [str(a) for a in args], check=False)
    pump(0.25)


def screen_xy(widget, x, y):
    """Where a point of a widget is on the screen."""
    win = widget.get_window()
    ox, oy = win.get_origin()[1:]
    a = widget.get_allocation()
    if widget.get_has_window():
        return ox + x, oy + y
    return ox + a.x + x, oy + a.y + y


def row_xy(view, path, col=None):
    r = view.get_background_area(path, col or view.get_column(1))
    bx, by = view.convert_bin_window_to_widget_coords(r.x + r.width // 2, r.y + r.height // 2)
    wx, wy = view.translate_coordinates(view.get_toplevel(), bx, by)
    ox, oy = view.get_toplevel().get_window().get_origin()[1:]
    return ox + wx, oy + wy


def main():
    w = win  # noqa: F821
    a = app  # noqa: F821
    lib, pb, eng = a.lib, a.playback, a.playback.engine
    d, songs = music(w, secs=3.0)
    T = {r["title"]: r["id"] for r in lib.tracks()}
    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"), "chord_b8_%d" % os.getpid())
    os.makedirs(tmp, exist_ok=True)

    # ---- C8-38 the menus can be read: an item of an open menu is dark on light, the bar's own label light
    w.resize(1300, 860)
    pump(0.3)
    bar = w.menubar if hasattr(w, "menubar") else None
    if bar is None:
        bar = [c for c in w.get_children()[0].get_children() if isinstance(c, Gtk.MenuBar)][0]
    top = [m for m in bar.get_children() if (m.get_label() or "").replace("_", "") == "View"][0]
    top.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    sub = top.get_submenu()
    sub.show_all()
    item = [m for m in sub.get_children() if type(m) is Gtk.MenuItem and m.get_label()][0]
    lab = item.get_child()
    col = lab.get_style_context().get_color(lab.get_state_flags())
    toplab = top.get_child().get_style_context().get_color(Gtk.StateFlags.PRELIGHT)
    c = theme.colours(w.dark)
    want = Gdk.RGBA()
    want.parse(c["menu_fg"])
    check(abs(col.red - want.red) < 0.05 and abs(col.green - want.green) < 0.05,
          "C8-38: items of a menu opened from the bar are in the menu's own dark text", (col.to_string(), c["menu_fg"]))
    check(toplab.red > 0.9 and toplab.green > 0.9, "C8-38: the bar's own label is light on the highlight", toplab.to_string())
    top.unset_state_flags(Gtk.StateFlags.PRELIGHT)
    if XDO:
        tx, ty = screen_xy(top, top.get_allocation().width // 2, top.get_allocation().height // 2)
        xdo("mousemove", tx, ty)
        xdo("click", 1)
        pump(0.4)
        check(sub.get_visible(), "C8-38: the View menu opens with the pointer")
        xdo("key", "Escape")

    # ---- C8-03 Delete in a playlist narrowed by a search removes the song selected
    ids = [T[t] for t in sorted(T)]
    pid = lib.new_playlist("Mix", tracks=ids)
    w.fill_sources()
    w.select_source("playlist", pid)
    pump(0.3)
    w.search.set_text("rock")
    pump(0.5)
    target = None
    for row in w.songs.store:
        if row[3] == "Grunge Waltz":
            target = row
    if target is None:
        w.search.set_text("waltz")
        pump(0.5)
        target = [r for r in w.songs.store if r[3] == "Grunge Waltz"][0]
    w.songs.select_ids([target[0]])
    w.run("delete")
    pump(0.3)
    w.search.set_text("")
    pump(0.4)
    left = [r["title"] for r in lib.playlist_tracks(pid)]
    check("Grunge Waltz" not in left and len(left) == len(ids) - 1, "C8-03: Delete in a playlist narrowed by a search removes that song", left)

    # ---- C8-21 the name typed after New Playlist is taken (real keys)
    if XDO:
        w.present()
        a_ = w.get_allocation()
        ox, oy = w.get_window().get_origin()[1:]
        xdo("mousemove", ox + a_.width // 2, oy + a_.height // 2)      # keys go to the window under the pointer
        w.run("new-playlist")
        pump(0.4)
        xdo("type", "--delay", "40", "Road Trip")
        xdo("key", "Return")
        pump(0.4)
        names = [p["name"] for p in lib.playlists()]
        check("Road Trip" in names, "C8-21: the name typed after New Playlist is taken", names[-3:])

    # ---- C8-15 dragging a song that isn't selected onto a playlist (real pointer)
    w.select_source("music")
    pump(0.3)
    w.songs.view.get_selection().unselect_all()
    pid2 = lib.new_playlist("Drop Here")
    w.fill_sources()
    pump(0.3)
    if XDO:
        srow = [r for r in w.songs.store if r[3] == "Locomotion"][0]
        x0, y0 = row_xy(w.songs.view, srow.path, w.songs.columns["title"])
        dest = None
        for r in w.src_store:
            pass

        def find(model, path, it):
            if model[it][2] == "playlist" and model[it][3] == pid2:
                found.append(path.copy())
        found = []
        w.src_store.foreach(find)
        x1, y1 = row_xy(w.src_view, found[0], w.src_view.get_column(0))
        print("drag from %s to %s" % ((x0, y0), (x1, y1)))
        xdo("mousemove", x0, y0)
        xdo("mousedown", 1)
        for k in range(1, 9):
            xdo("mousemove", x0 + (x1 - x0) * k // 8, y0 + (y1 - y0) * k // 8)
        xdo("mouseup", 1)
        pump(0.6)
        got = [r["title"] for r in lib.playlist_tracks(pid2)]
        check(got == ["Locomotion"], "C8-15: a song not selected can be dragged onto a playlist", got)

    # ---- C8-26 songs dropped from the file manager (a separate program's drag, real pointer)
    if XDO:
        import re
        extra = os.path.join(tmp, "dropped")
        mkaudio.make(extra, 1.0)
        dropped = sorted(os.path.join(dp, f) for dp, _ds, fs in os.walk(extra) for f in fs)

        def drag_files(files, tx, ty):
            p = subprocess.Popen([sys.executable, os.path.join(os.environ["FOLIO_TESTS"], "dragsrc.py")] + files)
            pump(2.0)
            out = subprocess.run(["xdotool", "search", "--name", "Files stand-in", "getwindowgeometry"],
                                 capture_output=True, text=True).stdout
            m = re.search(r"Position: (\d+),(\d+)", out)
            if not m:
                p.kill()
                return False
            bx, by = int(m.group(1)) + 40, int(m.group(2)) + 20
            xdo("mousemove", bx, by)
            xdo("mousedown", 1)
            for k in range(1, 10):
                xdo("mousemove", bx + (tx - bx) * k // 9, by + (ty - by) * k // 9)
            for k in range(3):
                xdo("mousemove", tx + k, ty)
            xdo("mouseup", 1)
            pump(1.5)
            p.kill()
            return True
        before = len(lib.tracks())
        ox, oy = w.get_window().get_origin()[1:]
        drag_files(dropped[:2], ox + 700, oy + 520)
        check(len(lib.tracks()) == before + 2, "C8-26: songs dropped from the file manager join the library", (before, len(lib.tracks())))
        found = []
        w.src_store.foreach(lambda m_, pth, it: found.append(pth.copy()) if m_[it][2] == "playlist" and m_[it][3] == pid2 else None)
        x1, y1 = row_xy(w.src_view, found[0], w.src_view.get_column(0))
        drag_files(dropped[2:3], x1, y1)
        got = [r["path"] for r in lib.playlist_tracks(pid2)]
        check(dropped[2] in got, "C8-26: a song dropped from the file manager onto a playlist goes into it", got)
        m3u = os.path.join(tmp, "Dropped List.m3u")
        open(m3u, "w").write("#EXTM3U\n%s\n%s\n" % (songs["Blue Train"], songs["Adagio"] if "Adagio" in songs else songs["Sonata in C"]))
        drag_files([m3u], ox + 700, oy + 520)
        check(any(p["name"] == "Dropped List" for p in lib.playlists()), "C8-26: a playlist file dropped in becomes a playlist")

    # ---- C8-11 the list keeps its place when a song finishes or a rating is set
    many = os.path.join(tmp, "many")
    os.makedirs(many, exist_ok=True)
    first = songs["Blue Train"]
    for i in range(60):
        shutil.copy(first, os.path.join(many, "copy%02d.flac" % i))
    w.add_paths([many])
    w.select_source("music")
    pump(0.5)
    adj = w.songs.get_vadjustment()
    adj.set_value(adj.get_upper() - adj.get_page_size())
    pump(0.3)
    was = adj.get_value()
    lib.played(T["Locomotion"])
    lib.rate([T["Sonata in C"]], 60)
    pump(0.6)
    check(was > 0 and abs(adj.get_value() - was) < 2, "C8-11: the list keeps its place when a play is counted or a rating set",
          (was, adj.get_value()))

    # ---- C8-10 a big library: a rating redraws its row, not the whole list
    t0 = time.time()
    lib.rate([T["Locomotion"]], 100)
    pump(0.05)
    while w._lib_pending:
        pump(0.02)
    took = time.time() - t0
    row = [r for r in w.songs.store if r[0] == T["Locomotion"]][0]
    check(row[12] == 100 and took < 0.5, "C8-10: a rating shows in its row at once (%.2f s)" % took)

    # ---- C8-06, C8-14, C8-25 songs that can't be played; the end of the list
    gone = os.path.join(tmp, "gone")
    mkaudio.make(gone, 1.0)
    w.add_paths([gone])
    gids = [r["id"] for r in lib.tracks() if r["path"].startswith(gone)]
    msgs = []
    pb.listen(lambda ev, v: msgs.append(v) if ev == "error" else None)
    for g in gids[1:4]:
        os.remove(lib.track(g)["path"])
    lib.remove([gids[4]])
    pb.play_songs(gids[:6], 0)
    wait(lambda: eng.state == "playing", 5)
    eng.seek(max(0, eng.duration() - 0.3))
    ok = wait(lambda: pb.now and pb.now.get("id") == gids[5], 8)
    check(ok and len(msgs) == 1 and "3 songs couldn't be found" in msgs[0],
          "C8-06, C8-14: songs gone or deleted are passed over, with one message", msgs)
    eng.seek(max(0, eng.duration() - 0.3))
    ok = wait(lambda: pb.now is None and eng.state == "stopped", 8)
    check(ok and not w.lcd.stack.get_visible_child_name() == "playing", "C8-25: after the last song the display shows nothing loaded")
    pb.set_repeat("all")
    msgs.clear()
    for g in gids:
        p = (lib.track(g) or {"path": ""})["path"]
        if p and os.path.exists(p):
            os.remove(p)
    pb.play_songs(gids[:6], 0)
    pump(3)
    check(len(msgs) <= 2 and eng.state == "stopped", "C8-14: a list whose songs are all gone stops with one message", msgs)
    pb.set_repeat("off")

    # ---- C8-13 Next in the last moments of a song plays the next song, not the one after
    seq = [T["Blue Train"], T["Moment's Notice"], T["Locomotion"], T["Sonata in C"]]
    pb.play_songs(seq, 0)
    wait(lambda: eng.state == "playing", 5)
    eng.seek(eng.duration() - 0.6)
    wait(lambda: eng.cur.pending is not None, 3)
    pb.next()
    pump(0.8)
    check(pb.now and pb.now["id"] == seq[1], "C8-13: Next in the last moment plays the very next song", pb.now and pb.now["title"])
    eng.seek(eng.duration() - 0.6)
    wait(lambda: eng.cur.pending is not None, 3)
    eng.seek(0.5)
    pump(0.8)
    check(pb.now["id"] == seq[1] and eng.position() < 2.0, "C8-13: moving back in the last moment stays in the song",
          (pb.now["title"], eng.position()))
    pb.stop()

    # ---- C8-12 Pause during a crossfade pauses everything
    eng.crossfade = 2.0
    pb.play_songs(seq, 0)
    wait(lambda: eng.state == "playing", 5)
    eng.seek(eng.duration() - 2.5)
    wait(lambda: eng._fading is not None, 5)
    pb.toggle()
    pump(0.3)
    from gi.repository import Gst
    states = [p.pb.get_state(0)[1] for p in (eng.a, eng.b)]
    check(eng.state == "paused" and Gst.State.PLAYING not in states, "C8-12: Pause during a crossfade stops both songs", states)
    pb.stop()
    eng.crossfade = 0.0

    # ---- C8-20, C8-42 Up Next: Previous, reorder, remove
    pb.play_songs(seq, 1)
    pump(0.3)
    q = pb.queue
    q.play_next([T["Lazy Bird"], T["Teen Spirit Cover"], T["Grunge Waltz"]])
    shown = w.run("up-next")
    check(shown[:3] == [T["Lazy Bird"], T["Teen Spirit Cover"], T["Grunge Waltz"]], "Up Next lists the songs queued")
    q.move_up_next(2, 0)
    q.remove_up_next(1)
    w.up_next_popover.fill()
    check(q.up_next == [T["Grunge Waltz"], T["Teen Spirit Cover"]], "C8-42: Up Next songs can be moved and taken out", q.up_next)
    buttons = [b for b in _all(w.up_next_popover) if isinstance(b, Gtk.Button) and b.get_tooltip_text() == "Take out of Up Next"]
    buttons[0].clicked()
    pump(0.2)
    check(q.up_next == [T["Teen Spirit Cover"]], "C8-42: the ✕ beside a song takes it out", q.up_next)
    w.up_next_popover.popdown()
    pb.next()
    pump(0.3)
    pb.previous()
    pump(0.3)
    check(pb.now["id"] == seq[1], "C8-20: Previous after an Up Next song goes back to the list song", pb.now["title"])
    pb.stop()

    # ---- C8-16 Smart Playlist: times as m:ss, sizes in MB, mistakes said
    def fill(dlg):
        r = dlg.rule_rows[0]
        r["field"].set_active_id("duration")
        r["op"].set_active_id("is greater than")
        r["v1"].set_text("0:02")
        return Gtk.ResponseType.OK
    answer("Smart Playlist", fill)
    spec = dialogs.smart_playlist(w, None)
    check(spec and spec["rules"][0] == ["duration", "is greater than", 2.0], "C8-16: a time is typed as m:ss", spec and spec["rules"])
    said = []
    old_msg = dialogs.message
    dialogs.message = lambda win, text, title=None: said.append(text)

    def bad(dlg):
        r = dlg.rule_rows[0]
        r["field"].set_active_id("year")
        r["op"].set_active_id("is")
        r["v1"].set_text("199x")
        return Gtk.ResponseType.OK
    answer("Smart Playlist", bad)
    spec = dialogs.smart_playlist(w, None)
    dialogs.message = old_msg
    check(spec is None and said and "199x" in said[0], "C8-16: a mistyped number is pointed out, not counted as 0", said)
    dialogs.RESPONSE.pop("Smart Playlist", None)

    # ---- C8-27, C8-28 a shared library with a passcode plays, its playlists in their order
    other_dir = os.path.join(tmp, "other")
    mkaudio.make(other_dir, 2.0)
    other = L.Library(os.path.join(tmp, "other.db"))
    other.add_folder(other_dir)
    other.scan()
    ot = other.tracks()
    opl = other.new_playlist("Theirs", tracks=[ot[2]["id"], ot[0]["id"], ot[2]["id"]])
    srv = sharing.Share(other, "Den", "pw", port=0, host="127.0.0.1")
    port = srv.start()
    w.settings.set("share_known", {"127.0.0.1:%d" % port: "pw"})
    w._shares_found([{"name": "Den", "host": "127.0.0.1", "port": port, "songs": len(ot), "needs_pass": True}])
    w.select_source("shared", 0)
    pump(0.5)
    w.play_from_rows([r["id"] for r in w.rows], 0)
    ok = wait(lambda: eng.state == "playing", 8)
    check(ok, "C8-27: a song from a shared library with a passcode plays")
    pb.stop()
    r_ = w._remotes.get(0)
    check(r_ and [t["id"] for t in r_.playlist(opl)] == [ot[2]["id"], ot[0]["id"], ot[2]["id"]],
          "C8-28: a shared playlist keeps its own order")
    s = pb.session()
    check(s["now"] is None, "C8-09: a shared song isn't carried over to the next start")
    srv.stop()
    w.select_source("music")
    settings_text = open(w.settings.path).read()
    check("pw" not in settings_text, "C8-37: passcodes aren't written into settings.json")

    # ---- C8-29, C8-35, C8-34 stations that fail, and speaker errors
    ogg = os.path.join(tmp, "tone.ogg")
    mkaudio.tone(ogg, 4.0)
    stub = netstub.Stub(ogg)
    msgs.clear()
    busy = []
    pb.listen(lambda ev, v: busy.append(v) if ev == "busy" else None)
    pb.play_station(R.custom_station("Drops", stub.base + "/stream/u-jazz"))
    wait(lambda: eng.state == "playing", 8)
    ok = wait(lambda: busy, 30)
    check(ok and "trying again" in busy[0], "C8-29: a station that stops sending is tried again", busy)
    pump(3)
    check(eng.state == "playing", "C8-29: and plays again")
    pb.stop()
    orig = stub.route
    stub.route = lambda path, q_, h: ((b"[playlist]\nFile1=%s/stream/u-rock\n" % stub.base.encode()), "audio/x-scpls", 200) \
        if path == "/tunein" else (b"<html><body>Listen</body></html>" * 30, "text/html", 200) if path == "/page" else orig(path, q_, h)
    msgs.clear()
    pb.play_station(R.custom_station("Tunein", stub.base + "/tunein"))
    ok = wait(lambda: eng.state == "playing", 10)
    check(ok, "C8-35: a station playlist whose address doesn't say so plays", msgs)
    pb.stop()
    msgs.clear()
    pb.play_station(R.custom_station("Page", stub.base + "/page"))
    wait(lambda: msgs, 10)
    check(msgs and "web page" in msgs[0], "C8-35: a web page instead of a stream is called that", msgs)

    class Spk:
        name = "Kitchen"

        def set_volume(self, v):
            pass

        def play_file(self, *a):
            return False

        def stop(self):
            pass

        def close(self):
            pass

        def position(self):
            return None

        def state(self):
            return "STOPPED"
    msgs.clear()
    eng.play_to(Spk())
    pb.play_songs([T["Locomotion"]], 0)
    pump(0.5)
    check(msgs and "Kitchen" in msgs[0], "C8-34: a speaker that refuses a song says so", msgs)
    eng.play_to(None)

    # ---- C8-36 the desktop's controls get the cover and hear of seeks
    seen = []
    try:
        conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error:
        conn = None                 # no session bus in this run (the Wayland pass): nothing to hear
    if conn is not None:
        conn.signal_subscribe(None, "org.mpris.MediaPlayer2.Player", "Seeked", "/org/mpris/MediaPlayer2", None,
                              Gio.DBusSignalFlags.NONE, lambda *args: seen.append(args), None)
    from folio_chord import tags as TG
    art = open(os.path.join(os.environ["FOLIO_TESTS"], "art.png"), "rb").read()
    TG.set_artwork(songs["Sonata in C"], art, "image/png")
    pb.play_songs([T["Sonata in C"]], 0)
    wait(lambda: eng.state == "playing", 5)
    md = a.mpris.metadata()
    eng.seek(1.0)
    pump(0.5)
    check("mpris:artUrl" in md and md["mpris:artUrl"].unpack().startswith("file://"), "C8-36: the desktop is given the song's cover")
    if conn is not None and a.mpris.conn is not None:
        check(seen, "C8-36: the desktop hears when the position is moved")
    pb.stop()

    # ---- C8-23 removing a music folder in Options takes its songs out of the library
    answer("Choose", lambda dl: 2)          # Remove from Library
    od = dialogs.OptionsDialog(w) if hasattr(dialogs, "OptionsDialog") else None
    if od is not None:
        rows = [r for r in od.folders if r[0] == gone]
        for r in rows:
            od.folders.remove(r.iter)
        od.apply()
        od.destroy()
        check(not [r for r in lib.tracks() if r["path"].startswith(gone)], "C8-23: removing a folder in Options removes its songs from the library")
    dialogs.RESPONSE.pop("Choose", None)

    # ---- C8-40 dates the way the computer writes them, without seconds
    txt = views.fmt_date(1700000000)
    check(txt and txt.count(":") == 1, "C8-40: dates follow the computer's language and region", txt)


def _all(widget):
    out = [widget]
    if isinstance(widget, Gtk.Container):
        for c in widget.get_children():
            out += _all(c)
    return out


run(main)
