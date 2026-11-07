# C4-02 Playing to network speakers in the window: the speakers that answered are offered, the
# sound goes to the one chosen, the controls drive it, and "This computer" brings it back.
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.environ["FOLIO_TESTS"])
from uicommon import check, music, pump, run, wait  # noqa: E402
from folio_chord import cast  # noqa: E402

DESC = """<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0"><device>
<deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
<friendlyName>Test Speaker</friendlyName><UDN>uuid:ui-renderer</UDN>
<serviceList>
<service><serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>
<controlURL>/av</controlURL></service>
<service><serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType>
<controlURL>/rc</controlURL></service>
</serviceList></device></root>"""

CALLS = []
STATE = ["PLAYING"]


class Renderer(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_a):
        pass

    def do_GET(self):  # noqa: N802
        b = DESC.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/xml")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(n)
        action = (self.headers.get("SOAPAction", "") or "").strip('"').rsplit("#", 1)[-1]
        CALLS.append(action)
        out = {"GetPositionInfo": "<RelTime>0:00:02</RelTime><TrackDuration>0:00:03</TrackDuration>",
               "GetTransportInfo": "<CurrentTransportState>%s</CurrentTransportState>" % STATE[0]}.get(action, "")
        env = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
               '<s:Body><u:%sResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">%s'
               "</u:%sResponse></s:Body></s:Envelope>" % (action, out, action)).encode()
        self.send_response(200)
        self.send_header("Content-Type", 'text/xml; charset="utf-8"')
        self.send_header("Content-Length", str(len(env)))
        self.end_headers()
        self.wfile.write(env)


def main():
    w = win  # noqa: F821
    a = app  # noqa: F821
    pb = a.playback
    _d, songs = music(w, secs=3.0)
    check(bool(songs), "songs to play")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Renderer)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]

    # the window asks the network; here the answer is the speaker above
    cast.speakers = lambda timeout=2.0: [cast.describe(base + "/desc.xml")]

    w.run("speakers")
    pump(0.4)
    check(getattr(w, "speaker_popover", None) is not None, "the Play to list opens")
    wait(lambda: any("Test Speaker" in str(c.get_label()) for c in w.speaker_popover.get_child().get_children()
                     if hasattr(c, "get_label") and c.get_label()), 8)
    labels = [c.get_label() for c in w.speaker_popover.get_child().get_children()
              if hasattr(c, "get_label") and c.get_label()]
    check("This computer" in labels, "this computer is offered", labels)
    check(any("Test Speaker" in (l or "") for l in labels), "and the speaker that answered", labels)

    info = cast.describe(base + "/desc.xml")
    w.choose_speaker(info)
    pump(0.3)
    eng = pb.engine
    check(eng.speaker is not None and eng.speaker.name == "Test Speaker", "the sound goes to the speaker")

    # play a song: the speaker is told what to play
    ids = [r["id"] for r in a.lib.tracks()]
    pb.play_songs(ids, 0)
    wait(lambda: "SetAVTransportURI" in CALLS, 8)
    check("SetAVTransportURI" in CALLS and "Play" in CALLS, "told what to play, and to play it", CALLS[:4])
    check(eng.state == "playing", "the window says it is playing", eng.state)

    pb.toggle()
    pump(0.3)
    check("Pause" in CALLS and eng.state == "paused", "pause reaches the speaker", eng.state)
    pb.toggle()
    pump(0.3)
    check(eng.state == "playing", "and so does playing again")

    eng.seek(1.0)
    pump(0.3)
    check("Seek" in CALLS, "seeking reaches it too")
    pb.set_volume(0.3)
    pump(0.3)
    check("SetVolume" in CALLS, "and the volume")

    # back to this computer
    w.choose_speaker(None)
    pump(0.3)
    check(eng.speaker is None, "This computer brings the sound back")
    srv.shutdown()


run(main)
