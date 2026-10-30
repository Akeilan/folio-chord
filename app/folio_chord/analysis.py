"""Sound Check for every song (C3-16): the loudness of songs that carry no ReplayGain tags is
measured in the background (GStreamer's ReplayGain analysis, the same measure the tags use) and
kept in the library, as iTunes measured songs for Sound Check."""
import threading

import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst  # noqa: E402

Gst.init(None)


def measure(path, timeout=600):
    """The ReplayGain track gain of a file in dB, or None."""
    pipe = Gst.parse_launch("uridecodebin name=d ! audioconvert ! audioresample ! rganalysis name=rg ! fakesink sync=false")
    pipe.get_by_name("d").set_property("uri", Gst.filename_to_uri(path))
    pipe.set_state(Gst.State.PLAYING)
    bus = pipe.get_bus()
    gain = None
    while True:
        m = bus.timed_pop_filtered(timeout * Gst.SECOND, Gst.MessageType.TAG | Gst.MessageType.EOS | Gst.MessageType.ERROR)
        if m is None or m.type != Gst.MessageType.TAG:
            break
        ok, g = m.parse_tag().get_double(Gst.TAG_TRACK_GAIN)
        if ok:
            gain = g
    pipe.set_state(Gst.State.NULL)
    return gain


class Analyser:
    """Works through the songs without a gain, one at a time, while Sound Check is on."""

    def __init__(self, lib, done=None):
        self.lib = lib
        self.done = done
        self.running = False
        self.stop = False
        self.count = 0

    def start(self):
        if self.running:
            return
        self.running = True
        self.stop = False
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            while not self.stop:
                rows = self.lib.q("select id, path from tracks where rg_track is null and not missing "
                                  "and coalesce(rg_measured,0)=0 limit 20")
                if not rows:
                    break
                for r in rows:
                    if self.stop:
                        break
                    try:
                        g = measure(r["path"])
                    except Exception:       # noqa: BLE001
                        g = None
                    with self.lib.lock:
                        self.lib.db.execute("update tracks set rg_track=?, rg_measured=1 where id=?", (g, r["id"]))
                        self.lib.db.commit()
                    self.count += 1
        finally:
            self.running = False
            if self.done:
                GLib.idle_add(lambda: (self.done(self.count), False)[1])
