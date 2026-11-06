"""Home Sharing (C4-01): share this library with the other Folio Chords on the same network, and
play from theirs. Plain HTTP over the local network, with no account and nothing sent off it: a
shared library answers a question asked on the local network, serves the song details it holds and
streams the songs themselves. Sharing is off until it is turned on, and can ask for a passcode."""
import json
import os
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request

from . import VERSION

PORT = 3691                  # HTTP, and the same number for the question asked over UDP
PROBE = b"FOLIO-SHARE?1"
PASS_HEADER = "X-Folio-Pass"
AGENT = "FolioChord/%s" % VERSION
TRACK_COLS = ("id", "title", "artist", "album_artist", "album", "genre", "composer", "year",
              "track_no", "track_count", "disc_no", "disc_count", "duration", "bitrate",
              "sample_rate", "kind", "size", "rating", "play_count", "has_art", "compilation")


def host_name():
    try:
        return socket.gethostname().split(".")[0] or "Folio Chord"
    except OSError:
        return "Folio Chord"


def default_name():
    return "%s's Music" % (os.environ.get("USER") or host_name())


# ---------------------------------------------------------------- sharing this library
class Share:
    """The server: this library offered to the network. Nothing is served until start()."""

    def __init__(self, lib, name=None, passcode="", port=PORT, host="0.0.0.0"):
        self.lib = lib
        self.name = name or default_name()
        self.passcode = passcode or ""
        self.port = port
        self.host = host
        self.httpd = None
        self.udp = None
        self._threads = []

    # ---- the song details and the files
    def info(self):
        n = len(self.lib.q("select id from tracks where not missing"))
        return {"folio": "share", "version": 1, "name": self.name, "songs": n,
                "playlist_count": len(self.playlists()), "app": VERSION,
                "needs_pass": bool(self.passcode)}

    def tracks(self):
        out = []
        for r in self.lib.tracks():
            out.append({c: (r[c] if c in r.keys() else None) for c in TRACK_COLS})
        return out

    def playlists(self):
        return [{"id": p["id"], "name": p["name"], "kind": p["kind"]}
                for p in self.lib.playlists() if p["kind"] in ("playlist", "smart")]

    def playlist(self, pid):
        return [r["id"] for r in self.lib.playlist_tracks(pid)]

    def path_of(self, tid):
        r = self.lib.track(tid)
        if r is None or r["missing"]:
            return None
        p = r["path"]
        return p if p and os.path.isfile(p) else None

    # ---- running
    def start(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        share = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = AGENT

            def log_message(self, *_a):
                pass                              # the terminal is not a log

            def _deny(self):
                if share.passcode and self.headers.get(PASS_HEADER, "") != share.passcode:
                    self.send_error(403, "This shared library needs its passcode.")
                    return True
                return False

            def _json(self, obj):
                b = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):                     # noqa: N802
                path = urllib.parse.urlparse(self.path).path.rstrip("/")
                if path in ("/folio", "/folio/info"):
                    return self._json(share.info())     # the greeting needs no passcode
                if self._deny():
                    return None
                if path == "/folio/tracks":
                    return self._json(share.tracks())
                if path == "/folio/playlists":
                    return self._json(share.playlists())
                if path.startswith("/folio/playlist/"):
                    try:
                        return self._json(share.playlist(int(path.rsplit("/", 1)[1])))
                    except (ValueError, TypeError):
                        return self.send_error(404)
                if path.startswith("/folio/art/"):
                    return self._art(path.rsplit("/", 1)[1])
                if path.startswith("/folio/stream/"):
                    return self._stream(path.rsplit("/", 1)[1])
                return self.send_error(404)

            def do_HEAD(self):                    # noqa: N802
                return self.do_GET()

            def _art(self, tid):
                from . import tags
                data, mime = None, "image/jpeg"
                try:
                    a = tags.artwork(share.path_of(int(tid)) or "")
                    data, mime = (a[0], a[1] or mime) if a else (None, mime)
                except Exception:                 # noqa: BLE001
                    data = None
                if not data:
                    return self.send_error(404)
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return None

            def _stream(self, tid):
                try:
                    p = share.path_of(int(tid))
                except (ValueError, TypeError):
                    p = None
                if not p:
                    return self.send_error(404)
                size = os.path.getsize(p)
                start, end = 0, size - 1
                rng = self.headers.get("Range", "")
                partial = rng.startswith("bytes=")
                if partial:
                    a, _, b = rng[6:].partition("-")
                    start = int(a or 0)
                    end = int(b) if b else size - 1
                    end = min(end, size - 1)
                    if start > end:
                        self.send_response(416)
                        self.send_header("Content-Range", "bytes */%d" % size)
                        self.end_headers()
                        return None
                self.send_response(206 if partial else 200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(end - start + 1))
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
                            return None           # the other end stopped listening
                        left -= len(chunk)
                return None

        self.httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self._spawn(self.httpd.serve_forever)
        self._start_beacon()
        return self.port

    def _start_beacon(self):
        """Answer the question asked on the local network, so no names have to be typed in."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", self.port))
        except OSError:
            self.udp = None
            return
        self.udp = s
        self._spawn(self._beacon)

    def _beacon(self):
        s = self.udp                              # kept here, so stopping mid-question is harmless
        while s is not None and self.udp is s:
            try:
                data, addr = s.recvfrom(256)
            except OSError:
                return
            if not data.startswith(b"FOLIO-SHARE?") or self.udp is not s:
                continue
            reply = dict(self.info())
            reply["port"] = self.port
            try:
                s.sendto(json.dumps(reply).encode(), addr)
            except OSError:
                return

    def _spawn(self, fn):
        t = threading.Thread(target=fn, daemon=True)
        t.start()
        self._threads.append(t)

    def stop(self):
        u, self.udp = self.udp, None
        if u is not None:
            try:
                u.close()
            except OSError:
                pass
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None


class Row(dict):
    """A song from a shared library. The song list asks for whatever columns are showing, so a
    detail the shared library didn't send reads as empty rather than failing."""

    def __missing__(self, _k):
        return None


# ---------------------------------------------------------------- finding and reading others
def probe(timeout=1.2, port=PORT, addresses=None):
    """The shared libraries that answer on the local network: [{name, host, port, songs}]."""
    found = {}
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(0.2)
        for a in (addresses or ["255.255.255.255", "127.0.0.1"]):
            try:
                s.sendto(PROBE, (a, port))
            except OSError:
                continue
        import time
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, addr = s.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                d = json.loads(data.decode("utf-8", "replace"))
            except ValueError:
                continue
            if d.get("folio") != "share":
                continue
            d["host"] = addr[0]
            d.setdefault("port", port)
            found[(d["host"], d["port"])] = d
    finally:
        s.close()
    return sorted(found.values(), key=lambda d: (d.get("name") or "").lower())


class Remote:
    """A shared library on another computer, read over HTTP."""

    def __init__(self, host, port=PORT, passcode="", name=""):
        self.host, self.port, self.passcode = host, int(port), passcode or ""
        self.name = name
        self.songs = []

    @property
    def base(self):
        return "http://%s:%d" % (self.host, self.port)

    def _get(self, path, timeout=20):
        h = {"User-Agent": AGENT}
        if self.passcode:
            h[PASS_HEADER] = self.passcode
        req = urllib.request.Request(self.base + path, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()

    def _json(self, path, timeout=20):
        return json.loads(self._get(path, timeout).decode("utf-8", "replace"))

    def info(self):
        d = self._json("/folio/info", timeout=6)
        self.name = d.get("name") or self.name
        return d

    def tracks(self):
        self.songs = [Row(t, path=self.stream_url(t["id"]), shared=True, missing=0, checked=1)
                      for t in self._json("/folio/tracks")]
        return self.songs

    def playlists(self):
        return self._json("/folio/playlists")

    def playlist(self, pid):
        ids = set(self._json("/folio/playlist/%d" % int(pid)))
        return [t for t in (self.songs or self.tracks()) if t["id"] in ids]

    def stream_url(self, tid):
        return "%s/folio/stream/%d" % (self.base, int(tid))

    def art_url(self, tid):
        return "%s/folio/art/%d" % (self.base, int(tid))

    def reachable(self):
        try:
            self.info()
            return True
        except (urllib.error.URLError, OSError, ValueError):
            return False
