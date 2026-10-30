"""Engine tests (no window): tags in every format, the library and its folders, Smart Playlists,
play order, and playback through GStreamer (to a fake sink): gapless, Sound Check, equalizer,
crossfade, start/stop times."""
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
from folio_chord import library as L, playqueue, tags  # noqa: E402

FAILS = []
N = [0]


def check(ok, what, info=None):
    N[0] += 1
    print(("ok   " if ok else "FAIL ") + what + ("" if ok or info is None else "  -- %r" % (info,)))
    if not ok:
        FAILS.append(what)


T = tempfile.mkdtemp()
MUSIC = os.path.join(T, "Music")
songs = mkaudio.make(MUSIC)

# ---------------------------------------------------------------- tags, every format
for title, p in songs.items():
    t = tags.read(p)
    ext = os.path.splitext(p)[1]
    check(t["title"] == title and t["artist"] and t["album"] and t["track_no"] >= 1 and t["year"] > 1900
          and 1.5 < t["duration"] < 3.0, "read tags and length: %s" % ext, (t["title"], t["track_no"], t["year"], t["duration"]))
    check(t["kind"].endswith("audio file"), "kind %s: %s" % (ext, t["kind"]))
for p in songs.values():
    ext = os.path.splitext(p)[1]
    tags.write(p, {"comments": "liner note", "composer": "J. C.", "disc_no": 1, "disc_count": 2, "bpm": 120,
                   "album_artist": "Various", "compilation": True})
    t = tags.read(p)
    check(t["comments"] == "liner note" and t["composer"] == "J. C." and (t["disc_no"], t["disc_count"]) == (1, 2)
          and t["album_artist"] == "Various" and t["compilation"] and t["title"], "write tags: %s" % ext,
          (t["comments"], t["composer"], t["disc_no"], t["disc_count"], t["album_artist"], t["compilation"]))
    tags.write(p, {"comments": "", "album_artist": "", "compilation": False})
    t = tags.read(p)
    check(not t["comments"] and not t["album_artist"] and not t["compilation"], "clear tags: %s" % ext)
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02\x08\x02\x00\x00\x00\xfd\xd4\x9as"
       b"\x00\x00\x00\x16IDATx\x9cc\xf8\xcf\xc0\xc0\xc0\xf0\x9f\x81\x81\x81\x01\x00\x0b\xf4\x02\xfe\x1a\x8b\x89\x8b"
       b"\x00\x00\x00\x00IEND\xaeB`\x82")
for p in songs.values():
    ext = os.path.splitext(p)[1]
    tags.set_artwork(p, PNG, "image/png")
    a = tags.artwork(p)
    check(a is not None and a[0] == PNG and a[1] == "image/png" and tags.read(p)["has_art"], "artwork: %s" % ext)
p0 = songs["Sonata in C"]
tags.set_artwork(p0, None)
check(tags.artwork(p0) is None, "remove artwork")

# ---------------------------------------------------------------- library
lib = L.Library(os.path.join(T, "data", "library.db"))
check([p["name"] for p in lib.playlists()] == ["90's Music", "Classical Music", "My Top Rated", "Recently Added",
                                               "Recently Played", "Top 25 Most Played"], "iTunes' Smart Playlists to start with")
lib.add_folder(MUSIC)
n, gone = lib.scan()
rows = lib.tracks()
check(n == 7 and len(rows) == 7, "scan the music folder: 7 songs", n)
check([r["title"] for r in rows][:4] == ["Blue Train", "Moment's Notice", "Locomotion", "Lazy Bird"], "album order by track number",
      [r["title"] for r in rows])
check(lib.browse(rows, "genre") == ["Classical", "Jazz", "Rock"], "column browser: genres")
check(lib.browse(rows, "artist") == ["Coltrane Quartet", "Hall Ensemble", "The Garage"], "column browser: artists")
check(lib.stats(rows).startswith("7 songs, "), "status line", lib.stats(rows))
n2, _ = lib.scan()
check(n2 == 7 and len(lib.tracks()) == 7, "rescan: nothing doubled")
os.remove(songs["Grunge Waltz"])
_, gone = lib.scan()
check(gone == 1 and len(lib.tracks()) == 6, "a deleted file drops out")
mkaudio.tone(songs["Grunge Waltz"], 2.0, 349)
tags.write(songs["Grunge Waltz"], {"title": "Grunge Waltz", "artist": "The Garage", "album": "Loud Nineties",
                                   "genre": "Rock", "year": 1996, "track_no": 2})
lib.scan()
check(len(lib.tracks()) == 7, "and comes back")
ids = {r["title"]: r["id"] for r in lib.tracks()}
lib.rate([ids["Blue Train"]], 100)
lib.rate([ids["Lazy Bird"]], 80)
lib.rate([ids["Locomotion"]], 40)
for _ in range(3):
    lib.played(ids["Locomotion"])
lib.played(ids["Blue Train"])
sp = {p["name"]: p["id"] for p in lib.playlists()}
titles = lambda pid: [r["title"] for r in lib.playlist_tracks(pid)]  # noqa: E731
check(sorted(titles(sp["90's Music"])) == ["Grunge Waltz", "Teen Spirit Cover"], "90's Music")
check(titles(sp["Classical Music"]) == ["Sonata in C"], "Classical Music")
check(sorted(titles(sp["My Top Rated"])) == ["Blue Train", "Lazy Bird"], "My Top Rated (4 stars and up)")
check(titles(sp["Top 25 Most Played"]) == ["Locomotion", "Blue Train"], "Top 25 Most Played")
check(sorted(titles(sp["Recently Played"])) == ["Blue Train", "Locomotion"], "Recently Played")
check(len(titles(sp["Recently Added"])) == 7, "Recently Added")
spec = {"match": "any", "rules": [["artist", "contains", "garage"], ["rating", "is", 100]]}
pid = lib.new_playlist("Mix", kind="smart", rules=spec)
check(sorted(titles(pid)) == ["Blue Train", "Grunge Waltz", "Teen Spirit Cover"], "match any of the rules")
lib.set_rules(pid, {"match": "all", "rules": [["genre", "is", "jazz"]], "limit": [2, "items"], "selected_by": "highest rating"})
check(titles(pid) == ["Blue Train", "Lazy Bird"], "limit to 2 songs selected by highest rating")
lib.set_rules(pid, {"match": "all", "rules": [["genre", "is", "jazz"]], "limit": [5, "minutes"], "selected_by": "album"})
check(len(titles(pid)) == 4, "limit by minutes")
lib.set_rules(pid, {"match": "all", "rules": [["title", "begins with", "L"], ["year", "is in the range", 1950, 1960]]})
check(sorted(titles(pid)) == ["Lazy Bird", "Locomotion"], "begins with, and a year range")
lib.set_rules(pid, {"match": "all", "rules": [["title", "contains", "50%_"]]})
check(titles(pid) == [], "wildcards in rules are taken literally")
lib.update([ids["Sonata in C"]], checked=0)
lib.set_rules(pid, {"match": "all", "rules": [["genre", "is", "classical"]], "checked_only": True})
check(titles(pid) == [], "match only checked songs")
# playlists and folders
pl = lib.new_playlist("Road Trip", tracks=[ids["Lazy Bird"], ids["Blue Train"]])
lib.add_to_playlist(pl, [ids["Grunge Waltz"]], at=1)
check(titles(pl) == ["Lazy Bird", "Grunge Waltz", "Blue Train"], "playlist keeps its order; insert at a place")
lib.reorder_playlist(pl, [2], 0)
check(titles(pl) == ["Blue Train", "Lazy Bird", "Grunge Waltz"], "drag to reorder")
lib.remove_from_playlist(pl, [1])
check(titles(pl) == ["Blue Train", "Grunge Waltz"], "remove from playlist")
fo = lib.new_playlist("Summer", kind="folder")
pl2 = lib.new_playlist("Beach", tracks=[ids["Teen Spirit Cover"]])
lib.move_playlist(pl, fo)
lib.move_playlist(pl2, fo)
check(titles(fo) == ["Blue Train", "Grunge Waltz", "Teen Spirit Cover"], "a playlist folder plays everything in it")
m3u = os.path.join(T, "trip.m3u")
lib.export_m3u(lib.playlist_tracks(pl), m3u)
p3 = lib.import_m3u(m3u, "Trip again")
check(titles(p3) == ["Blue Train", "Grunge Waltz"], "M3U export and import")
lib.delete_playlist(fo)
check(lib.playlist(pl)["parent"] is None and lib.playlist(fo) is None, "deleting a folder keeps its playlists")

# ---------------------------------------------------------------- play order
import random  # noqa: E402
q = playqueue.PlayQueue(random.Random(4))
q.start([1, 2, 3, 4], 1)
check([q.current, q.advance(), q.advance(), q.advance()] == [2, 3, 4, None], "plays on from the song started")
q.start([1, 2, 3, 4], 2)
q.set_repeat("all")
check([q.advance(), q.advance(), q.advance()] == [4, 1, 2], "repeat all wraps round")
q.set_repeat("one")
check(q.advance() == 2 and q.advance(user=True) == 3, "repeat one; Next still moves on")
q.set_repeat("off")
q.start([1, 2, 3, 4], 0)
q.play_next([9])
q.add([8])
check(q.upcoming()[:3] == [9, 8, 2] and [q.advance(), q.advance(), q.advance()] == [9, 8, 2], "Up Next first, Play Next before Add")
check(q.back() == 1, "previous")
q.set_shuffle(True)
q.start(list(range(1, 21)), 4)
seen = [q.current] + [q.advance() for _ in range(19)]
check(seen[0] == 5 and sorted(seen) == list(range(1, 21)) and seen != list(range(1, 21))[4:] + list(range(1, 5)),
      "shuffle: every song once, the chosen one first")
q.album_of = lambda i: i // 5
q.set_shuffle(True, "albums")
q.start(list(range(0, 15)), 7)
seen = [q.current] + [q.advance() for _ in range(14)]
groups = [s // 5 for s in seen]
check(seen[0] == 7 and groups == sorted(groups, key=lambda g: groups.index(g)), "shuffle by album keeps albums together", seen)
q.set_shuffle(False)

# ---------------------------------------------------------------- playback
from gi.repository import GLib  # noqa: E402
from folio_chord import player  # noqa: E402

eng = player.Engine()
events = []
eng.listen(lambda ev, v: events.append((ev, v if not isinstance(v, dict) else v.get("title"))))


def spin(secs, until=None):
    ctx = GLib.MainContext.default()
    end = time.time() + secs
    while time.time() < end:
        while ctx.pending():
            ctx.iteration(False)
        if until and until():
            return True
        time.sleep(0.01)
    return bool(until and until())


def item(title, **kw):
    r = lib.tracks("title=?", (title,))[0]
    d = {"uri": player.uri_of(r["path"]), "title": title, "id": r["id"], "duration": r["duration"], "rg": None}
    d.update(kw)
    return d


order = ["Blue Train", "Moment's Notice", "Locomotion"]
left = list(order[1:])
eng.play(item(order[0]), lambda: item(left.pop(0)) if left else None)
ok = spin(15, lambda: ("state", "stopped") in events)
tracks = [v for e, v in events if e == "track"]
check(ok and tracks == order, "plays three songs one after another (gapless hand-over)", tracks)
check([v for e, v in events if e == "eos"] == order, "each song's end reported once (play counts)")
events.clear()
eng.play(item("Lazy Bird"))
spin(1.0, lambda: eng.state == "playing")
spin(0.5)
eng.pause()
p1 = eng.position()
spin(0.6)
check(eng.state == "paused" and abs(eng.position() - p1) < 0.05 and p1 > 0.1, "pause holds the place", (eng.state, p1))
eng.resume()
spin(0.3)
eng.seek(1.5)
spin(0.3)
check(eng.position() >= 1.5, "seek", eng.position())
eng.stop()
check(eng.state == "stopped", "stop")
# Sound Check and the equalizer drive the gain element
eng.set_sound_check(True)
it = item("Locomotion", rg=-6.0)
check(abs(eng.gain_db(it) + 6.0) < 1e-6, "Sound Check applies the song's ReplayGain")
eng.set_sound_check(False)
check(eng.gain_db(it) == 0, "Sound Check off")
eng.set_eq(True, *player.PRESETS["Rock"])
eng.play(item("Blue Train"))
spin(0.5)
check(abs(eng.cur.eq.get_property("band0") - 5.0) < 1e-6 and abs(eng.cur.eq.get_property("band9") - 4.5) < 1e-6,
      "equalizer preset reaches the filter")
eng.set_eq(False)
check(eng.cur.eq.get_property("band0") == 0.0, "equalizer off is flat")
check(len(player.PRESETS) == 22 and all(len(b) == 10 for _p, b in player.PRESETS.values()), "iTunes' 22 presets, ten bands")
eng.stop()
# volume adjust
check(abs(eng.gain_db({"volume_adjust": 50}) - 6.0) < 1e-6, "per-song volume adjustment")
# stop time
events.clear()
eng.play(item("Blue Train", stop=0.8))
ok = spin(4, lambda: ("eos", "Blue Train") in events)
check(ok and eng.position() < 1.5, "stop time ends the song early")
# crossfade
events.clear()
eng.crossfade = 0.6
left = ["Locomotion"]
eng.play(item("Moment's Notice"), lambda: item(left.pop(0)) if left else None)
saw_both = []


def both():
    if eng._fading:
        saw_both.append((eng.a.fade, eng.b.fade))
    return ("state", "stopped") in events
spin(10, both)
check(saw_both and any(0.1 < a < 0.9 for a, b in saw_both), "crossfade: both songs play while one fades out", saw_both[:3])
check([v for e, v in events if e == "track"] == ["Moment's Notice", "Locomotion"], "crossfade moves to the next song")
eng.crossfade = 0
# spectrum for the visualizer
events.clear()
eng.set_spectrum(True)
eng.play(item("Blue Train"))
spin(1.5, lambda: any(e == "spectrum" for e, v in events))
check(any(e == "spectrum" for e, v in events), "spectrum for the visualizer")
eng.set_spectrum(False)
eng.stop()
shutil.rmtree(T)
print("%d checks, %d failed" % (N[0], len(FAILS)))
print("all passed" if not FAILS else "FAILED")
sys.exit(1 if FAILS else 0)
