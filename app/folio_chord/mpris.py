"""The desktop's player controls and media keys (C3-02): MPRIS on the session bus
(org.mpris.MediaPlayer2.folio_chord)."""
from gi.repository import Gio, GLib

from . import APP_NAME

XML = """
<node>
  <interface name="org.mpris.MediaPlayer2">
    <method name="Raise"/><method name="Quit"/>
    <property name="CanQuit" type="b" access="read"/><property name="CanRaise" type="b" access="read"/>
    <property name="HasTrackList" type="b" access="read"/><property name="Identity" type="s" access="read"/>
    <property name="DesktopEntry" type="s" access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/><property name="SupportedMimeTypes" type="as" access="read"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Next"/><method name="Previous"/><method name="Pause"/><method name="PlayPause"/>
    <method name="Stop"/><method name="Play"/>
    <method name="Seek"><arg direction="in" name="Offset" type="x"/></method>
    <method name="SetPosition"><arg direction="in" name="TrackId" type="o"/><arg direction="in" name="Position" type="x"/></method>
    <method name="OpenUri"><arg direction="in" name="Uri" type="s"/></method>
    <signal name="Seeked"><arg name="Position" type="x"/></signal>
    <property name="PlaybackStatus" type="s" access="read"/><property name="LoopStatus" type="s" access="readwrite"/>
    <property name="Rate" type="d" access="readwrite"/><property name="Shuffle" type="b" access="readwrite"/>
    <property name="Metadata" type="a{sv}" access="read"/><property name="Volume" type="d" access="readwrite"/>
    <property name="Position" type="x" access="read"/><property name="MinimumRate" type="d" access="read"/>
    <property name="MaximumRate" type="d" access="read"/><property name="CanGoNext" type="b" access="read"/>
    <property name="CanGoPrevious" type="b" access="read"/><property name="CanPlay" type="b" access="read"/>
    <property name="CanPause" type="b" access="read"/><property name="CanSeek" type="b" access="read"/>
    <property name="CanControl" type="b" access="read"/>
  </interface>
</node>
"""
ROOT, PLAYER = "org.mpris.MediaPlayer2", "org.mpris.MediaPlayer2.Player"
PATH = "/org/mpris/MediaPlayer2"


class Mpris:
    def __init__(self, app):
        self.app = app
        self.conn = None
        self.name = "org.mpris.MediaPlayer2.folio_chord"
        try:
            self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            return
        node = Gio.DBusNodeInfo.new_for_xml(XML)
        for iface in node.interfaces:
            self.conn.register_object(PATH, iface, self._call, self._get, self._set)
        Gio.bus_own_name_on_connection(self.conn, self.name, Gio.BusNameOwnerFlags.NONE, None, None)
        app.playback.listen(self._changed)

    def _pb(self):
        return self.app.playback

    def _call(self, conn, sender, path, iface, method, params, inv):
        pb = self._pb()
        if method == "Raise":
            self.app.do_activate()
        elif method == "Quit":
            self.app.quit()
        elif method == "PlayPause":
            pb.toggle()
        elif method == "Play":
            if pb.engine.state != "playing":
                pb.toggle()
        elif method == "Pause":
            pb.engine.pause()
        elif method == "Stop":
            pb.stop()
        elif method == "Next":
            pb.next()
        elif method == "Previous":
            pb.previous()
        elif method == "Seek":
            pb.engine.seek(pb.engine.position() + params.unpack()[0] / 1e6)
        elif method == "SetPosition":
            pb.engine.seek(params.unpack()[1] / 1e6)
        elif method == "OpenUri":
            pb.play_uri(params.unpack()[0])
        inv.return_value(None)

    def metadata(self):
        n = self._pb().now
        if not n:
            return {}
        tid = n.get("id")
        md = {"mpris:trackid": GLib.Variant("o", "/org/folio/chord/%s/%s" % (n.get("kind", "song"), tid) if isinstance(tid, int)
                                            else "/org/folio/chord/stream"),
              "xesam:title": GLib.Variant("s", self._pb().stream_title or n.get("title") or ""),
              "xesam:artist": GLib.Variant("as", [n.get("artist") or ""]),
              "xesam:album": GLib.Variant("s", n.get("album") or "")}
        if n.get("duration"):
            md["mpris:length"] = GLib.Variant("x", int(float(n["duration"]) * 1e6))
        return md

    def props(self, iface):
        pb = self._pb()
        if iface == ROOT:
            return {"CanQuit": GLib.Variant("b", True), "CanRaise": GLib.Variant("b", True),
                    "HasTrackList": GLib.Variant("b", False), "Identity": GLib.Variant("s", APP_NAME),
                    "DesktopEntry": GLib.Variant("s", "org.folio.Chord"),
                    "SupportedUriSchemes": GLib.Variant("as", ["file", "http", "https"]),
                    "SupportedMimeTypes": GLib.Variant("as", ["audio/mpeg", "audio/flac", "audio/ogg", "audio/mp4", "audio/x-wav"])}
        st = {"playing": "Playing", "paused": "Paused"}.get(pb.engine.state, "Stopped")
        loop = {"off": "None", "all": "Playlist", "one": "Track"}[pb.queue.repeat]
        return {"PlaybackStatus": GLib.Variant("s", st), "LoopStatus": GLib.Variant("s", loop),
                "Rate": GLib.Variant("d", 1.0), "Shuffle": GLib.Variant("b", pb.queue.shuffle),
                "Metadata": GLib.Variant("a{sv}", self.metadata()), "Volume": GLib.Variant("d", pb.engine.volume),
                "Position": GLib.Variant("x", int(pb.engine.position() * 1e6)),
                "MinimumRate": GLib.Variant("d", 1.0), "MaximumRate": GLib.Variant("d", 1.0),
                "CanGoNext": GLib.Variant("b", True), "CanGoPrevious": GLib.Variant("b", True),
                "CanPlay": GLib.Variant("b", True), "CanPause": GLib.Variant("b", True),
                "CanSeek": GLib.Variant("b", bool(pb.now and not (pb.now or {}).get("stream"))),
                "CanControl": GLib.Variant("b", True)}

    def _get(self, conn, sender, path, iface, prop):
        return self.props(iface).get(prop)

    def _set(self, conn, sender, path, iface, prop, value):
        pb = self._pb()
        v = value.unpack()
        if prop == "Volume":
            pb.set_volume(max(0.0, min(1.0, v)))
        elif prop == "Shuffle":
            pb.set_shuffle(v)
        elif prop == "LoopStatus":
            pb.set_repeat({"None": "off", "Playlist": "all", "Track": "one"}.get(v, "off"))
        return True

    def _changed(self, ev, val):
        if self.conn is None or ev not in ("state", "track", "tags", "volume", "modes"):
            return
        p = self.props(PLAYER)
        keys = {"state": ["PlaybackStatus"], "track": ["Metadata", "PlaybackStatus", "CanSeek"], "tags": ["Metadata"],
                "volume": ["Volume"], "modes": ["Shuffle", "LoopStatus"]}[ev]
        changed = {k: p[k] for k in keys}
        try:
            self.conn.emit_signal(None, PATH, "org.freedesktop.DBus.Properties", "PropertiesChanged",
                                  GLib.Variant("(sa{sv}as)", (PLAYER, changed, [])))
        except GLib.Error:
            pass
