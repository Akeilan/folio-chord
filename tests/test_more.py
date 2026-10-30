"""Engine tests for Chord 0.2 (C3-13 to C3-26): nested and Playlist rules, lyrics, organizing the
music folder (and undo), importing an iTunes library, station playlists, measuring loudness,
watching folders, per-song equalizer, playback speed with the pitch kept, sound outputs."""
import datetime
import os
import plistlib
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
sys.path.insert(0, HERE)
os.environ.setdefault("FOLIO_CHORD_AUDIOSINK", "fakesink")
import mkaudio  # noqa: E402
from gi.repository import GLib  # noqa: E402
from folio_chord import analysis, itunes, library as L, organize, player, radio, tags, watcher  # noqa: E402

FAILS = []
N = [0]


def check(ok, what, info=None):
    N[0] += 1
    print(("ok   " if ok else "FAIL ") + what + ("" if ok or info is None else "  -- %r" % (info,)))
    if not ok:
        FAILS.append(what)


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


T = tempfile.mkdtemp()
MUSIC = os.path.join(T, "Music")
songs = mkaudio.make(MUSIC, 2.0)
lib = L.Library(os.path.join(T, "lib.db"))
lib.add_folder(MUSIC)
lib.scan()
ids = {r["title"]: r["id"] for r in lib.tracks()}
titles = lambda rows: sorted(r["title"] for r in rows)  # noqa: E731

# ---------------------------------------------------------------- C3-22 rules
spec = {"match": "all", "rules": [["genre", "is", "Jazz"],
                                  {"match": "any", "rules": [["title", "begins with", "L"], ["track_no", "is", 1]]}]}
check(titles(lib.smart_tracks(spec)) == ["Blue Train", "Lazy Bird", "Locomotion"], "a nested group of rules (any of these, all of those)")
pl = lib.new_playlist("Faves", tracks=[ids["Blue Train"], ids["Sonata in C"]])
check(titles(lib.smart_tracks({"match": "all", "rules": [["playlist", "is", pl]]})) == ["Blue Train", "Sonata in C"], "Playlist is")
check(len(lib.smart_tracks({"match": "all", "rules": [["playlist", "is not", pl]]})) == 5, "Playlist is not")
sp = lib.new_playlist("Jazz", kind="smart", rules={"match": "all", "rules": [["genre", "is", "Jazz"]]})
sp2 = lib.new_playlist("Jazz not faves", kind="smart",
                       rules={"match": "all", "rules": [["playlist", "is", sp], ["playlist", "is not", pl]]})
check(titles(lib.playlist_tracks(sp2)) == ["Lazy Bird", "Locomotion", "Moment's Notice"], "a rule on a Smart Playlist")
lib.set_rules(sp, {"match": "all", "rules": [["playlist", "is", sp2]]})
check(isinstance(lib.playlist_tracks(sp2), list), "playlists that refer to each other don't loop forever")

# ---------------------------------------------------------------- C3-19 lyrics
for t, p in songs.items():
    text = "First line of %s\nSecond line" % t
    tags.set_lyrics(p, text)
    check(tags.lyrics(p) == text, "lyrics kept in the file: %s" % os.path.splitext(p)[1])
tags.set_lyrics(songs["Blue Train"], "")
check(tags.lyrics(songs["Blue Train"]) == "", "lyrics removed")

# ---------------------------------------------------------------- C3-26 organize
messy = os.path.join(MUSIC, "incoming", "misc")
os.makedirs(messy)
loose = os.path.join(messy, "track.flac")
mkaudio.tone(loose, 1.0)
tags.write(loose, {"title": "Night Train", "artist": "Coltrane Quartet", "album": "Night Sessions", "track_no": 5})
open(os.path.join(messy, "cover.jpg"), "wb").write(b"\xff\xd8\xff fake jpeg")
dup = os.path.join(MUSIC, "Coltrane Quartet", "Night Sessions", "05 Night Train.flac")
lib.scan()
mkaudio.tone(os.path.join(T, "other.flac"), 1.0)
shutil.copy(os.path.join(T, "other.flac"), dup)       # a different file already has that name
tags.write(dup, {"title": "Night Train", "artist": "Coltrane Quartet", "album": "Night Sessions", "track_no": 5})
lib.scan()
gw = songs["Grunge Waltz"]
tags.write(gw, {"album_artist": "Various Artists"})
lib.scan()
moves = organize.plan(lib, [MUSIC])
mv = {os.path.relpath(o, MUSIC): os.path.relpath(n, MUSIC) for _i, o, n in moves}
check(mv.get("incoming/misc/track.flac") == "Coltrane Quartet/Night Sessions/05 Night Train (2).flac",
      "a loose song goes to Artist/Album/NN Title, and a clash gets (2)", mv)
check(mv.get("The Garage/Loud Nineties/02 Grunge Waltz.wav") == "Various Artists/Loud Nineties/02 Grunge Waltz.wav",
      "the album artist decides the folder", mv)
check(not any(o.endswith("01 Blue Train.flac") for _i, o, _n in moves), "songs already in place stay")
before = {r["id"]: (r["play_count"], r["rating"]) for r in lib.tracks()}
lib.rate([ids["Grunge Waltz"]], 80)
done, errors, rec = organize.apply(lib, moves, [MUSIC])
check(not errors and len(done) == len(moves), "everything moves", errors)
check(os.path.exists(os.path.join(MUSIC, "Coltrane Quartet", "Night Sessions", "cover.jpg")), "the cover picture goes along")
check(not os.path.exists(os.path.join(MUSIC, "incoming")), "folders left empty are removed")
r = lib.track(ids["Grunge Waltz"])
check(r["path"].endswith("Various Artists/Loud Nineties/02 Grunge Waltz.wav") and r["rating"] == 80,
      "the library follows the file, rating and all")
check(organize.plan(lib, [MUSIC]) == [], "nothing left to move")
moved, errs = organize.undo(lib, rec, [MUSIC])
check(not errs and os.path.exists(loose) and os.path.exists(gw) and lib.track(ids["Grunge Waltz"])["path"] == gw,
      "undo puts everything back")
check(os.path.exists(os.path.join(messy, "cover.jpg")), "the picture too")
# copy into the media folder (C3-12)
media = os.path.join(T, "Media")
ext = os.path.join(T, "elsewhere.ogg")
mkaudio.tone(ext, 1.0)
tags.write(ext, {"title": "Outside", "artist": "Band", "album": "Live", "track_no": 3})
cp = organize.copy_in(ext, media, tags.read(ext))
check(cp == os.path.join(media, "Band", "Live", "03 Outside.ogg") and os.path.exists(cp) and os.path.exists(ext),
      "Copy files to the media folder: a copy in its place, the original left alone")
check(organize.copy_in(ext, media, tags.read(ext)) == cp, "adding it again doesn't make a second copy")

# ---------------------------------------------------------------- C3-23 iTunes library
lib.scan()
ids = {r["title"]: r["id"] for r in lib.tracks()}
when = datetime.datetime(2019, 3, 4, 5, 6, 7)
xml = {"Major Version": 1, "Tracks": {
    "101": {"Track ID": 101, "Name": "Blue Train", "Artist": "Coltrane Quartet", "Album": "Night Sessions", "Total Time": 2000,
            "Rating": 100, "Play Count": 42, "Play Date UTC": when, "Date Added": datetime.datetime(2010, 1, 1),
            "Location": "file://localhost/C:/Users/Ron/Music/iTunes/iTunes%20Media/Music/Coltrane%20Quartet/Night%20Sessions/01%20Blue%20Train.flac"},
    "102": {"Track ID": 102, "Name": "Sonata in C", "Artist": "Hall Ensemble", "Album": "Chamber Works", "Total Time": 2000,
            "Rating": 60, "Play Count": 3, "Location": "file://localhost/D:/old/stuff/x.mp3"},
    "103": {"Track ID": 103, "Name": "Not Here", "Artist": "Nobody", "Album": "None", "Location": "file://localhost/C:/a/b/c.mp3"},
    "104": {"Track ID": 104, "Name": "A Podcast", "Podcast": True}},
    "Playlists": [
        {"Name": "Library", "Master": True, "Playlist Items": [{"Track ID": 101}]},
        {"Name": "Music", "Distinguished Kind": 4, "Music": True, "Playlist Items": [{"Track ID": 101}]},
        {"Name": "Old Favourites", "Playlist Persistent ID": "F1", "Folder": True},
        {"Name": "Sunday", "Playlist Persistent ID": "P1", "Parent Persistent ID": "F1",
         "Playlist Items": [{"Track ID": 102}, {"Track ID": 101}, {"Track ID": 103}]},
        {"Name": "Smart thing", "Smart Info": b"x", "Smart Criteria": b"y", "Playlist Items": [{"Track ID": 101}]}]}
xf = os.path.join(T, "iTunes Library.xml")
with open(xf, "wb") as f:
    plistlib.dump(xml, f)
n_pl = len(lib.playlists())
res = itunes.import_library(lib, xf)
bt = lib.track(ids["Blue Train"])
check(res["songs"] == 2 and res["unmatched"] == ["Not Here"], "iTunes library: songs matched by path or by name/artist/album", res)
check(bt["rating"] == 100 and bt["play_count"] >= 42 and abs(bt["last_played"] - when.timestamp()) < 1, "ratings, play counts, last played come across")
check(abs(bt["date_added"] - datetime.datetime(2010, 1, 1).timestamp()) < 1, "date added: the earlier date")
pls = {p["name"]: p for p in lib.playlists()}
check(len(lib.playlists()) == n_pl + 3 and "Library" not in pls and "Music" not in pls, "its playlists (not Library or Music)")
check([r["title"] for r in lib.playlist_tracks(pls["Sunday"]["id"])] == ["Sonata in C", "Blue Train"]
      and pls["Sunday"]["parent"] == pls["Old Favourites"]["id"], "a playlist in its folder, in order")
check([r["title"] for r in lib.playlist_tracks(pls["Smart thing"]["id"])] == ["Blue Train"], "a Smart Playlist comes as its songs")

# ---------------------------------------------------------------- C3-17 station playlists
check(radio.parse_playlist("[playlist]\nNumberOfEntries=2\nFile2=http://b.example/2\nFile1=http://a.example/1\n")
      == ["http://a.example/1", "http://b.example/2"], ".pls")
check(radio.parse_playlist("#EXTM3U\n#EXTINF:-1,Radio\nhttp://a.example/live\n") == ["http://a.example/live"], ".m3u")
check(radio.parse_playlist('<asx version="3.0"><entry><ref href="http://a.example/asx"/></entry></asx>') == ["http://a.example/asx"], ".asx")
check(radio.parse_playlist("#EXTM3U\n#EXT-X-VERSION:3\nseg1.ts\n") == [], "an HLS stream isn't taken for a playlist")
check(radio.looks_like_playlist("http://x/listen.pls?sid=1") and not radio.looks_like_playlist("http://x/stream.mp3"), "which addresses are playlists")
st = radio.custom_station("My Station", "http://x/live")
radio.set_favourite(lib, st, True)
check(radio.favourites(lib)[-1]["name"] == "My Station" and st["uuid"].startswith("custom:"), "a station of your own in Favourites")

# ---------------------------------------------------------------- C3-16 loudness
g = analysis.measure(songs["Blue Train"])
check(g is not None and -30 < g < 30, "loudness measured (ReplayGain)", g)
lib.update([ids["Blue Train"], ids["Lazy Bird"]], rg_track=None)
done_n = []
a = analysis.Analyser(lib, done=lambda n: done_n.append(n))
a.start()
spin(60, lambda: done_n)
check(done_n and lib.track(ids["Blue Train"])["rg_track"] is not None and lib.track(ids["Blue Train"])["rg_measured"] == 1,
      "songs without ReplayGain are measured in the background", done_n)

# ---------------------------------------------------------------- C3-14 watching
changes = []
w = watcher.Watcher(lib, on_change=lambda: changes.append(1), delay_ms=300)
w.watch([MUSIC])
newsong = os.path.join(MUSIC, "New Band", "First", "01 Hello.ogg")
os.makedirs(os.path.dirname(newsong))
mkaudio.tone(newsong + ".tmp.ogg", 1.0)
os.rename(newsong + ".tmp.ogg", newsong)
ok = spin(8, lambda: lib.tracks("path=?", (newsong,)))
check(ok, "a song put in the music folder appears by itself")
os.remove(newsong)
ok = spin(8, lambda: not lib.tracks("path=? and not missing", (newsong,)))
check(ok, "and goes when it's deleted")
w.stop()

# ---------------------------------------------------------------- C3-13 per-song EQ; C3-15 speed; C3-24 outputs
eng = player.Engine()
item = {"uri": player.uri_of(songs["Moment's Notice"]), "title": "x", "duration": 2, "rg": None, "eq": "Bass Booster"}
eng.play(item)
spin(1, lambda: eng.state == "playing")
check(abs(eng.cur.eq.get_property("band0") - 5.5) < 1e-6 and not eng.eq_on, "a song's own equalizer preset is used for it")
eng.stop()
long = os.path.join(T, "long.ogg")
mkaudio.tone(long, 8.0)
eng.play({"uri": player.uri_of(long), "title": "long", "duration": 8, "rg": None})
spin(1, lambda: eng.state == "playing")
t0, p0 = time.time(), eng.position()
eng.set_rate(2.0)
spin(1.5)
speed = (eng.position() - p0) / (time.time() - t0)
check(eng.cur.tempo is not None and 1.5 < speed < 2.5 and eng.state == "playing", "2× speed (voices keep their pitch)", speed)
eng.set_rate(1.0)
eng.stop()
devs = player.Engine.devices()
check(isinstance(devs, list), "the sound outputs can be listed", len(devs))
eng.set_output(None)
check(eng.a.pb.get_property("audio-sink") is not None, "changing the output keeps a sink")
shutil.rmtree(T)
print("%d checks, %d failed" % (N[0], len(FAILS)))
print("all passed" if not FAILS else "FAILED")
sys.exit(1 if FAILS else 0)
