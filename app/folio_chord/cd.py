"""Audio CDs (C3-07): read a disc's tracks, look up their names (MusicBrainz, the open music
database, if Options allows it; or the disc's own CD-Text), import them as AAC, Apple Lossless,
MP3, FLAC or WAV into the music folder, and burn a playlist to an audio CD or a data CD.

Reading and ripping go through GStreamer's CD source (cdparanoia); burning through wodim.
FOLIO_CHORD_FAKE_CD=<folder of WAV files> stands in for a disc in tests.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

from . import net, tags  # noqa: E402

Gst.init(None)

MUSICBRAINZ = os.environ.get("FOLIO_CHORD_MUSICBRAINZ", "https://musicbrainz.org/ws/2")
MB_AGENT = "FolioChord/%s ( https://github.com/Akeilan/folio-chord )" % net.VERSION

# Import Settings: label -> (extension, encoder pipeline)
FORMATS = {
    "AAC": (".m4a", "avenc_aac bitrate={kbps}000 ! mp4mux"),
    "Apple Lossless": (".m4a", "avenc_alac ! mp4mux"),
    "MP3": (".mp3", "lamemp3enc target=bitrate bitrate={kbps} cbr=true ! id3v2mux"),
    "FLAC": (".flac", "flacenc"),
    "WAV": (".wav", "wavenc"),
}
QUALITY = {"AAC": [128, 192, 256, 320], "MP3": [128, 160, 192, 256, 320]}
CD_SECONDS = 80 * 60


def drives():
    """Optical drives on this computer (device paths)."""
    fake = os.environ.get("FOLIO_CHORD_FAKE_CD")
    if fake:
        return ["fake:" + fake]
    out = []
    for d in sorted(glob.glob("/dev/sr[0-9]*")):
        out.append(d)
    if not out and os.path.exists("/dev/cdrom"):
        out.append("/dev/cdrom")
    return out


def _src(device, track):
    if device.startswith("fake:"):
        f = sorted(glob.glob(os.path.join(device[5:], "*.wav")))[track - 1]
        e = Gst.parse_bin_from_description("filesrc name=fsrc ! wavparse", True)
        e.get_by_name("fsrc").set_property("location", f)
        return e
    src = Gst.ElementFactory.make("cdparanoiasrc") or Gst.ElementFactory.make("cdiocddasrc")
    if src is None:
        raise RuntimeError("Reading CDs needs GStreamer's CD support (gstreamer1.0-plugins-base).")
    src.set_property("device", device)
    src.set_property("track", track)
    return src


def read_disc(device):
    """{"tracks": [seconds per track], "discid": MusicBrainz disc id or "", "cdtext": {...}}, or None
    when there is no audio disc in the drive."""
    if device.startswith("fake:"):
        files = sorted(glob.glob(os.path.join(device[5:], "*.wav")))
        if not files:
            return None
        info = {}
        p = os.path.join(device[5:], "disc.json")
        if os.path.exists(p):
            info = json.load(open(p))
        return {"tracks": [tags.read(f)["duration"] for f in files], "discid": info.get("discid", ""),
                "cdtext": info.get("cdtext", {})}
    try:
        src = _src(device, 1)
    except RuntimeError:
        return None
    pipe = Gst.Pipeline.new("cdread")
    sink = Gst.ElementFactory.make("fakesink")
    pipe.add(src)
    pipe.add(sink)
    src.link(sink)
    pipe.set_state(Gst.State.PAUSED)
    bus = pipe.get_bus()
    res = {"tracks": [], "discid": "", "cdtext": {}}
    got_toc = False
    while True:
        m = bus.timed_pop_filtered(15 * Gst.SECOND, Gst.MessageType.TAG | Gst.MessageType.TOC |
                                   Gst.MessageType.ASYNC_DONE | Gst.MessageType.ERROR)
        if m is None or m.type == Gst.MessageType.ERROR:
            break
        if m.type == Gst.MessageType.TAG:
            tl = m.parse_tag()
            ok, v = tl.get_string("musicbrainz-discid")
            if ok:
                res["discid"] = v
            for k, name in (("album", Gst.TAG_ALBUM), ("artist", Gst.TAG_ALBUM_ARTIST)):
                ok, v = tl.get_string(name)
                if ok and v:
                    res["cdtext"][k] = v
        elif m.type == Gst.MessageType.TOC:
            toc, _upd = m.parse_toc()
            for e in toc.get_entries():
                ok, start, stop = e.get_start_stop_times()
                if ok:
                    res["tracks"].append((stop - start) / Gst.SECOND)
            got_toc = True
        elif m.type == Gst.MessageType.ASYNC_DONE and got_toc:
            break
    pipe.set_state(Gst.State.NULL)
    return res if res["tracks"] else None


def lookup(discid):
    """Track names from MusicBrainz: {"album", "artist", "year", "genre", "tracks": [{"title", "artist"}]}."""
    if not discid:
        return None
    d = net.get_json(net.url(MUSICBRAINZ, "/discid/" + discid, inc="recordings artist-credits", fmt="json"),
                     headers={"User-Agent": MB_AGENT})
    rels = d.get("releases") or []
    if not rels:
        return None
    rel = rels[0]
    credit = lambda ac: "".join((c.get("name") or "") + (c.get("joinphrase") or "") for c in (ac or []))  # noqa: E731
    medium = None
    for m in rel.get("media") or []:
        if any(x.get("id") == discid for x in m.get("discs") or []):
            medium = m
            break
    medium = medium or (rel.get("media") or [{}])[0]
    tracks = [{"title": t.get("title") or "", "artist": credit(t.get("artist-credit")) or credit(rel.get("artist-credit"))}
              for t in medium.get("tracks") or []]
    year = re.match(r"\d{4}", rel.get("date") or "")
    return {"album": rel.get("title") or "", "artist": credit(rel.get("artist-credit")),
            "year": int(year.group(0)) if year else 0, "genre": "", "tracks": tracks,
            "disc_no": int(medium.get("position") or 1), "disc_count": len(rel.get("media") or []) or 1}


def safe(s):
    return re.sub(r'[\\/:*?"<>|]+', "_", (s or "").strip()).strip(". ") or "Unknown"


def dest_path(folder, info, n, fmt):
    """iTunes' layout: <music folder>/<Album Artist>/<Album>/<NN Title>.<ext>"""
    ext = FORMATS[fmt][0]
    t = info["tracks"][n - 1] if info.get("tracks") and n <= len(info["tracks"]) else {}
    d = os.path.join(folder, safe(info.get("artist") or "Unknown Artist"), safe(info.get("album") or "Unknown Album"))
    return os.path.join(d, "%s%02d %s%s" % ("%d-" % info["disc_no"] if info.get("disc_count", 1) > 1 else "", n,
                                            safe(t.get("title") or "Track %d" % n), ext))


def rip(device, track, dest, fmt="AAC", kbps=256, progress=None, stop=None):
    """Import one track to dest. progress(fraction)."""
    ext, enc = FORMATS[fmt]
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    pipe = Gst.Pipeline.new("rip")
    src = _src(device, track)
    rest = Gst.parse_bin_from_description("audioconvert ! audioresample ! " + enc.format(kbps=kbps) + " ! filesink name=out", True)
    rest.get_by_name("out").set_property("location", dest + ".part")
    pipe.add(src)
    pipe.add(rest)
    src.link(rest)
    pipe.set_state(Gst.State.PLAYING)
    bus = pipe.get_bus()
    ok = False
    while True:
        m = bus.timed_pop_filtered(200 * Gst.MSECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
        if stop and stop():
            break
        if progress:
            okp, pos = pipe.query_position(Gst.Format.TIME)
            okd, dur = pipe.query_duration(Gst.Format.TIME)
            if okp and okd and dur > 0:
                progress(min(1.0, pos / dur))
        if m is None:
            continue
        if m.type == Gst.MessageType.ERROR:
            err = m.parse_error()[0].message
            pipe.set_state(Gst.State.NULL)
            raise RuntimeError(err)
        ok = True
        break
    pipe.set_state(Gst.State.NULL)
    if not ok:
        try:
            os.remove(dest + ".part")
        except OSError:
            pass
        return None
    os.replace(dest + ".part", dest)
    return dest


def tag_ripped(path, info, n):
    t = info["tracks"][n - 1] if info.get("tracks") and n <= len(info["tracks"]) else {}
    tags.write(path, {"title": t.get("title") or "Track %d" % n, "artist": t.get("artist") or info.get("artist") or "",
                      "album_artist": info.get("artist") or "", "album": info.get("album") or "",
                      "year": info.get("year") or 0, "genre": info.get("genre") or "",
                      "track_no": n, "track_count": len(info.get("tracks") or []) or 0,
                      "disc_no": info.get("disc_no") or 0, "disc_count": info.get("disc_count") or 0})


def eject(device):
    if device.startswith("fake:"):
        return True
    return subprocess.call(["eject", device], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


# ---------------------------------------------------------------- burning
def burner():
    return os.environ.get("FOLIO_CHORD_WODIM") or shutil.which("wodim") or shutil.which("cdrecord")


def fits(seconds):
    return seconds <= CD_SECONDS


def to_cd_wav(src, dest, gap=0.0):
    """Decode a song to CD audio (44.1 kHz, 16-bit stereo WAV), with `gap` seconds of silence first."""
    pipe = Gst.parse_launch("uridecodebin name=d ! audioconvert ! audioresample ! "
                            "audio/x-raw,format=S16LE,rate=44100,channels=2 ! wavenc ! filesink name=out")
    pipe.get_by_name("d").set_property("uri", Gst.filename_to_uri(os.path.abspath(src)))
    pipe.get_by_name("out").set_property("location", dest)
    pipe.set_state(Gst.State.PLAYING)
    m = pipe.get_bus().timed_pop_filtered(600 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
    pipe.set_state(Gst.State.NULL)
    if m is None or m.type == Gst.MessageType.ERROR:
        raise RuntimeError("couldn't convert %s for the CD" % os.path.basename(src))
    if gap > 0:
        import wave
        with wave.open(dest, "rb") as w:
            frames = w.readframes(w.getnframes())
        with wave.open(dest, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(44100)
            w.writeframes(b"\0" * int(gap * 44100) * 4 + frames)


def burn(paths, device, kind="audio", gap=2.0, speed=0, progress=None, log=None):
    """Burn songs to a disc: kind "audio" (an audio CD, any player) or "data" (the files themselves).
    Returns the burner's exit status."""
    cmd = burner()
    if not cmd:
        raise RuntimeError("Burning discs needs wodim (sudo apt install wodim).")
    work = tempfile.mkdtemp(prefix="chord-burn-")
    try:
        if kind == "audio":
            wavs = []
            for i, p in enumerate(paths):
                if progress:
                    progress("Preparing “%s”" % os.path.basename(p), i / max(1, len(paths)) * 0.5)
                w = os.path.join(work, "%02d.wav" % (i + 1))
                to_cd_wav(p, w, gap if i > 0 else 0)
                wavs.append(w)
            args = [cmd, "-v", "-dao", "-pad", "-audio", "dev=" + device] + (["speed=%d" % speed] if speed else []) + wavs
        else:
            iso = os.path.join(work, "disc.iso")
            mk = shutil.which("genisoimage") or shutil.which("mkisofs")
            if not mk:
                raise RuntimeError("Data discs need genisoimage (sudo apt install genisoimage).")
            stage = os.path.join(work, "files")
            os.makedirs(stage)
            for p in paths:
                shutil.copy(p, stage)
            subprocess.check_call([mk, "-quiet", "-r", "-J", "-V", "Folio Chord", "-o", iso, stage])
            args = [cmd, "-v", "-data", "dev=" + device] + (["speed=%d" % speed] if speed else []) + [iso]
        if progress:
            progress("Burning…", 0.5)
        r = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if log is not None:
            log.append(r.stdout)
        if progress:
            progress("Done" if r.returncode == 0 else "The disc couldn't be burned.", 1.0)
        return r.returncode
    finally:
        shutil.rmtree(work, ignore_errors=True)
