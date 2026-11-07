"""Playing to network speakers (C4-02): a renderer is found and described, told what to play over
SOAP, and served the song itself a piece at a time over HTTP."""
import os
import sys
import tempfile
import threading
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
from folio_chord import cast  # noqa: E402

FAILS = []
N = [0]


def check(ok, what, info=None):
    N[0] += 1
    print(("ok   " if ok else "FAIL ") + what + ("" if ok or info is None else "  -- %r" % (info,)))
    if not ok:
        FAILS.append(what)


T = tempfile.mkdtemp(prefix="chord-cast-")
# a file to hand over: what is in it doesn't matter here, only that it is served whole
SONG = os.path.join(T, "song.mp3")
with open(SONG, "wb") as f:
    f.write(bytes(range(256)) * 40)

# ------------------------------------------------------------------ a speaker that isn't real
DESC = """<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0"><device>
<deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
<friendlyName>Kitchen Hi-Fi</friendlyName>
<UDN>uuid:test-renderer-1</UDN>
<serviceList>
<service><serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>
<controlURL>/ctrl/av</controlURL></service>
<service><serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType>
<controlURL>/ctrl/rc</controlURL></service>
</serviceList></device></root>"""

CALLS = []


class Renderer(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_a):
        pass

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/desc.xml"):
            b = DESC.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/xml")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        self.send_error(404)

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(n).decode()
        action = (self.headers.get("SOAPAction", "") or "").strip('"').rsplit("#", 1)[-1]
        CALLS.append((action, body))
        out = {"GetPositionInfo": "<RelTime>0:00:07</RelTime><TrackDuration>0:03:20</TrackDuration>",
               "GetTransportInfo": "<CurrentTransportState>PLAYING</CurrentTransportState>"}.get(action, "")
        env = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
               '<s:Body><u:%sResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">%s'
               "</u:%sResponse></s:Body></s:Envelope>" % (action, out, action)).encode()
        self.send_response(200)
        self.send_header("Content-Type", 'text/xml; charset="utf-8"')
        self.send_header("Content-Length", str(len(env)))
        self.end_headers()
        self.wfile.write(env)


srv = ThreadingHTTPServer(("127.0.0.1", 0), Renderer)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True).start()
BASE = "http://127.0.0.1:%d" % srv.server_address[1]

# ------------------------------------------------------------------ what it says about itself
info = cast.describe(BASE + "/desc.xml")
check(info is not None and info["name"] == "Kitchen Hi-Fi", "a renderer says its name", info)
check(info and info["avtransport"] == BASE + "/ctrl/av", "and where to send what it should play", info)
check(info and info["rendering"] == BASE + "/ctrl/rc", "and where to set its volume", info)
check(cast.describe(BASE + "/nothing.xml") is None, "a page that isn't a renderer gives nothing")

# the answer to the question asked on the network
hdrs = cast._parse_ssdp("HTTP/1.1 200 OK\r\nLOCATION: %s/desc.xml\r\nST: %s\r\n" % (BASE, cast.RENDERER))
check(hdrs.get("location") == BASE + "/desc.xml", "an answer on the network carries the address", hdrs)

# ------------------------------------------------------------------ the one-item playlist
d = cast.didl("http://host/song1", "A Song & Another", "The Artist", "The Album", "x.flac")
check("&amp;" in d and "<dc:title>" in d, "the playlist escapes what needs it", d[:80])
check('protocolInfo="http-get:*:audio/flac' in d, "and says what kind of file it is", d[:200])
check(cast.mime_of("x.m4a") == "audio/mp4" and cast.mime_of("x.unknown") == "audio/mpeg", "file kinds")

# ------------------------------------------------------------------ playing to it
server = cast.Server(port=0)
check(server.start(), "the little server starts")
server.port = server.httpd.server_address[1]
sp = cast.Speaker(info, server)
ok = sp.play_file(SONG, "A Song", "The Artist", "The Album")
check(ok, "the speaker takes the song")
check([a for a, _ in CALLS][:2] == ["SetAVTransportURI", "Play"], "told what to play, then told to play it", CALLS[:2])
url = [b for a, b in CALLS if a == "SetAVTransportURI"]
check(url and ("http://" in url[0]), "the address it was given points back here", url[:1])

# the song itself, a piece at a time
addr = "http://127.0.0.1:%d/%s" % (server.port, server.token)
with urllib.request.urlopen(addr, timeout=5) as r:
    whole = r.read()
check(len(whole) == os.path.getsize(SONG), "the whole song is served", (len(whole), os.path.getsize(SONG)))
req = urllib.request.Request(addr, headers={"Range": "bytes=10-109"})
with urllib.request.urlopen(req, timeout=5) as r:
    part = r.read()
    code = r.status
check(code == 206 and len(part) == 100, "and a piece of it when a piece is asked for", (code, len(part)))

check(sp.position() == (7.0, 200.0), "where the speaker is in the song", sp.position())
check(sp.state() == "PLAYING", "and what it is doing", sp.state())
check(sp.pause() and sp.resume() and sp.seek(30) and sp.set_volume(40), "pause, resume, seek and volume")
check([a for a, _ in CALLS][-4:] == ["Pause", "Play", "Seek", "SetVolume"], "each as its own call", CALLS[-4:])
sp.close()
check(server.httpd is None, "and the little server stops with it")

# a renderer that doesn't answer is not a crash
gone = dict(info)
gone["avtransport"] = "http://127.0.0.1:9/ctrl"
quiet = cast.Speaker(gone, cast.Server(port=0))
check(quiet.play_file(SONG) is False, "a speaker that doesn't answer says so")
quiet.server.stop()

srv.shutdown()
print("\n%d checks, %d failed" % (N[0], len(FAILS)))
sys.exit(1 if FAILS else 0)
