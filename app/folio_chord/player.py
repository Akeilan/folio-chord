"""Playback (C3-02) through GStreamer: gapless from one song to the next, crossfading when asked,
the 10-band equalizer (iTunes' bands), Sound Check from each song's ReplayGain, per-song volume
adjustment and start/stop times, internet radio streams with their song titles, and a spectrum
for the visualizer.

  e = Engine(); e.listen(fn)        fn(event, value): "state" (playing|paused|stopped),
                                    "track" (item), "tags" ({"title", "artist", ...} from a stream),
                                    "eos" (item), "error" (message), "spectrum" ([dB per band])
  e.play(item, next_item_fn)        item = {"uri", "gain_db", "start", "stop", ...}
"""
import math
import os

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstAudio", "1.0")
from gi.repository import GLib, Gst, GstAudio  # noqa: E402

Gst.init(None)

BANDS = [32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]   # what the equalizer shows
# iTunes' presets: preamp, then the ten bands, in dB
PRESETS = {
    "Acoustic": (0, [5, 4.9, 4, 1, 1.5, 1.5, 3.5, 4, 3.5, 2]),
    "Bass Booster": (0, [5.5, 4.3, 3.5, 2.5, 1.3, 0, 0, 0, 0, 0]),
    "Bass Reducer": (0, [-5.5, -4.3, -3.5, -2.5, -1.3, 0, 0, 0, 0, 0]),
    "Classical": (0, [4.8, 3.8, 3, 2.5, -1.5, -1.5, 0, 2.3, 3.3, 3.8]),
    "Dance": (0, [3.6, 6.6, 5, 0, 2, 3.5, 5, 4.5, 3.5, 0]),
    "Deep": (0, [5, 3.5, 1.8, 1, 3, 2.5, 1.5, -2, -3.5, -4.5]),
    "Electronic": (0, [4.3, 3.8, 1.3, 0, -2, 2.3, 1, 1.3, 4, 4.8]),
    "Flat": (0, [0] * 10),
    "Hip-Hop": (0, [5, 4.3, 1.5, 3, -1, -1, 1.5, -0.5, 2, 3]),
    "Jazz": (0, [4, 3, 1.5, 2.3, -1.5, -1.5, 0, 1.5, 3, 3.8]),
    "Latin": (0, [4.5, 3, 0, 0, -1.5, -1.5, -1.5, 0, 3, 4.5]),
    "Loudness": (0, [6, 4, 0, 0, -2, 0, -1, -5, 5, 1]),
    "Lounge": (0, [-3, -1.5, -0.5, 1.5, 4, 2.5, 0, -1.5, 2, 1]),
    "Piano": (0, [3, 2, 0, 2.5, 3, 1.5, 3.5, 4.5, 3, 3.5]),
    "Pop": (0, [-1.5, -1, 0, 2, 4, 4, 2, 0, -1, -1.5]),
    "R&B": (0, [2.6, 7, 5.7, 1.3, -2.2, -1.5, 2.3, 2.7, 3, 3.8]),
    "Rock": (0, [5, 4, 3, 1.5, -0.5, -1, 0.5, 2.5, 3.5, 4.5]),
    "Small Speakers": (0, [5.5, 4.3, 3.5, 2.5, 1.3, 0, -1.3, -2.5, -3.5, -4.3]),
    "Spoken Word": (0, [-3.5, -0.5, 0, 0.7, 3.5, 4.6, 4.8, 4.3, 2.5, 0]),
    "Treble Booster": (0, [0, 0, 0, 0, 0, 1.3, 2.5, 3.5, 4.3, 5.5]),
    "Treble Reducer": (0, [0, 0, 0, 0, 0, -1.3, -2.5, -3.5, -4.3, -5.5]),
    "Vocal Booster": (0, [-1.5, -3, -3, 1.5, 3.5, 3.5, 3, 1.5, 0, -1.5]),
}


def uri_of(path_or_uri):
    if "://" in path_or_uri:
        return path_or_uri
    return Gst.filename_to_uri(os.path.abspath(path_or_uri))


class _Pipe:
    """One playbin with Folio Chord's filters: gain (Sound Check, volume adjust, preamp),
    the equalizer and a spectrum."""

    def __init__(self, engine, name):
        self.engine = engine
        self.item = None
        self.pb = Gst.ElementFactory.make("playbin", name)
        self.pb.set_property("audio-sink", engine.make_sink())
        self.pb.set_property("video-sink", Gst.ElementFactory.make("fakesink"))
        flags = self.pb.get_property("flags")
        self.pb.set_property("flags", flags & ~0x1 & ~0x4)   # no video, no subtitles
        f = Gst.Bin.new("chord-filter")
        # scaletempo keeps voices at their pitch when podcasts play faster or slower (C3-15)
        self.tempo = Gst.ElementFactory.make("scaletempo")
        conv = Gst.ElementFactory.make("audioconvert")
        self.gain = Gst.ElementFactory.make("volume")
        self.eq = Gst.ElementFactory.make("equalizer-10bands")
        self.pan = Gst.ElementFactory.make("audiopanorama")      # balance (Chordamp, C3-28)
        conv2 = Gst.ElementFactory.make("audioconvert")
        self.spec = Gst.ElementFactory.make("spectrum")
        self.spec.set_property("bands", 256)
        self.spec.set_property("threshold", -70)
        self.spec.set_property("interval", 50 * Gst.MSECOND)
        self.spec.set_property("post-messages", False)
        for e in (conv, self.gain, self.eq, conv2, self.spec):
            f.add(e)
        first = conv
        if self.tempo is not None:
            pre = Gst.ElementFactory.make("audioconvert")
            f.add(self.tempo)
            f.add(pre)
            pre.link(self.tempo)
            self.tempo.link(conv)
            first = pre
        conv.link(self.gain)
        if self.pan is not None:
            f.add(self.pan)
            self.pan.set_property("method", 1)      # simple: the far side is turned down, not mixed in
            self.gain.link(self.pan)
            self.pan.link(self.eq)
        else:
            self.gain.link(self.eq)
        self.eq.link(conv2)
        conv2.link(self.spec)
        f.add_pad(Gst.GhostPad.new("sink", first.get_static_pad("sink")))
        f.add_pad(Gst.GhostPad.new("src", self.spec.get_static_pad("src")))
        self.pb.set_property("audio-filter", f)
        self.pb.connect("about-to-finish", self._about_to_finish)
        bus = self.pb.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._message)
        self.pending = None      # the next item set for gapless playback
        self.fade = 1.0

    def set_item(self, item):
        self.item = item
        self.pb.set_property("uri", item["uri"])

    def _about_to_finish(self, pb):
        # called from a streaming thread: hand the next song to playbin straight away (gapless)
        e = self.engine
        if e.crossfade > 0 and not (self.item or {}).get("stream"):
            return
        nxt = e.next_fn() if e.next_fn else None
        if nxt:
            self.pending = nxt
            pb.set_property("uri", nxt["uri"])

    def _message(self, bus, msg):
        self.engine._message(self, msg)


class Engine:
    def __init__(self):
        self.listeners = []
        self.volume = 1.0
        self.eq_on = False
        self.eq = (0, [0] * 10)
        self.sound_check = False
        self.crossfade = 0.0        # seconds; 0 = gapless
        self.next_fn = None
        self.rate = 1.0
        self.balance = 0.0          # -1 left .. 1 right
        self.auto_eq = True         # songs' own presets (Get Info) are used; Chordamp's AUTO
        self.output = None          # a Gst.Device, or None for the desktop's choice (C3-24)
        self.preset_lookup = lambda name: PRESETS.get(name)     # per-song presets, the app's own too (C3-13, C3-25)
        self.a = _Pipe(self, "chord-a")
        self.b = _Pipe(self, "chord-b")
        self.cur = self.a
        self.state = "stopped"
        self.spectrum_on = False
        self._fading = None
        GLib.timeout_add(100, self._tick)

    # ---------------------------------------------------------------- output (C3-24)
    def make_sink(self):
        name = os.environ.get("FOLIO_CHORD_AUDIOSINK", "autoaudiosink")
        if self.output is not None and not name.startswith("fakesink"):
            try:
                el = self.output.create_element(None)
                if el is not None:
                    return el
            except Exception:       # noqa: BLE001
                pass
        sink = Gst.parse_bin_from_description(name, True) if " " in name else Gst.ElementFactory.make(name)
        if name.startswith("fakesink"):
            sink.set_property("sync", True)
        return sink

    @staticmethod
    def devices():
        """The sound outputs on this computer: [(name, Gst.Device)]."""
        mon = Gst.DeviceMonitor.new()
        mon.add_filter("Audio/Sink", None)
        try:
            mon.start()
            devs = mon.get_devices() or []
        finally:
            mon.stop()
        out = []
        for d in devs:
            out.append((d.get_display_name(), d))
        return out

    def set_output(self, device):
        """Play through this output (None: the desktop's choice), carrying on where it was."""
        self.output = device
        item, pos, st = self.cur.item, self.position(), self.state
        for p in (self.a, self.b):
            p.pb.set_state(Gst.State.NULL)
            p.pb.set_property("audio-sink", self.make_sink())
        if item is not None and st in ("playing", "paused"):
            item = dict(item, start=pos, _started=False)
            self.play(item)
            if st == "paused":
                GLib.timeout_add(300, lambda: (self.pause(), False)[1])

    # ---------------------------------------------------------------- speed (C3-15)
    def set_rate(self, rate):
        self.rate = max(0.5, min(3.0, float(rate)))
        self._seek_rate(self.cur)

    def _seek_rate(self, pipe):
        if self.state == "stopped":
            return
        ok, pos = pipe.pb.query_position(Gst.Format.TIME)
        if not ok or pos < 0:
            pos = 0
        pipe.pb.seek(self.rate, Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
                     Gst.SeekType.SET, pos, Gst.SeekType.NONE, -1)

    # ---------------------------------------------------------------- events
    def listen(self, fn):
        self.listeners.append(fn)

    def _emit(self, ev, val=None):
        for fn in list(self.listeners):
            try:
                fn(ev, val)
            except Exception:
                import traceback
                traceback.print_exc()

    def _message(self, pipe, msg):
        t = msg.type
        if t == Gst.MessageType.STREAM_START and pipe is self.cur:
            if pipe.pending is not None:
                old = pipe.item
                pipe.item = pipe.pending
                pipe.pending = None
                self._apply_gain(pipe)
                self._emit("eos", old)
                self._emit("track", pipe.item)
                self._start_at(pipe)
        elif t == Gst.MessageType.EOS:
            if pipe is self.cur:
                old = pipe.item
                pipe.pb.set_state(Gst.State.NULL)
                self.state = "stopped"
                self._emit("eos", old)
                nxt = self.next_fn() if self.next_fn else None
                if nxt:
                    self.play(nxt)
                else:
                    self._emit("state", "stopped")
            else:
                pipe.pb.set_state(Gst.State.NULL)
        elif t == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            if pipe is self.cur:
                pipe.pb.set_state(Gst.State.NULL)
                self.state = "stopped"
                self._emit("error", (pipe.item, err.message))
        elif t == Gst.MessageType.TAG and pipe is self.cur:
            tl = msg.parse_tag()
            got = {}
            for k, name in (("title", Gst.TAG_TITLE), ("artist", Gst.TAG_ARTIST), ("album", Gst.TAG_ALBUM),
                            ("organization", Gst.TAG_ORGANIZATION), ("genre", Gst.TAG_GENRE)):
                ok, v = tl.get_string(name)
                if ok and v:
                    got[k] = v
            ok, br = tl.get_uint(Gst.TAG_BITRATE)
            if ok:
                got["bitrate"] = br
            if got:
                self._emit("tags", got)
        elif t == Gst.MessageType.ELEMENT and pipe is self.cur:
            s = msg.get_structure()
            if s and s.get_name() == "spectrum":
                # PyGObject can't read the value list itself: take it from the text form
                txt = s.to_string()
                i = txt.find("magnitude=")
                if i >= 0:
                    a, b = txt.find("{", i), txt.find("}", i)
                    try:
                        mags = [float(x) for x in txt[a + 1:b].replace("(float)", "").split(",") if x.strip()]
                    except ValueError:
                        mags = []
                    if mags:
                        self._emit("spectrum", mags)
        elif t == Gst.MessageType.STATE_CHANGED and msg.src is pipe.pb and pipe is self.cur:
            old, new, _p = msg.parse_state_changed()
            st = {Gst.State.PLAYING: "playing", Gst.State.PAUSED: "paused"}.get(new)
            if st and st != self.state and not (st == "paused" and (self.state == "loading" or getattr(pipe, "buffering", False))):
                self.state = st
                self._emit("state", st)
            if new == Gst.State.PAUSED and old == Gst.State.READY:
                self._start_at(pipe)
                if (pipe.item or {}).get("_paused") and self.state == "loading":
                    pipe.item["_paused"] = False
                    self.state = "paused"
                    self._emit("state", "paused")
        elif t == Gst.MessageType.BUFFERING and pipe is self.cur:
            pct = msg.parse_buffering()
            # a network stream waits while it fills up, then carries on
            if (pipe.item or {}).get("stream") and self.state in ("playing", "loading", "buffering"):
                if pct < 100:
                    pipe.pb.set_state(Gst.State.PAUSED)
                    pipe.buffering = True
                elif getattr(pipe, "buffering", False):
                    pipe.buffering = False
                    pipe.pb.set_state(Gst.State.PLAYING)
            self._emit("buffering", pct)

    # ---------------------------------------------------------------- controls
    def play(self, item, next_fn=None):
        if next_fn is not None:
            self.next_fn = next_fn
        self._cancel_fade()
        for p in (self.a, self.b):
            p.pb.set_state(Gst.State.NULL)
            p.pending = None
            p.fade = 1.0
        self.cur = self.a
        self.cur.set_item(item)
        self._apply_gain(self.cur)
        self._apply_eq()
        self.state = "loading"
        # a song brought back from last time waits, paused, at its place (C3-18)
        self.cur.pb.set_state(Gst.State.PAUSED if item.get("_paused") else Gst.State.PLAYING)
        self._emit("track", item)

    def _start_at(self, pipe):
        if self.rate != 1.0 and not (pipe.item or {}).get("stream") and not (pipe.item or {}).get("_rated"):
            pipe.item["_rated"] = True
            st0 = float(pipe.item.get("start") or 0)
            pipe.item["_started"] = True
            GLib.idle_add(lambda: (pipe.pb.seek(self.rate, Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
                                                Gst.SeekType.SET, int(st0 * Gst.SECOND), Gst.SeekType.NONE, -1), False)[1])
            return
        st = float((pipe.item or {}).get("start") or 0)
        if st > 0 and not pipe.item.get("_started"):
            pipe.item["_started"] = True
            GLib.idle_add(lambda: (pipe.pb.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                                                       int(st * Gst.SECOND)), False)[1])

    def pause(self):
        if self.state == "playing":
            self.cur.pb.set_state(Gst.State.PAUSED)
            self.state = "paused"
            self._emit("state", "paused")

    def resume(self):
        if self.state in ("paused",):
            self.cur.pb.set_state(Gst.State.PLAYING)
            self.state = "playing"
            self._emit("state", "playing")

    def toggle(self):
        if self.state == "playing":
            self.pause()
        elif self.state == "paused":
            self.resume()

    def stop(self):
        self._cancel_fade()
        for p in (self.a, self.b):
            p.pb.set_state(Gst.State.NULL)
            p.pending = None
        self.state = "stopped"
        self._emit("state", "stopped")

    @property
    def item(self):
        return self.cur.item if self.state != "stopped" else None

    def position(self):
        ok, pos = self.cur.pb.query_position(Gst.Format.TIME)
        return pos / Gst.SECOND if ok and pos >= 0 else 0.0

    def duration(self):
        ok, d = self.cur.pb.query_duration(Gst.Format.TIME)
        if ok and d > 0:
            return d / Gst.SECOND
        return float((self.cur.item or {}).get("duration") or 0)

    def seek(self, secs):
        t = int(max(0, secs) * Gst.SECOND)
        if self.rate != 1.0:        # keep the speed (a plain seek would set it back to 1x)
            self.cur.pb.seek(self.rate, Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                             Gst.SeekType.SET, t, Gst.SeekType.NONE, -1)
        else:
            self.cur.pb.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, t)

    def set_volume(self, v):
        self.volume = max(0.0, min(1.0, v))
        for p in (self.a, self.b):
            self._apply_volume(p)

    def set_balance(self, b):
        self.balance = max(-1.0, min(1.0, float(b)))
        for p in (self.a, self.b):
            if p.pan is not None:
                p.pan.set_property("panorama", self.balance)

    def _apply_volume(self, p):
        lin = GstAudio.stream_volume_convert_volume(GstAudio.StreamVolumeFormat.CUBIC,
                                                    GstAudio.StreamVolumeFormat.LINEAR, self.volume)
        p.pb.set_property("volume", lin * p.fade)

    def set_eq(self, on, preamp=None, bands=None):
        self.eq_on = bool(on)
        if preamp is not None or bands is not None:
            pa, bs = self.eq
            self.eq = (pa if preamp is None else float(preamp), list(bs if bands is None else bands))
        self._apply_eq()
        for p in (self.a, self.b):
            self._apply_gain(p)

    def eq_for(self, item):
        """(on, preamp, bands) for a song: its own preset from Get Info, else the Equalizer's."""
        name = (item or {}).get("eq")
        if name and self.auto_eq:
            pr = self.preset_lookup(name)
            if pr:
                return True, float(pr[0]), list(pr[1])
        return self.eq_on, float(self.eq[0]), list(self.eq[1])

    def _apply_eq(self):
        for p in (self.a, self.b):
            self._apply_eq_pipe(p)

    def _apply_eq_pipe(self, p):
        on, _pa, bands = self.eq_for(p.item)
        for i in range(10):
            p.eq.set_property("band%d" % i, float(bands[i]) if on else 0.0)

    def set_sound_check(self, on):
        self.sound_check = bool(on)
        for p in (self.a, self.b):
            self._apply_gain(p)

    def gain_db(self, item):
        g = 0.0
        if item:
            if self.sound_check and item.get("rg") is not None:
                g += float(item["rg"])
            g += float(item.get("volume_adjust") or 0) * 0.12    # -100..100 % → about ±12 dB
        on, pa, _b = self.eq_for(item)
        if on:
            g += pa
        return g

    def _apply_gain(self, p):
        self._apply_eq_pipe(p)
        db = self.gain_db(p.item)
        p.gain.set_property("volume", min(10.0, math.pow(10, db / 20.0)))
        self._apply_volume(p)

    def set_spectrum(self, on):
        self.spectrum_on = bool(on)
        for p in (self.a, self.b):
            p.spec.set_property("post-messages", self.spectrum_on)

    # ---------------------------------------------------------------- crossfade and stop times
    def _tick(self):
        p = self.cur
        it = p.item
        if self.state == "playing" and it and not it.get("stream"):
            pos = self.position()
            dur = self.duration()
            stop = float(it.get("stop") or 0)
            if stop > 0 and pos >= stop and not self._fading:
                p.pb.set_state(Gst.State.NULL)
                self.state = "stopped"
                self._emit("eos", it)
                nxt = self.next_fn() if self.next_fn else None
                if nxt:
                    self.play(nxt)
                else:
                    self._emit("state", "stopped")
                return True
            if self.crossfade > 0 and dur > self.crossfade * 2 and pos >= dur - self.crossfade and not self._fading:
                nxt = self.next_fn() if self.next_fn else None
                if nxt:
                    self._begin_fade(nxt)
        if self._fading:
            old, new, t0 = self._fading
            k = min(1.0, (GLib.get_monotonic_time() / 1e6 - t0) / max(0.1, self.crossfade))
            old.fade, new.fade = 1.0 - k, k
            self._apply_volume(old)
            self._apply_volume(new)
            if k >= 1.0:
                old.pb.set_state(Gst.State.NULL)
                self._fading = None
        return True

    def _begin_fade(self, nxt):
        old = self.cur
        new = self.b if old is self.a else self.a
        new.pb.set_state(Gst.State.NULL)
        new.set_item(nxt)
        new.fade = 0.0
        self._apply_gain(new)
        new.pb.set_state(Gst.State.PLAYING)
        self.cur = new
        self._fading = (old, new, GLib.get_monotonic_time() / 1e6)
        self._emit("eos", old.item)
        self._emit("track", nxt)

    def _cancel_fade(self):
        if self._fading:
            old, new, _t = self._fading
            old.pb.set_state(Gst.State.NULL)
            new.fade = 1.0
            self._apply_volume(new)
            self._fading = None
