"""Playing to network speakers (C4-02): the sound goes to a UPnP (DLNA) renderer on the local
network — a hi-fi, a soundbar, a smart speaker — instead of this computer's own output. Chord
finds the renderers by asking on the network, serves the song over plain HTTP from this computer,
and tells the renderer to play that address. Nothing leaves the network and no account is needed.
"""
import os
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import VERSION

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
RENDERER = "urn:schemas-upnp-org:device:MediaRenderer:1"
AVTRANSPORT = "urn:schemas-upnp-org:service:AVTransport:1"
RENDERING = "urn:schemas-upnp-org:service:RenderingControl:1"
AGENT = "FolioChord/%s UPnP/1.0" % VERSION
PORT = 3692                  # the little server that hands the song to the speaker

MIME = {
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".mp4": "audio/mp4", ".aac": "audio/aac",
    ".flac": "audio/flac", ".ogg": "audio/ogg", ".oga": "audio/ogg", ".opus": "audio/ogg",
    ".wav": "audio/wav", ".aiff": "audio/aiff", ".aif": "audio/aiff", ".wma": "audio/x-ms-wma",
    ".m4b": "audio/mp4", ".alac": "audio/mp4",
}


def mime_of(path):
    return MIME.get(os.path.splitext(path)[1].lower(), "audio/mpeg")


def local_address(towards="239.255.255.250"):
    """This computer's address on the network the speaker is on."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((towards, 9))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# ------------------------------------------------------------------ finding the speakers
def _parse_ssdp(text):
    """The headers of one SSDP answer, lower-cased."""
    out = {}
    for line in text.splitlines()[1:]:
        k, _, v = line.partition(":")
        if k.strip():
            out[k.strip().lower()] = v.strip()
    return out


def discover(timeout=2.0, target=RENDERER):
    """Ask the network for media renderers; returns their description addresses."""
    msg = ("M-SEARCH * HTTP/1.1\r\n"
           "HOST: %s:%d\r\n"
           'MAN: "ssdp:discover"\r\n'
           "MX: 1\r\n"
           "ST: %s\r\n"
           "USER-AGENT: %s\r\n\r\n" % (SSDP_ADDR, SSDP_PORT, target, AGENT)).encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    s.settimeout(0.4)
    found = []
    try:
        for _ in range(2):                       # asked twice: UDP loses packets
            try:
                s.sendto(msg, (SSDP_ADDR, SSDP_PORT))
            except OSError:
                return found
        end = threading.Event()
        import time
        stop = time.monotonic() + timeout
        while time.monotonic() < stop and not end.is_set():
            try:
                data, addr = s.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            h = _parse_ssdp(data.decode("utf-8", "replace"))
            loc = h.get("location")
            if loc and loc not in found:
                found.append(loc)
    finally:
        s.close()
    return found


def _text(node, tag):
    for e in node.iter():
        if e.tag.rsplit("}", 1)[-1] == tag and e.text:
            return e.text.strip()
    return ""


def describe(location, timeout=3.0):
    """What a renderer says about itself: its name and how to drive it."""
    try:
        req = urllib.request.Request(location, headers={"User-Agent": AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            xml = r.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    name = _text(root, "friendlyName") or "Speaker"
    av, rc = "", ""
    for svc in root.iter():
        if svc.tag.rsplit("}", 1)[-1] != "service":
            continue
        kind = _text(svc, "serviceType")
        ctrl = _text(svc, "controlURL")
        if not ctrl:
            continue
        if kind.startswith(AVTRANSPORT[:-1]):
            av = urllib.parse.urljoin(location, ctrl)
        elif kind.startswith(RENDERING[:-1]):
            rc = urllib.parse.urljoin(location, ctrl)
    if not av:
        return None
    return {"name": name, "location": location, "avtransport": av, "rendering": rc,
            "udn": _text(root, "UDN")}


def speakers(timeout=2.0):
    """Every renderer on the network, by name."""
    out = []
    for loc in discover(timeout):
        d = describe(loc)
        if d and not any(x["udn"] == d["udn"] and d["udn"] for x in out):
            out.append(d)
    out.sort(key=lambda d: d["name"].lower())
    return out


# ------------------------------------------------------------------ talking to one
def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def didl(url, title, artist="", album="", path=""):
    """The one-item playlist a renderer wants with the address."""
    mime = mime_of(path or url)
    return (
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        '<item id="1" parentID="0" restricted="1">'
        "<dc:title>%s</dc:title>"
        "<upnp:artist>%s</upnp:artist>"
        "<upnp:album>%s</upnp:album>"
        "<upnp:class>object.item.audioItem.musicTrack</upnp:class>"
        '<res protocolInfo="http-get:*:%s:DLNA.ORG_OP=01;DLNA.ORG_FLAGS=01700000000000000000000000000000">%s</res>'
        "</item></DIDL-Lite>" % (_esc(title), _esc(artist), _esc(album), mime, _esc(url))
    )


def soap(control_url, service, action, args, timeout=5.0):
    """One SOAP call to a renderer. Gives back the answer's fields, or None."""
    body = "".join("<%s>%s</%s>" % (k, _esc(str(v)) if not str(v).startswith("<") else str(v), k)
                   for k, v in args)
    env = ('<?xml version="1.0" encoding="utf-8"?>'
           '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
           's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
           "<s:Body><u:%s xmlns:u=\"%s\">%s</u:%s></s:Body></s:Envelope>" % (action, service, body, action))
    req = urllib.request.Request(
        control_url,
        data=env.encode(),
        headers={"Content-Type": 'text/xml; charset="utf-8"',
                 "SOAPAction": '"%s#%s"' % (service, action),
                 "User-Agent": AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    out = {}
    for e in root.iter():
        tag = e.tag.rsplit("}", 1)[-1]
        if tag not in ("Envelope", "Body") and not tag.startswith(action):
            out[tag] = e.text or ""
    return out


# ------------------------------------------------------------------ handing over the song
class Server:
    """A small HTTP server that hands the current song to the speaker, a piece at a time."""

    def __init__(self, port=PORT):
        self.port = port
        self.httpd = None
        self.path = None
        self.token = "song"

    def url(self):
        if not self.httpd:
            return None
        return "http://%s:%d/%s" % (local_address(), self.port, self.token)

    def serve(self, path):
        """Offer this file; the address stays the same, the file behind it changes."""
        self.path = path if path and os.path.isfile(path) else None
        self.token = "song%d" % (abs(hash(path or "")) % 100000)
        return self.url()

    def start(self):
        if self.httpd:
            return True
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "FolioChord/%s" % VERSION

            def log_message(self, *_a):
                pass

            def do_GET(self):                     # noqa: N802
                p = owner.path
                if not p or not os.path.isfile(p):
                    return self.send_error(404)
                size = os.path.getsize(p)
                start, end = 0, size - 1
                rng = self.headers.get("Range", "")
                partial = rng.startswith("bytes=")
                if partial:
                    a, _, b = rng[6:].partition("-")
                    try:
                        start = int(a or 0)
                        end = int(b) if b else size - 1
                    except ValueError:
                        start, end = 0, size - 1
                    end = min(end, size - 1)
                    if start > end:
                        self.send_response(416)
                        self.send_header("Content-Range", "bytes */%d" % size)
                        self.end_headers()
                        return None
                self.send_response(206 if partial else 200)
                self.send_header("Content-Type", mime_of(p))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("transferMode.dlna.org", "Streaming")
                if partial:
                    self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
                self.end_headers()
                if self.command == "HEAD":
                    return None
                left = end - start + 1
                with open(p, "rb") as f:
                    f.seek(start)
                    while left > 0:
                        chunk = f.read(min(65536, left))
                        if not chunk:
                            break
                        try:
                            self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError):
                            break
                        left -= len(chunk)
                return None

            def do_HEAD(self):                    # noqa: N802
                return self.do_GET()

        try:
            self.httpd = ThreadingHTTPServer(("0.0.0.0", self.port), Handler)
        except OSError:
            self.httpd = None
            return False
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.3},
                         daemon=True).start()
        return True

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except OSError:
                pass
            self.httpd = None


class Speaker:
    """One renderer, being played to."""

    def __init__(self, info, server=None):
        self.info = dict(info)
        self.server = server or Server()
        self.playing = None

    @property
    def name(self):
        return self.info.get("name", "Speaker")

    def _av(self, action, args):
        return soap(self.info["avtransport"], AVTRANSPORT, action, [("InstanceID", 0)] + list(args))

    def play_file(self, path, title="", artist="", album=""):
        """Put a song on the speaker and start it."""
        if not self.server.start():
            return False
        url = self.server.serve(path)
        if not url:
            return False
        meta = didl(url, title or os.path.basename(path), artist, album, path)
        if self._av("SetAVTransportURI", [("CurrentURI", url), ("CurrentURIMetaData", meta)]) is None:
            return False
        ok = self._av("Play", [("Speed", 1)]) is not None
        self.playing = path if ok else None
        return ok

    def pause(self):
        return self._av("Pause", []) is not None

    def resume(self):
        return self._av("Play", [("Speed", 1)]) is not None

    def stop(self):
        out = self._av("Stop", [])
        self.playing = None
        return out is not None

    def seek(self, seconds):
        t = "%d:%02d:%02d" % (int(seconds) // 3600, (int(seconds) % 3600) // 60, int(seconds) % 60)
        return self._av("Seek", [("Unit", "REL_TIME"), ("Target", t)]) is not None

    def set_volume(self, percent):
        if not self.info.get("rendering"):
            return False
        v = max(0, min(100, int(round(percent))))
        return soap(self.info["rendering"], RENDERING, "SetVolume",
                    [("InstanceID", 0), ("Channel", "Master"), ("DesiredVolume", v)]) is not None

    def position(self):
        """Where the speaker is in the song, in seconds, and how long it is."""
        out = self._av("GetPositionInfo", [])
        if not out:
            return None
        return (_hms(out.get("RelTime", "")), _hms(out.get("TrackDuration", "")))

    def state(self):
        out = self._av("GetTransportInfo", [])
        return (out or {}).get("CurrentTransportState", "")

    def close(self):
        self.stop()
        self.server.stop()


def _hms(text):
    """"0:03:12" as seconds."""
    parts = [p for p in (text or "").split(":") if p != ""]
    if not parts:
        return 0.0
    try:
        v = 0.0
        for p in parts:
            v = v * 60 + float(p)
        return v
    except ValueError:
        return 0.0
