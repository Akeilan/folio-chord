# C3-05, C3-06: internet radio and podcasts in the window, against a stand-in for the internet.
import os
import sys

sys.path.insert(0, os.environ["FOLIO_TESTS"])
from uicommon import answer, check, pump, run, shot, wait  # noqa: E402
from gi.repository import Gtk  # noqa: E402
import mkaudio  # noqa: E402
import netstub  # noqa: E402
from folio_chord import dialogs, podcasts as P, radio as R  # noqa: E402


def main():
    w = win  # noqa: F821
    pb = app.playback  # noqa: F821
    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"), "chord_net_%d" % os.getpid())
    os.makedirs(tmp, exist_ok=True)
    ogg = os.path.join(tmp, "tone.ogg")
    mkaudio.tone(ogg, 6.0)
    stub = netstub.Stub(ogg)
    os.environ["FOLIO_CHORD_RADIO_API"] = stub.base
    P.APPLE = stub.base
    P.PODCASTINDEX = stub.base + "/pi"
    app.radio._servers = None  # noqa: F821
    # ---------------------------------------------------------------- radio
    w.select_source("radio")
    rv = w.radioview
    ok = wait(lambda: len(rv.stations) == 3, 8)
    check(ok and rv.heading.get_text() == "Most Popular", "Radio opens on the most popular stations", rv.heading.get_text())
    wait(lambda: rv.cat_store.iter_n_children(rv.genres) == 3, 6)
    check(rv.cat_store.iter_n_children(rv.genres) == 3 and rv.cat_store.iter_n_children(rv.countries) == 2,
          "genres, countries and languages from the directory")
    it = rv.cat_store.iter_children(rv.genres)
    rv.cat_view.get_selection().select_iter(it)
    wait(lambda: [s["name"] for s in rv.stations] == ["Rock Radio Test"], 6)
    check([s["name"] for s in rv.stations] == ["Rock Radio Test"], "By Genre: rock")
    w.search.set_text("jazz")
    wait(lambda: [s["name"] for s in rv.stations] == ["Jazz FM Test"], 6)
    check([s["name"] for s in rv.stations] == ["Jazz FM Test"] and "jazz" in rv.heading.get_text(), "search stations by name")
    shot(w, "net_radio")
    rv.view.get_selection().select_path(Gtk.TreePath.new_first())
    check(rv.toggle_favourite() is True and R.is_favourite(app.lib, rv.stations[0]), "Add to Favourites")  # noqa: F821
    check(rv.store[0][0] == "♥" and rv.fav_btn.get_label() == "Remove from Favourites", "the heart and the button follow")
    rv.view.get_selection().select_path(Gtk.TreePath.new_first())
    st = rv.play_selected()
    ok = wait(lambda: pb.engine.state == "playing", 8)
    check(ok and pb.now["kind"] == "station" and w.lcd.title.get_text() == "Jazz FM Test", "play a station")
    ok = wait(lambda: pb.stream_title == stub.TITLE, 8)
    check(ok and w.lcd.sub.get_text() == stub.TITLE, "the song playing on the station shows in the status display", w.lcd.sub.get_text())
    check(any(h[0] == "/json/url/u-jazz" for h in stub.hits), "the directory is told which station was played")
    check(not w.lcd.scale.get_visible(), "no progress bar for a live stream")
    shot(w, "net_station")
    w.run("play-pause")
    wait(lambda: pb.engine.state == "stopped", 3)
    check(pb.engine.state == "stopped" and w.b_play.get_tooltip_text() == "Play", "a station stops rather than pausing")
    w.search.set_text("")
    pump(0.3)
    rv.cat_view.get_selection().select_path(Gtk.TreePath.new_from_indices([2]))
    pump(0.2)
    check([s["name"] for s in rv.stations] == ["Jazz FM Test"], "Recently Played")
    rv.cat_view.get_selection().select_path(Gtk.TreePath.new_from_indices([1]))
    pump(0.2)
    check([s["name"] for s in rv.stations] == ["Jazz FM Test"], "Favourites")
    rv.view.get_selection().select_path(Gtk.TreePath.new_first())
    w.run("delete")
    check(rv.stations == [] and not R.favourites(app.lib), "Delete takes a station out of Favourites")  # noqa: F821
    # Open Stream
    answer("Open Stream", lambda d: (d.entry.set_text(stub.base + "/stream/x"), Gtk.ResponseType.OK)[1])
    w.run("open-stream")
    ok = wait(lambda: pb.engine.state == "playing", 8)
    check(ok and pb.now["uri"].endswith("/stream/x"), "Advanced > Open Stream")
    w.run("stop")
    # ---------------------------------------------------------------- podcasts
    w.select_source("podcasts")
    pv = w.podview
    check(pv.stack.get_visible_child_name() == "empty", "no podcasts yet: says how to find some")
    pv.btn["directory"].set_active(True)
    ok = wait(lambda: len(pv.dir_store) == 2, 8)
    check(ok and [r[2]["title"] for r in pv.dir_store] == ["Garden Show", "Tech Show"], "the Podcast Directory opens on the charts")
    check("Apple" in pv.dir_hint.get_text(), "and says where they're from", pv.dir_hint.get_text())
    pv.genre.set_active_id("1318")
    wait(lambda: len(pv.dir_store) == 1, 6)
    check([r[2]["title"] for r in pv.dir_store] == ["Tech Show"], "charts by category")
    w.search.set_text("garden")
    wait(lambda: len(pv.dir_store) == 1 and pv.dir_store[0][2]["title"] == "Garden Show", 6)
    check(pv.dir_store[0][2]["title"] == "Garden Show" and "garden" in pv.dir_label.get_text(), "search the directory")
    shot(w, "net_directory")
    pv.subscribe_row(Gtk.TreePath.new_first())
    ok = wait(lambda: len(app.pods.shows()) == 1 and not pv.btn["directory"].get_active(), 8)  # noqa: F821
    check(ok and pv.stack.get_visible_child_name() == "mine", "subscribe: the show is added and shown")
    wait(lambda: len(pv.ep_store) == 2, 4)
    check([r[2] for r in pv.ep_store] == ["Garden episode 2", "Garden episode 1"], "its episodes, newest first")
    ok = wait(lambda: any(r[5] == "Downloaded" for r in pv.ep_store), 8)
    check(ok and pv.ep_store[0][5] == "Downloaded" and pv.ep_store[1][5] == "Stream", "the newest is downloaded automatically")
    check(w.src_store and any(r[2] == "podcasts" and r[4] == "2" for r in w.src_store), "the source list shows the unplayed count")
    shot(w, "net_podcasts")
    w.search.set_text("")
    pump(0.2)
    pv.ep_view.get_selection().select_path(Gtk.TreePath.new_from_indices([1]))
    pump(0.1)
    check(pv.notes.get_buffer().get_property("text") == "Notes for 1", "show notes under the list")
    eid = pv.play_selected()
    ok = wait(lambda: pb.engine.state == "playing" and pb.now["kind"] == "episode", 8)
    check(ok and pb.now["title"] == "Garden episode 1" and pb.now["stream"], "play an episode (streamed)", (pb.engine.state, pb.now))
    wait(lambda: pb.engine.position() > 5.2, 10)
    pb.engine.pause()
    pump(0.2)
    pb._save_position()
    check(app.pods.episode(eid)["position"] > 5, "where you stopped is kept")  # noqa: F821
    pb.engine.resume()
    ok = wait(lambda: app.pods.episode(eid)["played"] == 1, 10)  # noqa: F821
    check(ok, "played to the end: marked as played")
    w.run("stop")
    pv.ep_view.get_selection().select_path(Gtk.TreePath.new_from_indices([1]))
    first = pv.selected_episodes()[0]
    w.run("pod:unplayed")
    check(app.pods.episode(first)["played"] == 0, "Mark as Unplayed")  # noqa: F821
    pv.ep_view.get_selection().select_all()
    w.run("pod:played")
    check(all(e["played"] for e in app.pods.episodes()), "Mark as Played")  # noqa: F821
    pv.ep_view.get_selection().select_path(Gtk.TreePath.new_from_indices([1]))
    w.run("pod:download")
    ok = wait(lambda: pv.ep_store[1][5] == "Downloaded", 8)
    check(ok, "Download Episode")
    w.run("pod:remove-download")
    pump(0.3)
    check(pv.ep_store[1][5] == "Stream", "Remove Download", [tuple(r)[:6] for r in pv.ep_store])
    # new episodes turn up on refresh
    stub.feeds_n["garden"] = 4
    pv.on_refresh()
    ok = wait(lambda: len(pv.ep_store) == 4, 8)
    check(ok and pv.ep_store[0][1] == "●", "Refresh finds new episodes, marked new")
    # settings for a show
    answer("Podcast Settings", lambda d: (d.auto.set_active(False), Gtk.ResponseType.OK)[1])
    pv.on_settings()
    check(app.pods.show(pv.current_show())["auto_download"] == 0, "a show's settings: don't download automatically")  # noqa: F821
    # OPML out and in, by its address
    out = os.path.join(tmp, "subs.opml")
    dialogs.save_file = lambda *a: out
    w.run("export-opml")
    check(os.path.exists(out) and "garden" in open(out).read(), "Export Podcasts (OPML)")
    answer("Subscribe to Podcast", lambda d: (d.entry.set_text(stub.base + "/feed/tech"), Gtk.ResponseType.OK)[1])
    w.run("subscribe")
    ok = wait(lambda: len(app.pods.shows()) == 2, 8)  # noqa: F821
    check(ok, "File > Subscribe to Podcast by its address")
    # the Podcast Index directory, from Options
    def opts(d):
        d.dir_pi.set_active(True)
        d.pi_key.set_text("k")
        d.pi_secret.set_text("s")
        return Gtk.ResponseType.OK
    answer("Options", opts)
    w.run("options")
    pv.btn["directory"].set_active(True)
    w.search.set_text("tech")
    ok = wait(lambda: len(pv.dir_store) == 1 and "Podcast Index" in pv.dir_hint.get_text(), 8)
    check(ok and pv.dir_store[0][3] == "Subscribed", "Options: search Podcast Index instead (signed requests)", pv.dir_hint.get_text())
    pv.btn["directory"].set_active(False)
    w.search.set_text("")
    # unsubscribe
    answer("Confirm", Gtk.ResponseType.OK)
    pid = pv.current_show()
    pv.on_unsubscribe()
    check(len(app.pods.shows()) == 1 and app.pods.show(pid) is None, "Unsubscribe")  # noqa: F821
    stub.stop()


run(main)
