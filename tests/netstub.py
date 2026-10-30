"""A stand-in for the internet in tests: radio-browser.info, Apple's podcast search and charts,
Podcast Index, two podcast feeds with their episode files, and a radio stream (an Ogg tone).

  s = Stub(audio_file); s.base -> "http://127.0.0.1:port"; s.hits -> [(path, query, headers)]
"""
import hashlib
import os
import http.server
import json
import threading
import urllib.parse

STATIONS = [
    {"stationuuid": "u-jazz", "name": "Jazz FM Test", "url": "", "url_resolved": "", "homepage": "http://jazz.example",
     "favicon": "", "tags": "jazz,smooth jazz", "country": "Netherlands", "countrycode": "NL", "language": "dutch",
     "codec": "OGG", "bitrate": 128, "votes": 900, "clickcount": 50},
    {"stationuuid": "u-rock", "name": "Rock Radio Test", "url": "", "url_resolved": "", "homepage": "",
     "favicon": "", "tags": "rock,classic rock", "country": "The United States Of America", "countrycode": "US",
     "language": "english", "codec": "OGG", "bitrate": 192, "votes": 500, "clickcount": 80},
    {"stationuuid": "u-news", "name": "News Talk Test", "url": "", "url_resolved": "", "homepage": "",
     "favicon": "", "tags": "news,talk", "country": "Germany", "countrycode": "DE", "language": "german",
     "codec": "OGG", "bitrate": 64, "votes": 100, "clickcount": 10},
]


def feed(base, name, n):
    items = "".join(
        "<item><title>%s episode %d</title><guid>%s-%d</guid><pubDate>%s</pubDate>"
        "<itunes:duration>00:00:02</itunes:duration><description>&lt;p&gt;Notes for %d&lt;/p&gt;</description>"
        "<enclosure url='%s/ep/%s-%d.ogg' type='audio/ogg' length='1000'/></item>"
        % (name.capitalize(), i, name, i, "Mon, %02d Sep 2026 10:00:00 +0000" % (10 + i), i, base, name, i) for i in range(n, 0, -1))
    return ("<?xml version='1.0' encoding='UTF-8'?><rss version='2.0' xmlns:itunes='http://www.itunes.com/dtds/podcast-1.0.dtd'>"
            "<channel><title>%s Show</title><itunes:author>%s Media</itunes:author><description>All about %s.</description>"
            "<itunes:image href='%s/art/%s.png'/><itunes:category text='Technology'/><link>http://%s.example</link>%s</channel></rss>"
            % (name.capitalize(), name.capitalize(), name, base, name, name, items)).encode()


class Stub:
    def __init__(self, audio, pi_key="k", pi_secret="s"):
        self.audio = open(audio, "rb").read()
        self.hits = []
        self.feeds_n = {"tech": 3, "garden": 2}
        stub = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                q = dict(urllib.parse.parse_qsl(u.query))
                stub.hits.append((u.path, q, dict(self.headers)))
                if u.path.startswith("/stream/"):
                    return stub.stream(self)
                body, ctype, code = stub.route(u.path, q, self.headers)
                rng = self.headers.get("Range")
                start, end = 0, len(body) - 1
                if rng and code == 200 and u.path.startswith("/ep/"):
                    a, _, b = rng.replace("bytes=", "").partition("-")
                    start = int(a or 0)
                    end = int(b) if b else len(body) - 1
                    code = 206
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                if u.path.startswith("/ep/"):
                    self.send_header("Accept-Ranges", "bytes")
                if code == 206:
                    self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, len(body)))
                    body = body[start:end + 1]
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = "http://127.0.0.1:%d" % self.srv.server_address[1]
        self.pi = (pi_key, pi_secret)
        for s in STATIONS:
            s["url_resolved"] = s["url"] = self.base + "/stream/" + s["stationuuid"]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown()

    TITLE = "Night Owls - Midnight Blue"

    def stream(self, h):
        """An endless internet-radio stream (no length, not seekable), with Shoutcast/Icecast song
        titles when the player asks for them."""
        import time as _t
        icy = h.headers.get("Icy-MetaData") == "1"
        h.send_response(200)
        h.send_header("Content-Type", "application/ogg")
        h.send_header("icy-name", "Test Station")
        if icy:
            h.send_header("icy-metaint", "8192")
        h.end_headers()
        meta = ("StreamTitle='%s';" % self.TITLE).encode()
        meta += b"\0" * (-len(meta) % 16)
        block = bytes([len(meta) // 16]) + meta
        sent = 0
        end = _t.time() + 20
        try:
            while _t.time() < end:
                for i in range(0, len(self.audio), 8192):
                    chunk = self.audio[i:i + 8192]
                    if icy:
                        # metadata goes in after every 8192 bytes of audio
                        while chunk:
                            room = 8192 - (sent % 8192)
                            part, chunk = chunk[:room], chunk[room:]
                            h.wfile.write(part)
                            sent += len(part)
                            if sent % 8192 == 0:
                                h.wfile.write(block)
                    else:
                        h.wfile.write(chunk)
                    h.wfile.flush()
                    _t.sleep(0.05)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def j(self, v):
        return json.dumps(v).encode(), "application/json", 200

    def route(self, path, q, headers):
        b = self.base
        if path == "/json/stations/search":
            r = STATIONS
            if q.get("name"):
                r = [s for s in r if q["name"].lower() in s["name"].lower()]
            if q.get("tag"):
                r = [s for s in r if q["tag"].lower() in s["tags"].split(",")]
            if q.get("countrycode"):
                r = [s for s in r if s["countrycode"] == q["countrycode"]]
            if q.get("language"):
                r = [s for s in r if s["language"] == q["language"].lower()]
            if q.get("order") == "votes":
                r = sorted(r, key=lambda s: -s["votes"])
            return self.j(r[:int(q.get("limit", 100))])
        if path.startswith("/json/stations/topvote/"):
            return self.j(sorted(STATIONS, key=lambda s: -s["votes"]))
        if path == "/json/stations/byuuid":
            want = q.get("uuids", "").split(",")
            return self.j([s for s in STATIONS if s["stationuuid"] in want])
        if path == "/json/tags":
            return self.j([{"name": "rock", "stationcount": 2}, {"name": "jazz", "stationcount": 1}, {"name": "news", "stationcount": 1}])
        if path == "/json/countries":
            return self.j([{"name": "Netherlands", "iso_3166_1": "NL", "stationcount": 1}, {"name": "Germany", "iso_3166_1": "DE", "stationcount": 1}])
        if path == "/json/languages":
            return self.j([{"name": "english", "stationcount": 1}, {"name": "dutch", "stationcount": 1}])
        if path.startswith("/json/url/"):
            return self.j({"ok": True, "url": ""})
        if path.startswith("/stream/") or path.startswith("/ep/"):
            return self.audio, "audio/ogg", 200
        if path.startswith("/art/"):
            return b"\x89PNG\r\n\x1a\n", "image/png", 200
        if path.startswith("/feed/"):
            name = path.split("/")[-1]
            return feed(b, name, self.feeds_n.get(name, 1)), "application/rss+xml", 200
        if path == "/search":       # Apple
            shows = [{"collectionId": 11, "collectionName": "Tech Show", "artistName": "Tech Media", "feedUrl": b + "/feed/tech",
                      "artworkUrl600": b + "/art/tech.png", "primaryGenreName": "Technology", "trackCount": 3},
                     {"collectionId": 12, "collectionName": "Garden Show", "artistName": "Garden Media", "feedUrl": b + "/feed/garden",
                      "artworkUrl600": b + "/art/garden.png", "primaryGenreName": "Leisure", "trackCount": 2},
                     {"collectionId": 13, "collectionName": "No Feed Show", "artistName": "X"}]
            t = q.get("term", "").lower()
            return self.j({"resultCount": 3, "results": [s for s in shows if t in s["collectionName"].lower() or t == "show"]})
        if "/rss/toppodcasts/" in path:
            ids = ["12", "11"] if "genre=26" in path else ["11"]
            return self.j({"feed": {"entry": [{"id": {"attributes": {"im:id": i}}} for i in ids]}})
        if path == "/lookup":
            all_ = {"11": {"collectionId": 11, "collectionName": "Tech Show", "artistName": "Tech Media", "feedUrl": b + "/feed/tech",
                           "artworkUrl600": b + "/art/tech.png", "primaryGenreName": "Technology"},
                    "12": {"collectionId": 12, "collectionName": "Garden Show", "artistName": "Garden Media", "feedUrl": b + "/feed/garden",
                           "artworkUrl600": b + "/art/garden.png", "primaryGenreName": "Leisure"}}
            return self.j({"results": [all_[i] for i in q.get("id", "").split(",") if i in all_]})
        if path in ("/pi/search/byterm", "/pi/podcasts/trending"):
            k, s = self.pi
            d = headers.get("X-Auth-Date", "")
            ok = headers.get("X-Auth-Key") == k and headers.get("Authorization") == hashlib.sha1((k + s + d).encode()).hexdigest()
            if not ok:
                return b'{"status":"false"}', "application/json", 401
            return self.j({"feeds": [{"id": 77, "title": "Tech Show", "author": "Tech Media", "url": b + "/feed/tech",
                                      "artwork": b + "/art/tech.png", "categories": {"102": "Technology"}, "episodeCount": 3}]})
        if path == "/mb/release/":
            ok = "Night Sessions" in q.get("query", "")
            return self.j({"releases": [{"id": "rel-1", "score": 100}] if ok else []})
        if path == "/caa/release/rel-1/front-500":
            return open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "art.png"), "rb").read(), "image/png", 200
        if path.startswith("/mb/discid/"):
            if path.endswith("/unknown"):
                return self.j({"releases": []})
            return self.j({"releases": [{"title": "Fake Disc", "date": "2001-05-01",
                                         "artist-credit": [{"name": "Test Band", "joinphrase": ""}],
                                         "media": [{"position": 1, "discs": [{"id": path.split("/")[-1]}],
                                                    "tracks": [{"title": "Opening"}, {"title": "Middle",
                                                                "artist-credit": [{"name": "Test Band", "joinphrase": " feat. "},
                                                                                  {"name": "Guest", "joinphrase": ""}]},
                                                               {"title": "Closing"}]}]}]})
        return b"not found", "text/plain", 404
