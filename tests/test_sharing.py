"""Home Sharing tests (C4-01): a library offered to the network, found by the question asked on it,
read over HTTP and streamed a piece at a time, with the passcode honoured."""
import os
import sys
import tempfile
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
import mkaudio  # noqa: E402
from folio_chord import library as L, sharing  # noqa: E402

FAILS = []
N = [0]


def check(ok, what, info=None):
    N[0] += 1
    print(("ok   " if ok else "FAIL ") + what + ("" if ok or info is None else "  -- %r" % (info,)))
    if not ok:
        FAILS.append(what)


T = tempfile.mkdtemp(prefix="chord-share-")
music = os.path.join(T, "music")
songs = mkaudio.make(music, 1.0)
lib = L.Library(os.path.join(T, "lib.db"))
lib.add_folder(music)
lib.scan()
rows = lib.tracks()
check(len(rows) >= 6, "the test library has its songs", len(rows))
pid = lib.new_playlist("Favourites", tracks=[r["id"] for r in rows[:3]])

share = sharing.Share(lib, name="Test Library", port=0, host="127.0.0.1")
port = share.start()
check(port > 0, "sharing starts on a port of its own", port)
rem = sharing.Remote("127.0.0.1", port)
info = rem.info()
check(info["folio"] == "share" and info["name"] == "Test Library" and info["songs"] == len(rows),
      "another Chord sees the name and how many songs there are", info)
check(info["needs_pass"] is False, "and that no passcode is needed")

ts = rem.tracks()
check(len(ts) == len(rows) and ts[0]["title"] and ts[0]["duration"], "the songs come across with their details", ts[:1])
check(all(t["path"].startswith("http://127.0.0.1:%d/folio/stream/" % port) for t in ts),
      "each song is played from the shared library, not from a file", ts[0]["path"])
pls = rem.playlists()
check([p["name"] for p in pls if p["id"] == pid] == ["Favourites"], "its playlists are listed", pls)
inpl = rem.playlist(pid)
check(len(inpl) == 3 and all(t["id"] in {r["id"] for r in rows[:3]} for t in inpl),
      "and a playlist gives the songs in it", len(inpl))

# the file itself, whole and a piece at a time (what GStreamer does to seek)
first = [r for r in rows if r["id"] == ts[0]["id"]][0]
size = os.path.getsize(first["path"])
whole = urllib.request.urlopen(ts[0]["path"], timeout=20)
data = whole.read()
check(len(data) == size and whole.headers.get("Accept-Ranges") == "bytes",
      "a song streams whole, and says it can be asked for in pieces", (len(data), size))
req = urllib.request.Request(ts[0]["path"], headers={"Range": "bytes=10-109"})
with urllib.request.urlopen(req, timeout=20) as r2:
    piece = r2.read()
    code, crange = r2.status, r2.headers.get("Content-Range")
check(code == 206 and len(piece) == 100 and piece == data[10:110] and crange == "bytes 10-109/%d" % size,
      "a piece in the middle comes back as that piece", (code, len(piece), crange))
try:
    urllib.request.urlopen("http://127.0.0.1:%d/folio/stream/999999" % port, timeout=10)
    check(False, "a song that isn't there is refused", "no error")
except urllib.error.HTTPError as e:
    check(e.code == 404, "a song that isn't there is refused", e.code)

# the question asked on the local network
seen = sharing.probe(timeout=1.0, port=port, addresses=["127.0.0.1"])
check(any(d["name"] == "Test Library" and d["port"] == port for d in seen),
      "the shared library answers the question asked on the network", seen)
share.stop()
check(sharing.probe(timeout=0.4, port=port, addresses=["127.0.0.1"]) == [],
      "and stops answering when sharing is turned off")
check(not rem.reachable(), "a library that has stopped sharing is reported as away")

# a passcode
share2 = sharing.Share(lib, name="Locked", passcode="s3cret", port=0, host="127.0.0.1")
p2 = share2.start()
open2 = sharing.Remote("127.0.0.1", p2)
check(open2.info()["needs_pass"] is True, "a locked library still says who it is")
try:
    open2.tracks()
    check(False, "without the passcode it gives nothing away", "no error")
except urllib.error.HTTPError as e:
    check(e.code == 403, "without the passcode it gives nothing away", e.code)
with_pass = sharing.Remote("127.0.0.1", p2, passcode="s3cret")
check(len(with_pass.tracks()) == len(rows), "with the passcode it opens")
share2.stop()

print("%d checks, %d failed" % (N[0], len(FAILS)))
print("all passed" if not FAILS else "FAILED")
sys.stdout.flush()
sys.exit(1 if FAILS else 0)
