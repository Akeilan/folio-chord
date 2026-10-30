# C3-12..C3-26 in the window: copying into the media folder and what happens when a CD goes in,
# per-song equalizer and remembered places, watching the folders, podcast speed and skips and the
# sleep timer, station playlists and your own stations, carrying on where you left off, lyrics,
# duplicates, Cover Flow, nested Smart Playlist rules, importing an iTunes library, the sound
# outputs, your own equalizer presets, and Organize Music Folder with undo.
import datetime
import os
import plistlib
import shutil
import sys

sys.path.insert(0, os.environ["FOLIO_TESTS"])
from uicommon import OUT, answer, check, music, pump, run, shot, wait  # noqa: E402
from gi.repository import Gtk  # noqa: E402
import mkaudio  # noqa: E402
import netstub  # noqa: E402
from folio_chord import dialogs, player, radio, tags, watcher  # noqa: E402


def main():
    w = win  # noqa: F821
    a = app  # noqa: F821
    lib, pb, s = a.lib, a.playback, w.settings
    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"), "chord_more_%d" % os.getpid())
    os.makedirs(tmp, exist_ok=True)
    d, songs = music(w, secs=14.0)
    ids = {r["title"]: r["id"] for r in w.rows}

    # ---- C3-12 copy into the media folder; what to do when a CD goes in
    media = a.media_folder()
    ext = os.path.join(tmp, "outside.ogg")
    mkaudio.tone(ext, 1.0)
    tags.write(ext, {"title": "Outside", "artist": "Band", "album": "Live", "track_no": 3})
    s["copy_to_media"] = True
    got = w.add_paths([ext])
    r = lib.track(got[0])
    check(r["path"].startswith(media) and os.path.exists(ext), "Copy files to the media folder when adding them", r["path"])
    s["copy_to_media"] = False
    ran = []
    real_run = w.run
    w.run = lambda cmd, *x: ran.append(cmd) if cmd == "import-cd" else real_run(cmd, *x)
    w.cd_info, w._cd_acted = {"discid": "d1", "album": "Disc"}, None
    s["cd_after_import"] = "import"
    w._cd_inserted()
    check(ran == ["import-cd"], "When you insert a CD: Import", ran)
    w.cd_info, w._cd_acted = {"discid": "d2", "album": "Disc"}, None
    s["cd_after_import"] = "ask"
    answer("Confirm", Gtk.ResponseType.CANCEL)
    w._cd_inserted()
    dialogs.RESPONSE.pop("Confirm", None)
    check(ran == ["import-cd"], "Ask: nothing is imported when you say no")
    w.run = real_run
    w.cd_info = None
    s["cd_after_import"] = "nothing"
    w.select_source("music")

    # ---- C3-13 a song's own equalizer preset; carry on from the remembered place
    bt = ids["Blue Train"]
    lib.update([bt], eq="Rock", remember_position=1, position=6.0)
    pb.play_songs([bt], 0)
    wait(lambda: pb.engine.state == "playing", 5)
    pump(0.5)
    rock = player.PRESETS["Rock"][1]
    check(abs(pb.engine.cur.eq.get_property("band0") - rock[0]) < 0.01, "a song plays with its own equalizer preset")
    check(pb.engine.position() >= 5.5, "Remember playback position: it carries on from there", pb.engine.position())
    pb.stop()

    # ---- C3-14 watching the music folders
    wt = watcher.Watcher(lib, on_change=lambda: None, delay_ms=200)
    wt.watch([d])
    new = os.path.join(d, "Late Arrival.ogg")
    mkaudio.tone(new, 1.0)
    tags.write(new, {"title": "Late Arrival", "artist": "Coltrane Quartet", "album": "Night Sessions"})
    ok = wait(lambda: lib.q("select id from tracks where path=?", (new,)), 8)
    check(bool(ok), "a new file in the music folder shows up by itself")
    os.remove(new)
    ok = wait(lambda: not lib.q("select id from tracks where path=? and not missing", (new,)), 8)
    check(bool(ok), "and goes when it's deleted")
    wt.stop()

    # ---- C3-15 podcast speed, skips, sleep timer; C3-17 station playlists and your own stations
    ogg = os.path.join(tmp, "tone.ogg")
    mkaudio.tone(ogg, 20.0)
    stub = netstub.Stub(ogg)
    pid = a.pods.subscribe(stub.base + "/feed/tech")
    eid = a.pods.episodes(pid)[0]["id"]
    pb.play_episodes([eid], 0)
    wait(lambda: pb.engine.state == "playing", 8)
    check(w.lcd.b_back.get_visible() and w.lcd.b_speed.get_visible(), "an episode shows back 15, forward 30 and speed")
    check(w.run("speed:1.5") == 1.5 and pb.engine.rate == 1.5, "Playback Speed")
    check(float(a.pods.show(pid)["speed"]) == 1.5, "the speed is kept for the show")
    check(w.lcd.b_speed.get_label() == "1.5×", "the speed shows", w.lcd.b_speed.get_label())
    w.lcd._next_speed()
    check(pb.engine.rate == 1.75, "clicking it steps up", pb.engine.rate)
    wait(lambda: pb.engine.position() > 0.5, 4)
    p0 = pb.engine.position()
    w.run("skip:30")
    pump(0.4)
    check(pb.engine.state == "stopped" or pb.engine.position() > p0 + 5 or pb.engine.position() >= pb.engine.duration() - 1,
          "Skip Forward 30 Seconds", (p0, pb.engine.position()))
    pb.play_episodes([eid], 0)
    wait(lambda: pb.engine.state == "playing", 8)
    check(pb.engine.rate == 1.75, "the show's speed comes back next time")
    pb.engine.seek(12)
    pump(0.3)
    w.run("skip:-15")
    pump(0.4)
    check(pb.engine.position() < 3, "Skip Back 15 Seconds", pb.engine.position())
    w.run("sleep:30")
    check(pb.sleep_at and w.sleep_label.get_visible(), "the sleep timer is set and shown")
    w.run("sleep:0")
    check(not pb.sleep_at, "and turned off")
    w.run("sleep:-1")
    check(pb.sleep_end_of_item, "sleep at the end of this episode")
    w.run("sleep:0")
    pb.stop()
    w.lcd.update()
    pb.play_uri(stub.base + "/station.pls", "From a playlist")
    ok = wait(lambda: pb.engine.state == "playing", 8)
    check(ok and "/stream/from-pls" in (pb.now or {}).get("uri", ""), "a .pls address plays the stream inside it", (pb.now or {}).get("uri"))

    def fill(dlg):
        dlg.name_entry.set_text("My Station")
        return Gtk.ResponseType.OK
    answer("Add Stream to Favourites", fill)
    st = w.run("add-stream")
    check(st and radio.is_favourite(lib, st) and st["name"] == "My Station", "Add Stream to Favourites, with a name")
    pb.stop()

    # ---- C3-18 carry on where you left off
    w.select_source("music")
    w.load_songs()
    order = [r["id"] for r in w.rows]
    pb.play_songs(order, 2)
    wait(lambda: pb.engine.state == "playing", 5)
    pb.engine.seek(4)
    pump(0.3)
    pb.queue.add([order[0]])
    pb.save_session()
    pb.stop()
    pb.queue.start([], 0)
    pb.now = None
    check(pb.restore_session(), "the session comes back")
    wait(lambda: pb.engine.state == "paused", 5)
    check(pb.now["id"] == order[2] and pb.engine.state == "paused", "the song, paused", (pb.now["id"], pb.engine.state))
    check(abs(pb.engine.position() - 4) < 1.5, "at its place", pb.engine.position())
    check(pb.queue.source == order and pb.queue.up_next == [order[0]], "with the list and Up Next")
    pb.stop()

    # ---- C3-19 lyrics
    path = lib.track(bt)["path"]
    tags.set_lyrics(path, "So blue\nthe train")
    w.songs.select_ids([bt])
    if not w.lyrics_box.get_visible():
        w.run("toggle-lyrics")
    pump(0.2)
    buf = w.lyrics_view.get_buffer()
    check(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False) == "So blue\nthe train", "the lyrics pane shows the song's lyrics")
    shot(w, "more_lyrics")

    def edit(dlg):
        dlg.lyrics.get_buffer().set_text("New words")
        return Gtk.ResponseType.OK
    answer("Get Info", edit)
    w.run("get-info")
    pump(0.3)
    check(tags.lyrics(path) == "New words", "Get Info > Lyrics writes them into the file", tags.lyrics(path))
    w.run("toggle-lyrics")
    check(not w.lyrics_box.get_visible(), "Show/Hide Lyrics")

    # ---- C3-20 duplicates
    dup_dir = os.path.join(tmp, "dups")
    os.makedirs(dup_dir, exist_ok=True)
    shutil.copy(lib.track(bt)["path"], os.path.join(dup_dir, "copy" + os.path.splitext(path)[1]))
    w.add_paths([dup_dir])
    n = w.run("duplicates:name")
    check(n == 2 and {r["title"] for r in w.rows} == {"Blue Train"}, "Show Duplicate Items", n)
    shot(w, "more_duplicates")
    n = w.run("duplicates:off")
    check(n > 2, "Show All Items")

    # ---- C3-21 Cover Flow
    w.run("view:coverflow")
    pump(0.4)
    cf = w.coverflow
    check(cf.get_visible() and len(cf.albums) >= 3, "Cover Flow shows the albums", len(cf.albums))
    chosen = []
    cf.connect("chosen", lambda _w, rows: chosen.append(rows))
    cf.go(1)
    pump(0.6)
    check(cf.index == 1 and chosen, "flipping to an album picks its songs")
    shot(w, "more_coverflow")
    w.run("view:list")
    check(not cf.get_visible(), "and back to the list")

    # ---- C3-22 nested rules and Playlist is
    plid = lib.new_playlist("Pick", tracks=[bt])

    def smart(dlg):
        dlg.name.set_text("Nested")
        rec = dlg.rule_rows[0]
        rec["field"].set_active_id("playlist")
        pump(0.1)
        rec["op"].set_active_id("is")
        rec["playlist"].set_active_id(str(plid))
        g = dlg.add_group({"match": "any", "rules": [["artist", "contains", "Garage"], ["artist", "contains", "Hall"]]})
        check(g is not None, "a group of rules can be added")
        dlg.match.set_active_id("any")
        return Gtk.ResponseType.OK
    answer("Smart Playlist", smart)
    sp = w.run("new-smart")
    got = {r["title"] for r in lib.playlist_tracks(sp)}
    want = {"Blue Train", "Sonata in C", "Teen Spirit Cover", "Grunge Waltz"}
    check(got == want, "Playlist is … or (any of a group)", got)
    shot(w, "more_smart")

    # ---- C3-23 iTunes library
    xf = os.path.join(tmp, "iTunes Library.xml")
    with open(xf, "wb") as f:
        plistlib.dump({"Major Version": 1, "Tracks": {
            "7": {"Track ID": 7, "Name": "Lazy Bird", "Artist": "Coltrane Quartet", "Album": "Night Sessions", "Rating": 80,
                  "Play Count": 9, "Play Date UTC": datetime.datetime(2020, 1, 1), "Total Time": 14000,
                  "Location": "file://localhost/C:/Music/Coltrane%20Quartet/Night%20Sessions/04%20Lazy%20Bird.flac"}},
            "Playlists": [{"Name": "From iTunes", "Playlist Items": [{"Track ID": 7}]}]}, f)
    real_choose = dialogs.choose_files
    dialogs.choose_files = lambda *x, **k: [xf]
    res = w.run("import-itunes")
    dialogs.choose_files = real_choose
    lb = lib.track(ids["Lazy Bird"])
    check(res and res["songs"] == 1 and lb["rating"] == 80 and lb["play_count"] >= 9, "File > Library > Import iTunes Library…", res)
    check(any(p["name"] == "From iTunes" for p in lib.playlists()), "its playlists appear")

    # ---- C3-24 sound outputs
    names = w.run("outputs")
    check(isinstance(names, list) and "The desktop's choice" in w.output_buttons, "Window > Sound Output lists the outputs", names)
    if names:
        w.output_buttons[names[0]].set_active(True)
        check(s["output"] == names[0], "choosing one is remembered", s["output"])
        w.output_buttons["The desktop's choice"].set_active(True)
    check(s["output"] == "", "the desktop's choice again")
    w.output_popover.popdown()

    # ---- C3-25 your own equalizer presets
    eq = w.run("equalizer")
    eq.scales[0].set_value(7.0)
    name = eq.make_preset("Mine")
    check(name == "Mine" or "Mine" in (s.get("eq_custom") or {}), "Make Preset…")
    check("Mine" in a.eq_presets(), "your preset is listed with the others (and in Get Info)")
    check(a.eq_preset("Mine")[1][0] == 7.0, "with its settings")
    eq.hide()

    # ---- C3-26 Organize Music Folder
    root = os.path.join(tmp, "Music")
    os.makedirs(os.path.join(root, "mess", "deeper"), exist_ok=True)
    for i, (t, ar, al) in enumerate((("Song A", "Artist One", "Album X"), ("Song B", "Artist Two", "Album Y"))):
        p = os.path.join(root, "mess" if i == 0 else "mess/deeper", "track%d.ogg" % i)
        mkaudio.tone(p, 1.0)
        tags.write(p, {"title": t, "artist": ar, "album": al, "track_no": i + 1})
    w.add_paths([root])
    seen = []

    def org(dlg):
        seen.append(len(dlg.moves))
        return Gtk.ResponseType.OK
    answer("Organize Music Folder", org)
    done = w.run("organize")
    check(seen and seen[0] >= 2, "it shows what will move first", seen)
    want = os.path.join(root, "Artist One", "Album X", "01 Song A.ogg")
    check(os.path.exists(want) and not os.path.isdir(os.path.join(root, "mess")), "songs go into Artist / Album / Song; empty folders go", done)
    check(lib.q("select id from tracks where path=?", (want,)), "the library follows the file")
    back = w.run("undo-organize")
    check(back and os.path.exists(os.path.join(root, "mess", "track0.ogg")), "Undo Organize Music Folder", back)
    stub.stop()


run(main)
