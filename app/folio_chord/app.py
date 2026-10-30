"""Folio Chord, the application: settings, the library, playback (what plays, play counts,
skips, podcast positions), and the window."""
import json
import os
import sys
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk  # noqa: E402

from . import APP_ID, APP_NAME, VERSION, appearance, fontfix, library, player, playqueue, podcasts, radio, theme  # noqa: E402

DEFAULTS = {
    "music_folders": None,            # None: ~/Music
    "media_folder": None,             # where imported CDs go; None: ~/Music
    "import_format": "AAC", "import_kbps": 256, "cd_lookup": True, "cd_after_import": "nothing",
    "crossfade": False, "crossfade_secs": 6, "sound_check": False, "volume": 0.8,
    "eq_on": False, "eq_preset": "Flat", "eq_preamp": 0.0, "eq_bands": [0] * 10,
    "shuffle": False, "shuffle_by": "songs", "repeat": "off",
    "view": "list", "browser": True, "artwork": True,
    "columns": ["checked", "title", "duration", "artist", "album", "genre", "rating", "play_count"],
    "podcast_refresh": "hour", "podcast_new": "recent", "podcast_keep": "all",
    "podcast_directory": "apple", "podcastindex_key": "", "podcastindex_secret": "", "podcast_country": "",
    "radio_country": "", "burn_gap": 2, "burn_kind": "audio", "copy_to_media": False,
    "eq_custom": {}, "output": "", "resume": True, "look": "standard", "skin": "", "classic_double": False,
    "classic_eq": True, "classic_pl": True, "classic_ontop": False, "classic_vis": "spectrum", "eq_auto": True, "balance": 0.0, "classic_pos": {}, "classic_shade": False,
}


def data_dir():
    return os.environ.get("FOLIO_CHORD_DATA") or os.path.join(GLib.get_user_data_dir(), "folio-chord")


def config_dir():
    return os.path.join(GLib.get_user_config_dir(), "folio-chord")


def default_country():
    loc = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
    m = loc.split(".")[0].split("_")
    return m[1].lower() if len(m) > 1 and len(m[1]) == 2 else "us"


class Settings(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        self.path = os.path.join(config_dir(), "settings.json")
        try:
            with open(self.path) as f:
                self.update(json.load(f))
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(dict(self), f, indent=1)
        os.replace(tmp, self.path)

    def set(self, k, v):
        self[k] = v
        self.save()


class Playback:
    """What's playing and what comes next, and everything counted along the way."""

    def __init__(self, app):
        self.app = app
        self.lib = app.lib
        self.engine = player.Engine()
        self.queue = playqueue.PlayQueue()
        self.queue.album_of = lambda tid: "" if isinstance(tid, tuple) else (self.lib.track(tid) or {"album": ""})["album"]
        self.queue.skip_shuffle = lambda tid: False if isinstance(tid, tuple) else \
            bool((self.lib.track(tid) or {"skip_shuffle": 0})["skip_shuffle"])
        self.listeners = []
        self.now = None                # the item playing: {"kind": "song"|"episode"|"station", ...}
        self.stream_title = ""
        self.started_at = 0.0
        self.engine.listen(self._engine)
        s = app.settings
        self.engine.set_volume(float(s["volume"]))
        self.engine.set_sound_check(s["sound_check"])
        self.engine.crossfade = float(s["crossfade_secs"]) if s["crossfade"] else 0.0
        self.engine.set_eq(s["eq_on"], s["eq_preamp"], s["eq_bands"])
        self.engine.auto_eq = bool(s.get("eq_auto", True))
        self.engine.set_balance(float(s.get("balance", 0.0)))
        self.queue.shuffle, self.queue.shuffle_by, self.queue.repeat = s["shuffle"], s["shuffle_by"], s["repeat"]
        self.muted_from = None
        self.sleep_at = None
        self.sleep_end_of_item = False
        GLib.timeout_add_seconds(5, self._save_position)

    def listen(self, fn):
        self.listeners.append(fn)

    def _emit(self, ev, val=None):
        for fn in list(self.listeners):
            try:
                fn(ev, val)
            except Exception:
                import traceback
                traceback.print_exc()

    # ---------------------------------------------------------------- items
    def song_item(self, tid):
        r = self.lib.track(tid)
        if r is None:
            return None
        start = r["start_time"] or 0
        if r["remember_position"] and (r["position"] or 0) > 5 and (r["position"] or 0) < (r["duration"] or 0) - 5:
            start = r["position"]       # C3-13: carry on where it was left
        return {"kind": "song", "id": tid, "uri": player.uri_of(r["path"]), "title": r["title"], "artist": r["artist"],
                "album": r["album"], "duration": r["duration"], "rg": r["rg_track"], "start": start,
                "stop": r["stop_time"] or 0, "volume_adjust": r["volume_adjust"] or 0, "path": r["path"],
                "eq": r["eq"] or ""}

    def episode_item(self, eid):
        e = self.app.pods.episode(eid)
        if e is None:
            return None
        p = self.app.pods.show(e["podcast"])
        uri = player.uri_of(e["file"]) if e["file"] and os.path.exists(e["file"]) else e["url"]
        return {"kind": "episode", "id": eid, "uri": uri, "title": e["title"], "artist": p["title"] if p else "",
                "album": p["author"] if p else "", "duration": e["duration"], "rg": None,
                "start": e["position"] if e["position"] and e["position"] > 5 else 0, "stop": 0,
                "stream": not uri.startswith("file:"), "artwork": p["artwork"] if p else ""}

    def station_item(self, st):
        return {"kind": "station", "id": st["uuid"], "uri": st["url"], "title": st["name"], "artist": "",
                "album": ", ".join(st.get("tags", [])[:3]), "duration": 0, "rg": None, "stream": True, "station": st}

    # ---------------------------------------------------------------- playing
    def play_songs(self, ids, index=0):
        ids = list(ids)
        if not ids:
            return
        # unchecked songs are skipped when playing through a list, as in iTunes
        chk = {r["id"]: r["checked"] for r in self.lib.q("select id, checked from tracks where id in (%s)" % ",".join("?" * len(ids)), ids)}
        first = ids[index]
        ids = [t for t in ids if chk.get(t, 1) or t == first]
        self.queue.start(ids, ids.index(first))
        self._start(self.song_item(first))

    def play_episodes(self, eids, index=0):
        self.queue.start([("e", e) for e in eids], index)
        self._start(self.episode_item(eids[index]))

    def play_station(self, st):
        if radio.looks_like_playlist(st.get("url", "")):
            radio.played(self.lib, st)
            return self.play_uri(st["url"], st.get("name"))
        self.queue.start([], 0)
        radio.played(self.lib, st)
        self._start(self.station_item(st))
        from . import net
        net.in_thread(lambda: self.app.radio.clicked(st))

    def play_uri(self, uri, name=None):
        """Play an internet stream; a station playlist (.pls, .m3u, .asx) is opened for its stream (C3-17)."""
        self.queue.start([], 0)
        st = radio.custom_station(name or uri, uri)

        def go(real):
            item = self.station_item(st)
            item["uri"] = real
            self._start(item)
        if radio.looks_like_playlist(uri):
            from . import net
            net.in_thread(lambda: radio.resolve(uri), go, lambda e: self._emit("error", "“%s” couldn't be opened: %s" % (uri, e)))
        else:
            go(uri)

    def _item_for(self, key):
        if isinstance(key, tuple) and key[0] == "e":
            return self.episode_item(key[1])
        return self.song_item(key)

    def _next_item(self):
        k = self.queue.advance()
        return self._item_for(k) if k is not None else None

    def _start(self, item):
        if item is None:
            return
        self.stream_title = ""
        self.engine.rate = self.rate_for(item)
        self.engine.play(item, self._next_item)

    # ---------------------------------------------------------------- C3-15: speed, skips, sleep timer
    SPEEDS = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)

    def rate_for(self, item):
        if item and item.get("kind") == "episode":
            e = self.app.pods.episode(item["id"])
            p = self.app.pods.show(e["podcast"]) if e else None
            return float(p["speed"] or 1.0) if p else 1.0
        return 1.0

    def set_speed(self, rate):
        n = self.now
        if n and n.get("kind") == "episode":
            e = self.app.pods.episode(n["id"])
            if e:
                self.app.pods.set_speed(e["podcast"], rate)
        self.engine.set_rate(rate if n and n.get("kind") == "episode" else 1.0)
        self._emit("speed", self.engine.rate)

    def skip(self, secs):
        if self.engine.state == "stopped" or (self.now or {}).get("stream") and not (self.now or {}).get("duration"):
            return
        pos = self.engine.position() + secs
        dur = self.engine.duration()
        self.engine.seek(max(0.0, min(pos, dur - 1 if dur else pos)))

    def sleep_in(self, minutes):
        """Stop after this many minutes; 0 cancels; -1 stops at the end of the current song or episode."""
        if getattr(self, "_sleep", None):
            GLib.source_remove(self._sleep)
        self._sleep = None
        self.sleep_at = None
        self.sleep_end_of_item = minutes == -1
        if minutes and minutes > 0:
            self.sleep_at = time.time() + minutes * 60
            self._sleep = GLib.timeout_add_seconds(int(minutes * 60), self._sleep_now)
        self._emit("sleep", minutes)

    def _sleep_now(self):
        self._sleep = None
        self.sleep_at = None
        self.stop()
        self._emit("sleep", 0)
        return False

    def toggle(self):
        if self.engine.state in ("playing", "paused"):
            if self.now and self.now["kind"] == "station" and self.engine.state == "playing":
                self.engine.stop()      # a station stops rather than pausing, as iTunes does
                self.engine.state = "stopped"
                self._emit("state", "stopped")
                return
            self.engine.toggle()
        elif self.now and self.now["kind"] == "station":
            self._start(self.now)
        elif self.queue.current is not None:
            self._start(self._item_for(self.queue.current))
        else:
            self._emit("play-selection")

    def next(self):
        if self.now and self.now.get("kind") == "song" and self.engine.state == "playing":
            pos = self.engine.position()
            if 2 <= pos <= 20:
                self.lib.skipped(self.now["id"])
        k = self.queue.advance(user=True)
        if k is None:
            self.engine.stop()
            self.now = None
            self._emit("track", None)
            return
        self._start(self._item_for(k))

    def previous(self):
        if self.engine.state != "stopped" and self.engine.position() > 3:
            self.engine.seek(0)
            return
        k = self.queue.back()
        if k is not None:
            self._start(self._item_for(k))

    def stop(self):
        self._save_position()
        self.engine.stop()

    def set_volume(self, v):
        self.engine.set_volume(v)
        self.app.settings["volume"] = v
        self._emit("volume", v)

    def mute(self):
        if self.muted_from is None:
            self.muted_from = self.engine.volume
            self.set_volume(0)
        else:
            v, self.muted_from = self.muted_from, None
            self.set_volume(v)

    def set_shuffle(self, on, by=None):
        self.queue.set_shuffle(on, by)
        self.app.settings.set("shuffle", bool(on))
        if by:
            self.app.settings.set("shuffle_by", by)
        self._emit("modes")

    def set_repeat(self, mode):
        self.queue.set_repeat(mode)
        self.app.settings.set("repeat", mode)
        self._emit("modes")

    # ---------------------------------------------------------------- engine events
    def _engine(self, ev, val):
        if ev == "track":
            self.now = val
            self.started_at = time.time()
            self.stream_title = ""
        elif ev == "eos" and val:
            if getattr(self, "sleep_end_of_item", False):
                self.sleep_end_of_item = False
                GLib.idle_add(lambda: (self.stop(), self._emit("sleep", 0), False)[2])
            if val.get("kind") == "song":
                self.lib.played(val["id"])
            elif val.get("kind") == "episode":
                self.app.pods.mark_played([val["id"]])
        elif ev == "tags":
            t = val.get("title") or ""
            if self.now and self.now.get("kind") == "station" and t and t != self.now.get("title"):
                self.stream_title = t
        elif ev == "error" and val:
            item, msg = val
            self._emit("error", "“%s” couldn't be played: %s" % ((item or {}).get("title", ""), msg))
            if item and item.get("kind") == "song" and self.queue.order:
                GLib.timeout_add(300, lambda: (self.next(), False)[1])
            return
        self._emit(ev, val)

    # ---------------------------------------------------------------- C3-18: carry on where you left off
    def session(self):
        q = self.queue
        enc = lambda k: ["e", k[1]] if isinstance(k, tuple) else k  # noqa: E731
        n = self.now
        now = None
        if n:
            now = {"kind": n["kind"], "id": n["id"]}
            if n["kind"] == "station":
                now["station"] = n.get("station")
                now["uri"] = n.get("uri")
        return {"source": [enc(k) for k in q.source], "order": q.order, "pos": q.pos, "up_next": [enc(k) for k in q.up_next],
                "current": enc(q.current) if q.current is not None else None, "now": now,
                "position": self.engine.position() if self.engine.state in ("playing", "paused") else 0.0}

    def save_session(self):
        try:
            self.lib.put("session", json.dumps(self.session()))
        except Exception:       # noqa: BLE001
            pass

    def restore_session(self):
        try:
            d = json.loads(self.lib.get("session") or "null")
        except ValueError:
            d = None
        if not d or not d.get("now"):
            return False
        dec = lambda k: ("e", k[1]) if isinstance(k, list) else k  # noqa: E731
        q = self.queue
        q.source = [dec(k) for k in d.get("source", [])]
        q.order = d.get("order") or list(range(len(q.source)))
        q.pos = d.get("pos", -1)
        q.up_next = [dec(k) for k in d.get("up_next", [])]
        q.current = dec(d["current"]) if d.get("current") is not None else None
        n = d["now"]
        if n["kind"] == "station" and n.get("station"):
            item = self.station_item(n["station"])
            item["uri"] = n.get("uri") or item["uri"]
            self.now = item
            self._emit("track", item)
            self._emit("state", "stopped")
            return True
        item = self._item_for(("e", n["id"]) if n["kind"] == "episode" else n["id"])
        if item is None:
            return False
        item["start"] = float(d.get("position") or 0)
        item["_paused"] = True
        self._start(item)
        return True

    def _save_position(self):
        n = self.now
        if n and n.get("kind") == "episode" and self.engine.state in ("playing", "paused"):
            pos = self.engine.position()
            if pos > 5:
                self.app.pods.set(n["id"], position=pos, new=0)
        elif n and n.get("kind") == "song" and self.engine.state in ("playing", "paused"):
            r = self.lib.track(n["id"])
            if r and r["remember_position"]:
                with self.lib.lock:
                    self.lib.db.execute("update tracks set position=? where id=?", (self.engine.position(), n["id"]))
                    self.lib.db.commit()
        self.save_session()
        return True


class ChordApp(Gtk.Application):
    def __init__(self):
        flags = Gio.ApplicationFlags.HANDLES_OPEN
        if os.environ.get("FOLIO_CHORD_NON_UNIQUE"):
            flags |= Gio.ApplicationFlags.NON_UNIQUE
        super().__init__(application_id=APP_ID, flags=flags)
        GLib.set_application_name(APP_NAME)
        GLib.set_prgname(APP_ID)
        self.win = None
        self.pending_open = []

    def do_startup(self):
        Gtk.Application.do_startup(self)
        appearance.apply_initial()
        fontfix.install()
        self.settings = Settings()
        os.makedirs(data_dir(), exist_ok=True)
        self.lib = library.Library(os.path.join(data_dir(), "library.db"))
        if self.settings["music_folders"] is None:
            music = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_MUSIC) or os.path.expanduser("~/Music")
            self.settings["music_folders"] = [music]
            self.settings.save()
        for f in self.settings["music_folders"]:
            if os.path.isdir(f):
                self.lib.add_folder(f)
        self.pods = podcasts.Podcasts(self.lib, os.path.join(self.media_folder(), "Podcasts"))
        self.radio = radio.Directory()
        self.playback = Playback(self)
        self.playback.engine.preset_lookup = self.eq_preset
        if self.settings.get("output"):
            for name, dev in player.Engine.devices():
                if name == self.settings["output"]:
                    self.playback.engine.output = dev
                    for p in (self.playback.engine.a, self.playback.engine.b):
                        p.pb.set_property("audio-sink", self.playback.engine.make_sink())
        from . import analysis
        self.analyser = analysis.Analyser(self.lib)
        if self.settings["sound_check"] and not os.environ.get("FOLIO_CHORD_NO_SCAN"):
            self.analyser.start()
        icons = os.environ.get("FOLIO_CHORD_SHARE") or os.path.join(os.path.dirname(__file__), "..", "..", "share")
        for d in (icons, "/usr/share/folio-chord"):
            p = os.path.join(d, "icons")
            if os.path.isdir(p):
                Gtk.IconTheme.get_default().append_search_path(p)
        self._css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), self._css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5)
        self.apply_theme(appearance.is_dark())
        appearance.on_change(self.apply_theme)

        def own(w, *a):
            ctx = w.get_style_context()
            if isinstance(w, Gtk.Window) and not ctx.has_class("chord-own"):
                if w.get_window_type() == Gtk.WindowType.POPUP:
                    return True
                ctx.add_class("chord-dialog")
            return True
        GObject.add_emission_hook(Gtk.Window, "realize", own)
        from . import mpris
        self.mpris = mpris.Mpris(self)

    def eq_preset(self, name):
        """A preset by name: iTunes' own, or one made with Make Preset (C3-25)."""
        c = self.settings.get("eq_custom") or {}
        if name in c:
            return tuple(c[name])
        return player.PRESETS.get(name)

    def eq_presets(self):
        return sorted(player.PRESETS) + sorted(n for n in (self.settings.get("eq_custom") or {}) if n not in player.PRESETS)

    def apply_theme(self, dark):
        self._css.load_from_data(theme.css(dark).encode())
        if self.win is not None:
            self.win.queue_draw()

    def media_folder(self):
        return self.settings.get("media_folder") or GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_MUSIC) \
            or os.path.expanduser("~/Music")

    def do_activate(self):
        if self.win is None:
            from .window import Window
            self.win = Window(self)
            self.win.show_all()
            self.win.after_show()
            self._test_hook()
        self.win.present()

    def do_open(self, files, n, hint):
        self.do_activate()
        paths = [f.get_path() for f in files if f.get_path()]
        uris = [f.get_uri() for f in files if not f.get_path()]
        if paths:
            self.win.add_paths(paths, play=True)
        for u in uris:
            self.playback.play_uri(u)

    def _test_hook(self):
        script = os.environ.get("FOLIO_TEST_SCRIPT")
        if not script:
            return

        def run():
            ns = {"app": self, "win": self.win, "GLib": GLib, "Gtk": Gtk, "Gdk": Gdk}
            try:
                with open(script) as f:
                    exec(compile(f.read(), script, "exec"), ns)
            except SystemExit:
                raise
            except Exception:
                import traceback
                traceback.print_exc()
                sys.stdout.flush()
                os._exit(3)
            return False
        GLib.timeout_add(int(os.environ.get("FOLIO_TEST_DELAY", "1500")), run)

    def do_shutdown(self):
        try:
            self.playback.save_session()
            self.playback.stop()
            self.settings.save()
        except Exception:
            pass
        Gtk.Application.do_shutdown(self)


def main(argv):
    if len(argv) > 1 and argv[1] in ("--version", "-v"):
        print("%s %s" % (APP_NAME, VERSION))
        return 0
    app = ChordApp()
    return app.run(argv)
