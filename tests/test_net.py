"""Radio and podcast tests against a stand-in for the internet (netstub): the radio directory,
favourites, playing a stream with its song title; Apple's podcast search and charts, Podcast
Index with its signed requests, feeds, subscriptions, refresh, downloads, played marks, OPML."""
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
os.environ.setdefault("FOLIO_CHORD_AUDIOSINK", "fakesink")
import mkaudio  # noqa: E402
import netstub  # noqa: E402

T = tempfile.mkdtemp()
ogg = os.path.join(T, "tone.ogg")
mkaudio.tone(ogg, 3.0)
stub = netstub.Stub(ogg)
os.environ["FOLIO_CHORD_RADIO_API"] = stub.base
os.environ["FOLIO_CHORD_APPLE_API"] = stub.base
os.environ["FOLIO_CHORD_PODCASTINDEX_API"] = stub.base + "/pi"
from folio_chord import library as L, net, podcasts as P, radio as R  # noqa: E402

FAILS = []
N = [0]


def check(ok, what, info=None):
    N[0] += 1
    print(("ok   " if ok else "FAIL ") + what + ("" if ok or info is None else "  -- %r" % (info,)))
    if not ok:
        FAILS.append(what)


lib = L.Library(os.path.join(T, "lib.db"))
# ---------------------------------------------------------------- radio
d = R.Directory()
r = d.search(name="test", order="votes")
check([s["name"] for s in r] == ["Jazz FM Test", "Rock Radio Test", "News Talk Test"], "search stations by name, most votes first")
check(r[0]["tags"] == ["jazz", "smooth jazz"] and r[0]["countrycode"] == "NL" and r[0]["bitrate"] == 128 and r[0]["url"].startswith(stub.base),
      "a station's details")
check([s["name"] for s in d.search(tag="rock")] == ["Rock Radio Test"], "by tag")
check([s["name"] for s in d.search(countrycode="DE")] == ["News Talk Test"], "by country")
check([s["name"] for s in d.search(language="dutch")] == ["Jazz FM Test"], "by language")
check(d.tags()[0][0] == "rock" and d.countries()[0] == ("Netherlands", 1, "NL") and d.languages()[0][0] == "english",
      "tag, country and language lists")
q = [h for h in stub.hits if h[0] == "/json/stations/search"][0]
check(q[1].get("hidebroken") == "true" and q[2].get("User-Agent", "").startswith("FolioChord/"), "asks without broken stations, says who it is")
d.clicked(r[0])
check(any(h[0] == "/json/url/u-jazz" for h in stub.hits), "a played station is counted, as the directory asks")
check(R.servers() == [stub.base], "server from the setting")
R.set_favourite(lib, r[0], True)
R.set_favourite(lib, r[1], True)
R.set_favourite(lib, r[0], False)
check([s["name"] for s in R.favourites(lib)] == ["Rock Radio Test"] and R.is_favourite(lib, r[1]), "favourites")
R.played(lib, r[2])
R.played(lib, r[1])
R.played(lib, r[2])
check([s["name"] for s in R.recent(lib)] == ["News Talk Test", "Rock Radio Test"], "recently played stations")
check([s["uuid"] for s in d.by_uuid(["u-rock"])] == ["u-rock"], "look stations up again by id")
# a stream plays, and its song title arrives
from gi.repository import GLib  # noqa: E402
from folio_chord import player  # noqa: E402
eng = player.Engine()
ev = []
eng.listen(lambda e, v: ev.append((e, v)))
eng.play({"uri": r[0]["url"], "title": r[0]["name"], "stream": True})
end = time.time() + 8
while time.time() < end and eng.state != "playing":
    while GLib.MainContext.default().pending():
        GLib.MainContext.default().iteration(False)
    time.sleep(0.01)
check(eng.state == "playing", "a station plays", (eng.state, ev[-3:]))
end = time.time() + 6
while time.time() < end and not any(e == "tags" and v.get("title") == stub.TITLE for e, v in ev):
    while GLib.MainContext.default().pending():
        GLib.MainContext.default().iteration(False)
    time.sleep(0.01)
check(any(e == "tags" and v.get("title") == stub.TITLE for e, v in ev), "the song playing on the station (stream title)",
      [v for e, v in ev if e == "tags"])
eng.stop()

# ---------------------------------------------------------------- podcast directories
a = P.Apple()
res = a.search("show")
check([s["title"] for s in res] == ["Tech Show", "Garden Show"] and res[0]["feed"].endswith("/feed/tech"),
      "Apple's podcast search (shows without a feed left out)")
h = [x for x in stub.hits if x[0] == "/search"][-1][1]
check(h.get("media") == "podcast" and h.get("entity") == "podcast" and h.get("country") == "us", "asks for podcasts in a country")
ch = a.charts("nl", 26)
check([s["title"] for s in ch] == ["Garden Show", "Tech Show"], "charts, in chart order")
check([s["title"] for s in a.charts("nl", 1318)] == ["Tech Show"], "charts for a category")
check(any("/nl/rss/toppodcasts/" in x[0] for x in stub.hits), "the country's chart")
pi = P.PodcastIndex("k", "s")
check([s["title"] for s in pi.search("tech")] == ["Tech Show"], "Podcast Index search, signed request accepted")
bad = P.PodcastIndex("k", "wrong")
try:
    bad.search("tech")
    check(False, "a wrong Podcast Index secret is refused")
except Exception:
    check(True, "a wrong Podcast Index secret is refused")
try:
    P.PodcastIndex("", "").search("x")
    check(False, "without a key: says what's needed")
except ValueError as e:
    check("Options" in str(e), "without a key: says what's needed")
check(isinstance(P.directory({}), P.Apple) and isinstance(P.directory({"podcast_directory": "podcastindex"}), P.PodcastIndex),
      "Apple's directory unless Options says Podcast Index")

# ---------------------------------------------------------------- subscriptions
pods = P.Podcasts(lib, os.path.join(T, "Podcasts"))
pid = pods.subscribe(stub.base + "/feed/tech")
s = pods.show(pid)
eps = pods.episodes(pid)
check(s["title"] == "Tech Show" and s["author"] == "Tech Media" and s["genre"] == "Technology" and s["artwork"].endswith("tech.png"),
      "subscribe: the show")
check([e["title"] for e in eps] == ["Tech episode 3", "Tech episode 2", "Tech episode 1"] and eps[0]["duration"] == 2.0,
      "episodes, newest first, with their length", [(e["title"], e["published"], e["duration"]) for e in eps])
check(P.plain(eps[0]["description"]) == "Notes for 3", "show notes as text")
check(pods.to_download() == [eps[0]["id"]], "only the newest is new when you subscribe")
stub.feeds_n["tech"] = 5
new = pods.refresh(pid)
check(len(new) == 2 and len(pods.episodes(pid)) == 5, "refresh finds the new episodes")
check(len(pods.to_download()) == 3, "new episodes are downloaded automatically")
pods.set_auto_download(pid, False)
check(pods.to_download() == [], "unless the show is set not to")
e5 = pods.episodes(pid)[0]
f = pods.download(e5["id"])
check(f and os.path.exists(f) and open(f, "rb").read()[:4] == b"OggS" and pods.episode(e5["id"])["file"] == f, "download an episode")
pods.set(e5["id"], position=1.2)
check(pods.episode(e5["id"])["position"] == 1.2, "where you stopped is kept")
pods.mark_played([e5["id"]])
e = pods.episode(e5["id"])
check(e["played"] == 1 and e["position"] == 0, "mark as played")
check(pods.shows()[0]["unplayed"] == 4, "unplayed count")
pods.delete_download(e5["id"])
check(not os.path.exists(f) and pods.episode(e5["id"])["file"] is None, "remove the download")
pid2 = pods.subscribe(stub.base + "/feed/garden")
opml = os.path.join(T, "subs.opml")
pods.export_opml(opml)
got = P.Podcasts.read_opml(opml)
check(got == [("Garden Show", stub.base + "/feed/garden"), ("Tech Show", stub.base + "/feed/tech")], "OPML export", got)
pods.unsubscribe(pid2)
check([p["title"] for p in pods.shows()] == ["Tech Show"], "unsubscribe")
lib2 = L.Library(os.path.join(T, "lib2.db"))
pods2 = P.Podcasts(lib2, os.path.join(T, "P2"))
for title, url in P.Podcasts.read_opml(opml):
    pods2.subscribe(url)
check(len(pods2.shows()) == 2, "OPML import")
ok = net.download(stub.base + "/ep/tech-1.ogg", os.path.join(T, "x.ogg"), stop=lambda: True)
check(ok is False and not os.path.exists(os.path.join(T, "x.ogg.part")), "a download can be stopped")
stub.stop()
shutil.rmtree(T)
print("%d checks, %d failed" % (N[0], len(FAILS)))
print("all passed" if not FAILS else "FAILED")
sys.exit(1 if FAILS else 0)
