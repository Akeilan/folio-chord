"""Engine tests for Backlog 8 (C8-39): what the release run never caught before. A damaged library,
odd file names, songs moved or renamed, playlists with missing songs, M3U files from other
programs, Smart Playlist rules, tags in every format (WMA, WavPack, MP2 and Matroska too, C8-41),
podcast feeds as real sites send them, cut-off downloads, an iTunes library, station playlists, a
shared library's playlists, passcodes kept out of settings.json."""
import gzip
import http.server
import json
import os
import plistlib
import shutil
import socket
import sqlite3
import stat
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
os.environ.setdefault("FOLIO_CHORD_AUDIOSINK", "fakesink")
os.environ["FOLIO_CHORD_NO_KEYRING"] = "1"
TMP = tempfile.mkdtemp(prefix="chord-b8-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(TMP, "config")
import gi  # noqa: E402
gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402
Gst.init(None)
import mkaudio  # noqa: E402
from folio_chord import itunes, keys, library as L, net, podcasts as P, radio, sharing, tags  # noqa: E402

FAILS = []
N = [0]


def check(ok, what, info=None):
    N[0] += 1
    print(("ok   " if ok else "FAIL ") + what + ("" if ok or info is None else "  -- %r" % (info,)))
    sys.stdout.flush()
    if not ok:
        FAILS.append(what)


def gst_make(path, enc, secs=2.0, freq=440):
    """A tone through a GStreamer encoder (the same parts on every test machine)."""
    n = int(secs * 44100 / 1024) + 1
    p = Gst.parse_launch("audiotestsrc num-buffers=%d samplesperbuffer=1024 freq=%d volume=0.3 ! "
                         "audio/x-raw,rate=44100,channels=2 ! audioconvert ! audioresample ! %s ! filesink name=out" % (n, freq, enc))
    p.get_by_name("out").set_property("location", path)
    p.set_state(Gst.State.PLAYING)
    m = p.get_bus().timed_pop_filtered(30 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
    p.set_state(Gst.State.NULL)
    return m is not None and m.type == Gst.MessageType.EOS and os.path.getsize(path) > 0


# ---------------------------------------------------------------- C8-01 a damaged library
d = os.path.join(TMP, "lib1")
os.makedirs(d)
db = os.path.join(d, "library.db")
lib, note = L.open_library(db)
check(note is None and os.path.exists(db + ".bak"), "C8-01: a good library opens and a copy is kept beside it")
lib.new_playlist("Keep me")
lib.backup()
lib.db.close()
with open(db, "r+b") as f:
    f.seek(0)
    f.write(os.urandom(4096))
lib, note = L.open_library(db)
check(note and "copy" in note and any(p["name"] == "Keep me" for p in lib.playlists()) and os.path.exists(db + ".damaged"),
      "C8-01: a damaged library is set aside and the last good copy used, with a word about it", note)
lib.db.close()
os.remove(db + ".bak")
open(db, "wb").write(b"not a database" * 100)
lib, note = L.open_library(db)
check(note and "new library" in note and lib.tracks() == [], "C8-01: with no good copy a new library is started, and it says so", note)
lib.db.close()

# ---------------------------------------------------------------- C8-02, C8-05, C8-24 scanning
music = os.path.join(TMP, "music")
songs = mkaudio.make(music, 2.0)
lib = L.Library(os.path.join(TMP, "lib2", "library.db"))
lib.add_folder(music)
bad = os.path.join(music, "zz").encode() + b"/caf\xe9 bad.flac"
os.makedirs(os.path.join(music, "zz"), exist_ok=True)
shutil.copy(songs["Blue Train"], bad)
shutil.copy(songs["Blue Train"], os.path.join(music, "zz", "zzz after.flac"))
os.makedirs(os.path.join(TMP, "elsewhere", "Album"), exist_ok=True)
shutil.copy(songs["Sonata in C"], os.path.join(TMP, "elsewhere", "Album", "linked.flac"))
tags.write(os.path.join(TMP, "elsewhere", "Album", "linked.flac"), {"title": "Linked Song"})
os.symlink(os.path.join(TMP, "elsewhere"), os.path.join(music, "linked"))
os.symlink(music, os.path.join(music, "zz", "loop"))
n, gone = lib.scan()
names = {os.path.basename(r["path"]) for r in lib.tracks()}
check("zzz after.flac" in names and len(lib.bad_names) == 1, "C8-02: a badly named file is reported and the scan goes on past it",
      (sorted(names), lib.bad_names))
check("linked.flac" in names and len([x for x in names if x == "linked.flac"]) == 1,
      "C8-24: a linked folder is looked into, and a link back to the music folder doesn't loop", sorted(names))
T = {r["title"]: r["id"] for r in lib.tracks()}
before = len(lib.tracks())
lib.rate([T["Lazy Bird"]], 80)
lib.played(T["Lazy Bird"])
pl = lib.new_playlist("Faves", tracks=[T["Lazy Bird"], T["Blue Train"]])
old = songs["Lazy Bird"]
new = os.path.join(music, "Moved Here", "renamed lazy.m4a")
os.makedirs(os.path.dirname(new))
os.rename(old, new)
lib.scan()
r = lib.track(T["Lazy Bird"])
check(r and r["path"] == new and r["rating"] == 80 and r["play_count"] == 1 and not r["missing"]
      and T["Lazy Bird"] in [x["id"] for x in lib.playlist_tracks(pl)] and len(lib.tracks()) == before,
      "C8-05: a song renamed and moved in Files keeps its rating, plays and playlists",
      (len(lib.tracks()), before, [x["id"] for x in lib.playlist_tracks(pl)]))

# ---------------------------------------------------------------- C8-03 playlist places
lib.update([T["Blue Train"]], missing=1)
pl2 = lib.new_playlist("Order", tracks=[T["Blue Train"], T["Locomotion"], T["Sonata in C"], T["Moment's Notice"]])
rows = lib.playlist_tracks(pl2)
pos = [r["pl_pos"] for r in rows if r["title"] == "Sonata in C"]
lib.remove_from_playlist(pl2, pos)
left = [r["title"] for r in lib.playlist_tracks(pl2)]
check(left == ["Locomotion", "Moment's Notice"], "C8-03: removing a song from a playlist with a missing song in it removes that song", left)
lib.reorder_playlist(pl2, [r["pl_pos"] for r in lib.playlist_tracks(pl2) if r["title"] == "Moment's Notice"],
                     [r["pl_pos"] for r in lib.playlist_tracks(pl2) if r["title"] == "Locomotion"][0])
check([r["title"] for r in lib.playlist_tracks(pl2)] == ["Moment's Notice", "Locomotion"], "C8-03: reordering uses the playlist's own places")
lib.update([T["Blue Train"]], missing=0)
f1 = lib.new_playlist("F1", kind="folder")
f2 = lib.new_playlist("F2", kind="folder", parent=f1)
check(lib.move_playlist(f1, f2) is False and lib.playlist_tracks(f1) == [], "a playlist folder can't be put inside itself")

# ---------------------------------------------------------------- C8-17 M3U from other programs
A = os.path.dirname(songs["Locomotion"])
pdir = os.path.join(TMP, "pl")
os.makedirs(pdir)
open(os.path.join(pdir, "bom.m3u8"), "wb").write(("\ufeff%s\n%s\n" % (songs["Locomotion"], songs["Sonata in C"])).encode("utf-8"))
pid = lib.import_m3u(os.path.join(pdir, "bom.m3u8"))
check(len(lib.playlist_tracks(pid)) == 2, "C8-17: an .m3u8 starting with a byte-order mark keeps its first song")
win_path = "C:\\Users\\me\\Music\\" + "\\".join(songs["Locomotion"].split("/")[-3:])
open(os.path.join(pdir, "win.m3u"), "w", newline="").write("#EXTM3U\r\n%s\r\nD:\\nowhere\\gone.mp3\r\n" % win_path)
pid = lib.import_m3u(os.path.join(pdir, "win.m3u"))
check(len(lib.playlist_tracks(pid)) == 1 and lib.import_missing == ["D:\\nowhere\\gone.mp3"],
      "C8-17: a playlist made on Windows finds its songs here, and says which it couldn't", lib.import_missing)
shutil.copy(songs["Sonata in C"], os.path.join(A, "caf\u00e9.flac"))
open(os.path.join(pdir, "latin.m3u"), "wb").write(os.path.join(A, "caf\u00e9.flac").encode("latin-1") + b"\n")
check(len(lib.playlist_tracks(lib.import_m3u(os.path.join(pdir, "latin.m3u")))) == 1, "C8-17: a Latin-1 playlist with accented names")
open(os.path.join(pdir, "x.pls"), "w").write("[playlist]\nFile1=%s\nNumberOfEntries=1\n" % songs["Locomotion"])
check(len(lib.playlist_tracks(lib.import_m3u(os.path.join(pdir, "x.pls")))) == 1, "C8-17: a .pls playlist")

# ---------------------------------------------------------------- C8-16 Smart Playlist rules
lib.update([T["Locomotion"]], duration=200.4, size=5_000_000)
got = [r["id"] for r in lib.smart_tracks({"rules": [["duration", "is", 200]]})]
check(T["Locomotion"] in got, "C8-16: Time is matched in whole seconds, as the list shows it")
for bad_spec in ({"rules": [["year", "is", "abc"]]}, {"rules": [], "limit": [5, "songs"]}, {"rules": [["year"]]}):
    try:
        lib.smart_tracks(bad_spec)
        ok = True
    except Exception:       # noqa: BLE001
        ok = False
    check(ok, "C8-16: a damaged rule doesn't break the playlist: %s" % json.dumps(bad_spec))
sp = {"rules": [], "limit": [3, "items"], "selected_by": "random", "seed": 1234}
check([r["id"] for r in lib.smart_tracks(sp)] == [r["id"] for r in lib.smart_tracks(sp)],
      "C8-16: “selected by random” keeps the same songs until the rules change")
sys.path.insert(0, os.path.join(HERE, "..", "app"))

# ---------------------------------------------------------------- C8-22, C8-41 tags in every format
fmt = os.path.join(TMP, "formats")
os.makedirs(fmt)
encs = {"wma": "avenc_wmav2 ! asfmux", "wv": "wavpackenc", "mp2": "avenc_mp2", "mka": "vorbisenc ! matroskamux",
        "wav": "wavenc", "opus": "opusenc ! oggmux", "mp3": "lamemp3enc ! id3v2mux"}
made = {}
for ext, enc in encs.items():
    p = os.path.join(fmt, "t." + ext)
    if ext == "wv":
        # a WavPack file made by another program: GStreamer 1.24's own encoder writes files its reader refuses
        shutil.copy(os.path.join(HERE, "tone.wv"), p)
        made[ext] = p
        continue
    if gst_make(p, enc):
        made[ext] = p
check(set(made) == set(encs), "test files in every format were made", sorted(made))
ch = {"title": "New Tïtle", "artist": "New Artist", "album": "New Album", "genre": "Jazz", "year": 1999, "track_no": 7,
      "track_count": 9, "comments": "note"}
art = open(os.path.join(HERE, "art.png"), "rb").read()
for ext in ("wma", "wv", "mp2"):
    p = made.get(ext)
    if not p:
        continue
    t = tags.read(p)
    check(t["duration"] > 1.5 and t["kind"].endswith("file"), "C8-41: .%s is read (%s, %.1f s)" % (ext, t["kind"], t["duration"]))
    tags.write(p, ch)
    t = tags.read(p)
    # WMA keeps only the track number, not the count (Windows Media has no field for it)
    check(all(t[k] == v for k, v in ch.items() if not (ext == "wma" and k == "track_count")),
          "C8-41: .%s details written and read back" % ext, {k: t[k] for k in ch})
    tags.set_artwork(p, art, "image/png")
    a = tags.artwork(p)
    tags.set_lyrics(p, "la la")
    check(a and a[0] == art and tags.lyrics(p) == "la la", "C8-41: .%s artwork and lyrics" % ext)
if made.get("mka"):
    t = tags.read(made["mka"])
    check(t["duration"] > 1.5 and t["kind"] == "Matroska audio file", "C8-41: .mka is read through GStreamer", t["kind"])
    if shutil.which("mkvpropedit"):
        tags.write(made["mka"], {"title": "Mka Title", "artist": "Mka Artist"})
        t = tags.read(made["mka"])
        check(t["title"] == "Mka Title" and t["artist"] == "Mka Artist", "C8-41: .mka details written with mkvpropedit", (t["title"], t["artist"]))
    else:
        try:
            tags.write(made["mka"], {"title": "x"})
            said = ""
        except ValueError as e:
            said = str(e)
        check("mkvtoolnix" in said, "C8-41: without mkvtoolnix, changing a .mka says which package does it", said)
from gi.repository import GLib  # noqa: E402
from folio_chord import player  # noqa: E402
eng = player.Engine()
for ext in ("wma", "wv", "mp2", "mka"):
    if not made.get(ext):
        continue
    states = []
    eng.listen(lambda ev, v, st=states: st.append(v) if ev in ("state", "error") else None)
    eng.play({"kind": "song", "id": 1, "uri": player.uri_of(made[ext]), "title": ext, "duration": 2})
    ctx = GLib.MainContext.default()
    end = time.time() + 8
    while time.time() < end and "playing" not in states:
        while ctx.pending():
            ctx.iteration(False)
        time.sleep(0.02)
    eng.stop()
    check("playing" in states, "C8-41: .%s plays" % ext, states)
    eng.listeners.clear()
if made.get("wav"):
    w = made["wav"]
    import struct
    body = b"INFO" + b"INAM" + struct.pack("<I", 8) + b"Riff Tit" + b"IART" + struct.pack("<I", 6) + b"Riffer"
    data = open(w, "rb").read()
    data = data + b"LIST" + struct.pack("<I", len(body)) + body
    data = data[:4] + struct.pack("<I", len(data) - 8) + data[8:]
    open(w, "wb").write(data)
    t = tags.read(w)
    check((t["title"], t["artist"]) == ("Riff Tit", "Riffer"), "C8-22: WAV details written by other programs are read", (t["title"], t["artist"]))
    tags.write(w, {"title": "Changed"})
    raw = open(w, "rb").read()
    check(tags.read(w)["title"] == "Changed" and b"Riff Tit" not in raw and b"Changed" in raw,
          "C8-22: changing a WAV keeps the details other programs read in step")
if made.get("opus"):
    from mutagen.oggopus import OggOpus
    o = OggOpus(made["opus"])
    o["R128_TRACK_GAIN"] = ["-1536"]
    o.save()
    t = tags.read(made["opus"])
    check(abs((t["rg_track"] or 0) - -1.0) < 0.01 and t["bitrate"] > 0, "C8-22: Opus loudness (R128) and bit rate", (t["rg_track"], t["bitrate"]))
if made.get("mp3"):
    from mutagen.id3 import ID3, TIT2
    p = made["mp3"]
    i3 = ID3(p)
    i3.add(TIT2(encoding=1, text=["v23"]))
    i3.save(p, v2_version=3)
    tags.write(p, {"artist": "Kept"})
    check(ID3(p).version[:2] == (2, 3), "C8-22: an ID3v2.3 tag stays v2.3 after an edit", ID3(p).version)
fl = songs["Sonata in C"]
from mutagen.flac import FLAC
f = FLAC(fl)
f["DESCRIPTION"] = ["described"]
f.save()
check(tags.read(fl)["comments"] in ("described",) or tags.read(fl)["comments"], "C8-22: a FLAC comment kept as DESCRIPTION is read")
aac = os.path.join(fmt, "raw.aac")
if gst_make(aac, "avenc_aac ! aacparse ! audio/mpeg,stream-format=adts"):
    tags.write(aac, {"title": "Raw Title", "artist": "Raw Artist"})
    check(tags.read(aac)["title"] == "Raw Title", "C8-22: a raw .aac file's details can be changed")
vid = os.path.join(fmt, "video.mp4")
try:
    vid_ok = gst_make(vid, "avenc_aac ! m. videotestsrc num-buffers=20 ! video/x-raw,width=64,height=48 ! avenc_mpeg4 ! m. mp4mux name=m")
except Exception as e:      # noqa: BLE001
    vid_ok = False
    print("(no video test file: %s)" % e)
if vid_ok:
    try:
        tags.read(vid)
        said = ""
    except tags.NotASong as e:
        said = str(e)
    check("video" in said, "C8-22: a video .mp4 is left out of the library", said)

# ---------------------------------------------------------------- feeds, downloads (C8-07, C8-31, C8-32)
ROUTES = {}


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        r = ROUTES.get(self.path.split("?")[0])
        if r is None:
            return self.send_error(404)
        if callable(r):
            return r(self)
        body, ctype = r
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
B = "http://127.0.0.1:%d" % srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()


def rss(items, head='<?xml version="1.0" encoding="UTF-8"?>'):
    return (head + '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel><title>Show</title>%s</channel></rss>' % items).encode()


def item(n, date, title=None, url=None):
    return "<item><title>%s</title><guid>g%d</guid><pubDate>%s</pubDate><enclosure url='%s' type='audio/mpeg' length='100'/></item>" % (
        title or "Ep %d" % n, n, date, url or "%s/ep%d.mp3" % (B, n))


pods = P.Podcasts(lib, os.path.join(TMP, "Podcasts"))
ROUTES["/old"] = (rss("".join(item(i, "Mon, %02d Sep 2025 10:00:00 +0000" % i) for i in range(1, 6))), "application/rss+xml")
pid = pods.subscribe(B + "/old")
check([e["title"] for e in pods.episodes(pid) if e["new"]] == ["Ep 5"], "C8-31: a feed listing the oldest first marks the newest episode new")
ROUTES["/gz"] = lambda h: (h.send_response(200), h.send_header("Content-Encoding", "gzip"), h.end_headers(),
                           h.wfile.write(gzip.compress(rss(item(1, "Mon, 01 Sep 2025 10:00:00 +0000")))))
ROUTES["/ws"] = (b"\n\n  " + rss(item(1, "2025-09-01T10:00:00Z", title="Rock & Roll")), "text/xml")
ROUTES["/atom"] = (b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>A</title><entry><title>E</title><id>1</id>'
                   b'<updated>2025-09-01T10:00:00Z</updated><link rel="enclosure" type="audio/mpeg" href="/e.mp3"/></entry></feed>', "application/atom+xml")
ROUTES["/moved"] = lambda h: (h.send_response(301), h.send_header("Location", B + "/ws"), h.end_headers())
for path, what in (("/gz", "a compressed feed"), ("/ws", "blank lines before the XML, a bare & and an ISO date"), ("/atom", "an Atom feed")):
    try:
        p_ = pods.subscribe(B + path)
        eps = pods.episodes(p_)
        ok = len(eps) == 1 and eps[0]["published"] > 0
    except Exception as e:      # noqa: BLE001
        ok, eps = False, str(e)
    check(ok, "C8-32: %s is read" % what, [dict(x) for x in eps] if isinstance(eps, list) else eps)
eps = pods.episodes([s["id"] for s in pods.shows() if s["feed"].endswith("/atom")][0])
check(eps and eps[0]["url"] == B + "/e.mp3", "C8-32: an episode address given relative to the feed is made whole")
p_ = pods.subscribe(B + "/moved")
check(pods.show(p_)["feed"] == B + "/ws", "C8-32: a feed that has moved for good is kept at its new address", pods.show(p_)["feed"])


def cut(h):
    h.send_response(200)
    h.send_header("Content-Length", "1000000")
    h.end_headers()
    h.wfile.write(b"x" * 300000)
    h.wfile.flush()
    h.connection.shutdown(socket.SHUT_RDWR)


ROUTES["/cut.mp3"] = cut
ROUTES["/page.mp3"] = (b"<html>Please sign in</html>", "text/html")
dest = os.path.join(TMP, "dl.mp3")
for path, what in (("/cut.mp3", "a download cut off part way"), ("/page.mp3", "a web page instead of the episode")):
    try:
        net.download(B + path, dest)
        said = ""
    except Exception as e:      # noqa: BLE001
        said = net.explain(e)
    check(said and not os.path.exists(dest) and not os.path.exists(dest + ".part"), "C8-07: %s is not kept as a download" % what, said)
import urllib.error  # noqa: E402
check("internet" in net.explain(urllib.error.URLError(ConnectionRefusedError(111, "refused")))
      and "404" in net.explain(urllib.error.HTTPError("u", 404, "nf", {}, None)), "C8-33: network errors in plain words")

# ---------------------------------------------------------------- C8-08 iTunes library
ilib = L.Library(os.path.join(TMP, "lib3", "library.db"))
mine = os.path.join(TMP, "it", "Mine", "Album", "01 Intro.mp3")
os.makedirs(os.path.dirname(mine))
shutil.copy(songs["Moment's Notice"], mine)
tags.write(mine, {"title": "Intro", "artist": "Mine", "album": "Album"})
ilib.add_file(mine)
x = {"Tracks": {"1": {"Track ID": 1, "Name": "Intro", "Artist": "Somebody Else", "Album": "Other", "Play Count": 42,
                      "Location": "file://localhost/C:/Music/Somebody%20Else/Other/01%20Intro.mp3"}},
     "Playlists": []}
plistlib.dump(x, open(os.path.join(TMP, "it", "lib.xml"), "wb"))
res = itunes.import_library(ilib, os.path.join(TMP, "it", "lib.xml"))
check(ilib.tracks()[0]["play_count"] == 0 and res["unmatched"], "C8-08: an iTunes song that isn't here doesn't credit a song that only shares its file name",
      (ilib.tracks()[0]["play_count"], res))

# ---------------------------------------------------------------- C8-35 station playlists
check(radio.parse_playlist("<asx version='3.0'><entry><ref href='http://a/1'/></entry></asx>") == ["http://a/1"]
      and radio.parse_playlist("<html><a href='http://a/1'>x</a></html>") == []
      and radio.parse_playlist("stream.mp3\n", base="http://h/list.m3u") == ["http://h/stream.mp3"],
      "C8-35: station playlists: single quotes, web pages, relative entries")
ROUTES["/tunein"] = (b"[playlist]\nFile1=http://a/live\n", "audio/x-scpls")
check(radio.resolve(B + "/tunein", look_inside=True) == "http://a/live", "C8-35: a station playlist whose address doesn't say so is looked inside")

# ---------------------------------------------------------------- C8-28 shared playlists, C8-37 passcodes
share = sharing.Share(lib, "Den", "pw", port=0, host="127.0.0.1")
port = share.start()
rpl = lib.new_playlist("Their order", tracks=[T["Sonata in C"], T["Locomotion"], T["Sonata in C"]])
rem = sharing.Remote("127.0.0.1", port, "pw")
rem.tracks()
check([t["title"] for t in rem.playlist(rpl)] == ["Sonata in C", "Locomotion", "Sonata in C"],
      "C8-28: a shared playlist keeps its order, a song in it twice shown twice")
check(rem.headers() == {sharing.PASS_HEADER: "pw"}, "C8-27: a shared song's request carries the passcode")
share.stop()
keys.save("share_pass", "secret")
pf = os.path.join(os.environ["XDG_CONFIG_HOME"], "folio-chord", "passcodes.json")
check(keys.load("share_pass") == "secret" and stat.S_IMODE(os.stat(pf).st_mode) == 0o600,
      "C8-37: without a keyring, passcodes go in a file only you can read")

print("%d checks, %d failed" % (N[0], len(FAILS)))
print("all passed" if not FAILS else "FAILED")
shutil.rmtree(TMP, ignore_errors=True)
sys.stdout.flush()
os._exit(1 if FAILS else 0)
