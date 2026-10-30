# C3-02, C3-08: playing in the window — the transport buttons and status display, play counts and
# skips, shuffle and repeat, Up Next, volume and mute, Sound Check, the equalizer window, the Mini
# Player, the visualizer, Go to Current Song, and the desktop's player controls (MPRIS).
import os
import sys

sys.path.insert(0, os.environ["FOLIO_TESTS"])
from uicommon import check, music, pump, run, shot, wait  # noqa: E402
from gi.repository import Gio, GLib, Gtk  # noqa: E402
from folio_chord import player  # noqa: E402


def main():
    lib = app.lib  # noqa: F821
    w = win  # noqa: F821
    pb = app.playback  # noqa: F821
    d, songs = music(w, secs=3.0)
    ids = {r["title"]: r["id"] for r in w.rows}
    # play from the list (double-click / Enter)
    w.songs.emit("play", 0)
    ok = wait(lambda: pb.engine.state == "playing", 5)
    check(ok and pb.now["title"] == "Blue Train", "double-click plays the song")
    check(w.lcd.title.get_text() == "Blue Train" and w.lcd.stack.get_visible_child_name() == "playing", "the status display shows it")
    check(w.b_play.get_tooltip_text() == "Pause", "the play button becomes pause")
    check([r[27] for r in w.songs.store][0], "the playing song is marked in the list")
    shot(w, "play_playing")
    wait(lambda: pb.now and pb.now["title"] == "Moment's Notice", 6)
    check(pb.now["title"] == "Moment's Notice", "the next song follows")
    check(lib.track(ids["Blue Train"])["play_count"] == 1, "a finished song counts as played")
    # pause, resume, next, previous
    w.run("play-pause")
    wait(lambda: pb.engine.state == "paused", 3)
    check(pb.engine.state == "paused" and w.b_play.get_tooltip_text() == "Play", "Space / Play-Pause pauses")
    w.run("play-pause")
    wait(lambda: pb.engine.state == "playing", 3)
    w.run("next")
    wait(lambda: pb.now["title"] == "Locomotion", 3)
    check(pb.now["title"] == "Locomotion", "Next")
    w.run("previous")
    wait(lambda: pb.now["title"] == "Moment's Notice", 3)
    check(pb.now["title"] == "Moment's Notice", "Previous (at the start of a song)")
    # a skip is counted when you move on a few seconds in
    w.run("stop")
    check(pb.engine.state == "stopped", "Stop")
    # unchecked songs are left out when playing through
    lib.update([ids["Locomotion"]], checked=0)
    w.load_songs()
    w.songs.emit("play", 1)
    wait(lambda: pb.now and pb.now["title"] == "Lazy Bird", 6)
    check(pb.now["title"] == "Lazy Bird", "unchecked songs are skipped")
    lib.update([ids["Locomotion"]], checked=1)
    w.run("stop")
    # Up Next
    w.load_songs()
    w.songs.emit("play", 0)
    wait(lambda: pb.engine.state == "playing", 4)
    w.songs.select_ids([ids["Sonata in C"]])
    w.run("play-next")
    w.songs.select_ids([ids["Grunge Waltz"]])
    w.run("add-up-next")
    items = w.run("up-next")
    check(items[:2] == [ids["Sonata in C"], ids["Grunge Waltz"]], "Up Next: Play Next, then Add to Up Next")
    w.up_next_popover.popdown()
    w.run("next")
    wait(lambda: pb.now["title"] == "Sonata in C", 3)
    check(pb.now["title"] == "Sonata in C", "Up Next plays first")
    w.run("clear-up-next")
    check(pb.queue.up_next == [], "Clear Up Next")
    # shuffle and repeat buttons
    w.b_shuffle.set_active(True)
    pump(0.1)
    check(pb.queue.shuffle and w.settings["shuffle"], "the shuffle button")
    w.run("shuffle-by:albums")
    check(pb.queue.shuffle_by == "albums" and "albums" in w.b_shuffle.get_tooltip_text(), "Shuffle by Albums")
    w.b_shuffle.set_active(False)
    w.b_repeat.clicked()
    check(pb.queue.repeat == "all", "repeat button: all")
    w.b_repeat.clicked()
    check(pb.queue.repeat == "one" and "one" in w.b_repeat.get_tooltip_text(), "then one")
    w.b_repeat.clicked()
    check(pb.queue.repeat == "off", "then off")
    # volume and mute
    w.volume.set_value(0.4)
    check(abs(pb.engine.volume - 0.4) < 0.01 and abs(w.settings["volume"] - 0.4) < 0.01, "the volume slider")
    w.run("volume-up")
    check(abs(w.volume.get_value() - 0.5) < 0.01, "Increase Volume moves the slider")
    w.run("mute")
    check(pb.engine.volume == 0, "Mute")
    w.run("mute")
    check(abs(pb.engine.volume - 0.5) < 0.01, "and back")
    # go to the current song from another view
    if pb.engine.state != "playing":
        w.songs.emit("play", 0)
        wait(lambda: pb.engine.state == "playing", 3)
    w.select_source("radio")
    w.run("go-current")
    check(w.source[0] == "music" and pb.now["id"] in w.songs.selected_ids(), "Go to Current Song",
          (w.source, pb.now and pb.now.get("id"), w.songs.selected_ids()))
    # equalizer
    eq = w.run("equalizer")
    eq.preset.set_active_id("Rock")
    pump(0.2)
    check(eq.on.get_active() and w.settings["eq_preset"] == "Rock" and abs(pb.engine.cur.eq.get_property("band0") - 5.0) < 0.01,
          "Equalizer: a preset turns it on and reaches the sound")
    eq.scales[3].set_value(-6)
    pump(0.1)
    check(eq.preset.get_active_id() == "Manual" and abs(pb.engine.cur.eq.get_property("band3") + 6) < 0.01, "moving a band: Manual")
    eq.on.set_active(False)
    check(pb.engine.cur.eq.get_property("band0") == 0.0, "Equalizer off")
    shot(eq, "play_equalizer")
    eq.hide()
    # Sound Check from Options
    from uicommon import answer

    def opts(dlg):
        dlg.sc.set_active(True)
        dlg.xfade.set_active(True)
        dlg.xfade_s.set_value(3)
        return Gtk.ResponseType.OK
    answer("Options", opts)
    w.run("options")
    check(pb.engine.sound_check and pb.engine.crossfade == 3.0, "Options: Sound Check and crossfade")
    lib.update([ids["Blue Train"]], rg_track=-5.0)
    check(abs(pb.engine.gain_db(pb.song_item(ids["Blue Train"])) + 5.0) < 0.01, "Sound Check uses the song's ReplayGain")
    answer("Options", lambda dlg: (dlg.sc.set_active(False), dlg.xfade.set_active(False), Gtk.ResponseType.OK)[2])
    w.run("options")
    # Mini Player
    mini = w.run("mini-player")
    pump(0.3)
    check(mini.get_visible() and not w.get_visible() and mini.title.get_text() == pb.now["title"], "Mini Player shows the song")
    shot(mini, "play_mini")
    w.run("front")
    pump(0.2)
    check(w.get_visible() and not mini.get_visible(), "back to the full window")
    # visualizer
    vis = w.run("visualizer")
    pump(0.3)
    w.load_songs()
    w.songs.emit("play", 0)
    ok = wait(lambda: sum(vis.levels) > 0.5, 6)
    check(ok and pb.engine.spectrum_on and vis.frames > 3, "the visualizer moves with the music",
          (sum(vis.levels), pb.engine.spectrum_on, vis.frames, pb.engine.state))
    shot(vis, "play_visualizer")
    vis.hide()
    pump(0.2)
    check(not pb.engine.spectrum_on, "closing it stops the spectrum")
    # MPRIS, when there's a session bus
    if app.mpris.conn is not None:  # noqa: F821
        import subprocess
        q = ("import gi; from gi.repository import Gio, GLib; b = Gio.bus_get_sync(Gio.BusType.SESSION, None); "
             "r = b.call_sync('org.mpris.MediaPlayer2.folio_chord', '/org/mpris/MediaPlayer2', 'org.freedesktop.DBus.Properties', 'Get', "
             "GLib.Variant('(ss)', ('org.mpris.MediaPlayer2.Player', 'Metadata')), None, 0, 3000, None); "
             "print(r.unpack()[0].get('xesam:title')); "
             "b.call_sync('org.mpris.MediaPlayer2.folio_chord', '/org/mpris/MediaPlayer2', 'org.mpris.MediaPlayer2.Player', 'Pause', "
             "None, None, 0, 3000, None)")
        if pb.engine.state != "playing":
            w.run("play-pause")
            wait(lambda: pb.engine.state == "playing", 3)
        title = pb.now["title"]
        proc = subprocess.Popen([sys.executable, "-c", q], stdout=subprocess.PIPE, text=True)
        wait(lambda: proc.poll() is not None, 8)
        out = proc.stdout.read().strip()
        check(out == title, "MPRIS: the desktop sees what's playing", (out, title))
        wait(lambda: pb.engine.state == "paused", 3)
        check(pb.engine.state == "paused", "MPRIS: the desktop's pause button")
    else:
        print("(no session bus: MPRIS not checked)")
    # an unplayable file is reported and skipped
    bad = os.path.join(d, "broken.mp3")
    open(bad, "wb").write(b"not audio at all" * 100)
    pb._start({"kind": "song", "id": -1, "uri": player.uri_of(bad), "title": "Broken", "duration": 1, "rg": None})
    wait(lambda: w.lcd.busy, 4)
    check(w.lcd.busy and "couldn't be played" in w.lcd.busy, "a file that won't play says so")
    w.run("stop")


run(main)
