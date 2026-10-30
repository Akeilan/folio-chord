# C3-07: CDs — a disc in the drive (a stand-in), track names from MusicBrainz, Import CD in each
# format, eject; burning a playlist (a stand-in burner); Create Version of songs.
import json
import os
import stat
import sys

sys.path.insert(0, os.environ["FOLIO_TESTS"])
from uicommon import answer, check, music, pump, run, shot, wait  # noqa: E402
from gi.repository import Gtk  # noqa: E402
import mkaudio  # noqa: E402
import netstub  # noqa: E402
from folio_chord import cd, tags  # noqa: E402


def main():
    w = win  # noqa: F821
    lib = app.lib  # noqa: F821
    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"), "chord_cd_%d" % os.getpid())
    disc = os.path.join(tmp, "disc")
    os.makedirs(disc, exist_ok=True)
    for i, f in enumerate((262, 330, 392)):
        mkaudio.tone(os.path.join(disc, "track%02d.wav" % (i + 1)), 2.0, f)
    json.dump({"discid": "abcDISC-", "cdtext": {}}, open(os.path.join(disc, "disc.json"), "w"))
    ogg = os.path.join(tmp, "t.ogg")
    mkaudio.tone(ogg, 1.0)
    stub = netstub.Stub(ogg)
    cd.MUSICBRAINZ = stub.base + "/mb"
    media = os.path.join(tmp, "Media")
    w.settings["media_folder"] = media
    os.environ["FOLIO_CHORD_FAKE_CD"] = disc
    w._check_cd()
    ok = wait(lambda: w.cd_info is not None and w.cd_info.get("album") == "Fake Disc", 10)
    check(ok, "a CD in the drive shows under Devices, with its names from MusicBrainz", w.cd_info)
    check(any(r[2] == "cd" and r[1] == "Fake Disc" for r in w.src_store), "the CD in the source list")
    w.select_source("cd")
    pump(0.2)
    check([r[2] for r in w.cd_store] == ["Opening", "Middle", "Closing"] and w.cd_store[1][4] == "Test Band feat. Guest",
          "its tracks, names and artists")
    check(any(h[2].get("User-Agent", "").startswith("FolioChord/") and "github.com" in h[2].get("User-Agent", "")
              for h in stub.hits if h[0].startswith("/mb/")), "MusicBrainz is asked with Folio Chord's name (as it requires), nothing else")
    shot(w, "cd_disc")
    w.play_cd_track(2)
    ok = wait(lambda: app.playback.engine.state == "playing", 5)  # noqa: F821
    check(ok and w.lcd.title.get_text() == "Middle", "play a track from the CD")
    w.run("stop")
    # import, one format after another
    w.cd_store[2][0] = False
    for fmt, ext in (("AAC", ".m4a"), ("MP3", ".mp3"), ("FLAC", ".flac"), ("Apple Lossless", ".m4a")):
        w.settings["import_format"] = fmt
        made = w.run("import-cd")
        good = made and len(made) == 2 and all(p.endswith(ext) and os.path.exists(p) for p in made)
        t = tags.read(made[1]) if made else {}
        check(good and t.get("title") == "Middle" and t.get("album") == "Fake Disc" and t.get("track_no") == 2
              and t.get("year") == 2001 and t.get("album_artist") == "Test Band" and 1.5 < t.get("duration", 0) < 2.6,
              "Import CD as %s: the ticked tracks, named and tagged" % fmt, (made, t.get("kind")))
        for p in made or []:
            if fmt != "Apple Lossless":
                os.remove(p)
                lib.remove([r["id"] for r in lib.tracks("path=?", (p,))])
    check(made and made[0].startswith(os.path.join(media, "Test Band", "Fake Disc", "01 Opening")), "in Artist/Album/NN Title", made)
    check(tags.read(made[0])["kind"] == "Apple Lossless audio file", "Apple Lossless is lossless", tags.read(made[0])["kind"])
    check(len(lib.tracks("album=?", ("Fake Disc",))) == 2 and media in w.settings["music_folders"], "the imported songs are in the library")
    # a disc MusicBrainz doesn't know
    json.dump({"discid": "unknown", "cdtext": {"album": "My Mix"}}, open(os.path.join(disc, "disc.json"), "w"))
    w.run("eject")
    check(w.cd_info is None and w.source[0] == "music", "Eject")
    w._check_cd()
    wait(lambda: w.cd_info is not None and getattr(w, "last_message", "").startswith("No track names"), 8)
    check(w.cd_info["album"] == "My Mix", "the disc's own CD-Text name when MusicBrainz has none")
    # burn a playlist (a stand-in burner records what it's asked)
    rec = os.path.join(tmp, "burn.args")
    fake = os.path.join(tmp, "wodim")
    open(fake, "w").write("#!/bin/sh\necho \"$@\" > %s\nls \"$@\" >/dev/null 2>&1\necho done\nexit 0\n" % rec)
    os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
    os.environ["FOLIO_CHORD_WODIM"] = fake
    pid = lib.new_playlist("To Burn", tracks=[r["id"] for r in lib.tracks("album=?", ("Fake Disc",))])
    w.fill_sources()
    w.select_source("playlist", pid)
    answer("Burn Settings", lambda d: (d.gap.set_active_id("2"), Gtk.ResponseType.OK)[1])
    code = w.run("burn")
    args = open(rec).read() if os.path.exists(rec) else ""
    check(code == 0 and "-audio" in args and "-dao" in args and args.count(".wav") == 2, "Burn Playlist to Disc: an audio CD", args)
    answer("Burn Settings", lambda d: (d.data.set_active(True), Gtk.ResponseType.OK)[1])
    os.remove(rec)
    if __import__("shutil").which("genisoimage"):
        code = w.run("burn")
        args = open(rec).read() if os.path.exists(rec) else ""
        check(code == 0 and "-data" in args and args.strip().endswith(".iso"), "or a data CD", args)
    # too long for a CD
    lib.update([r["id"] for r in lib.tracks("album=?", ("Fake Disc",))], duration=3000)
    answer("Burn Settings", Gtk.ResponseType.OK)
    w.settings["burn_kind"] = "audio"
    check(w.run("burn") is None and "don't fit" in w.last_message, "too long for an audio CD: says so")
    lib.scan()
    # Create Version
    d, songs = music(w)
    ids = {r["title"]: r["id"] for r in w.rows}
    w.songs.select_ids([ids["Blue Train"]])
    made = w.run("convert:MP3")
    check(made and made[0].endswith(".mp3") and tags.read(made[0])["title"] == "Blue Train"
          and tags.read(made[0])["kind"] == "MPEG audio file", "Create MP3 Version, tags kept")
    check(len(lib.tracks("title=?", ("Blue Train",))) == 2, "the new version joins the library")
    # Get Album Artwork (Cover Art Archive)
    cd.COVERART = stub.base + "/caa"
    w.load_songs()
    w.songs.select_ids([r["id"] for r in w.rows if r["album"] in ("Night Sessions", "Loud Nineties")])
    w.run("get-artwork")
    ok = wait(lambda: getattr(w, "last_artwork", None) is not None, 8)
    check(ok and w.last_artwork >= 4 and tags.artwork(songs["Lazy Bird"]) is not None and tags.artwork(songs["Grunge Waltz"]) is None,
          "Get Album Artwork: covers for albums the archive knows", getattr(w, "last_artwork", None))
    check("1 of 2" in getattr(w, "last_message", ""), "and says which it couldn't find", getattr(w, "last_message", ""))
    stub.stop()


run(main)
