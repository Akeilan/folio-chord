"""Song information in the files themselves (C3-01, C3-04): read and write the tags and artwork
of MP3, MP2, MP4/M4A (AAC, ALAC), raw AAC, FLAC, Ogg Vorbis, Opus, WAV, AIFF, WMA, Monkey's Audio
and WavPack files through mutagen; Matroska audio (.mka) is read through GStreamer and written with
mkvpropedit (mkvtoolnix) when it is installed (C8-41).

  read(path)              {"title", "artist", "album_artist", "album", "genre", "composer", "year",
                           "track_no", "track_count", "disc_no", "disc_count", "comments",
                           "compilation", "bpm", "grouping", "rg_track", "rg_album", "duration",
                           "bitrate", "sample_rate", "channels", "kind", "has_art"}
  write(path, changes)    changes: the same keys; "" or None clears one
  artwork(path)           (bytes, mime) or None
  set_artwork(path, data, mime)   data None removes it
  lyrics(path) / set_lyrics(path, text)   the song's lyrics (C3-19)
"""
import base64
import os
import re

FIELDS = ("title", "artist", "album_artist", "album", "genre", "composer", "year", "track_no",
          "track_count", "disc_no", "disc_count", "comments", "compilation", "bpm", "grouping")
EXTENSIONS = (".mp3", ".mp2", ".m4a", ".m4b", ".mp4", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wav", ".aif", ".aiff",
              ".wma", ".ape", ".wv", ".mka")

# Vorbis comment names (FLAC, Ogg, Opus)
_VC = {"title": "TITLE", "artist": "ARTIST", "album_artist": "ALBUMARTIST", "album": "ALBUM",
       "genre": "GENRE", "composer": "COMPOSER", "year": "DATE", "comments": "COMMENT",
       "compilation": "COMPILATION", "bpm": "BPM", "grouping": "GROUPING"}
# MP4 atoms
_MP4 = {"title": "\xa9nam", "artist": "\xa9ART", "album_artist": "aART", "album": "\xa9alb",
        "genre": "\xa9gen", "composer": "\xa9wrt", "year": "\xa9day", "comments": "\xa9cmt",
        "grouping": "\xa9grp"}
# WMA (ASF) attributes
_ASF = {"title": "Title", "artist": "Author", "album_artist": "WM/AlbumArtist", "album": "WM/AlbumTitle",
        "genre": "WM/Genre", "composer": "WM/Composer", "year": "WM/Year", "comments": "Description",
        "grouping": "WM/ContentGroupDescription", "bpm": "WM/BeatsPerMinute"}
# APEv2 items (Monkey's Audio, WavPack)
_APE = {"title": "Title", "artist": "Artist", "album_artist": "Album Artist", "album": "Album", "genre": "Genre",
        "composer": "Composer", "year": "Year", "comments": "Comment", "grouping": "Grouping", "bpm": "BPM",
        "compilation": "Compilation"}
# Matroska tag names
_MKA = {"title": "TITLE", "artist": "ARTIST", "album_artist": "ALBUM_ARTIST", "album": "ALBUM", "genre": "GENRE",
        "composer": "COMPOSER", "year": "DATE_RELEASED", "comments": "COMMENT", "grouping": "GROUPING", "bpm": "BPM"}
# ID3 frames
_ID3 = {"title": "TIT2", "artist": "TPE1", "album_artist": "TPE2", "album": "TALB", "genre": "TCON",
        "composer": "TCOM", "year": "TDRC", "bpm": "TBPM", "grouping": "TIT1", "compilation": "TCMP"}


def is_audio(path):
    return path.lower().endswith(EXTENSIONS)


def _num_pair(v):
    """'3/12' -> (3, 12)."""
    if v is None:
        return 0, 0
    if isinstance(v, (tuple, list)):
        return (int(v[0] or 0), int(v[1] or 0)) if len(v) > 1 else (int(v[0] or 0), 0)
    m = re.match(r"\s*(\d*)\s*(?:/\s*(\d*))?", str(v))
    a = int(m.group(1)) if m and m.group(1) else 0
    b = int(m.group(2)) if m and m.group(2) else 0
    return a, b


def _year(v):
    m = re.search(r"\d{4}", str(v or ""))
    return int(m.group(0)) if m else 0


def _gain(v):
    m = re.search(r"[-+]?\d+(\.\d+)?", str(v or ""))
    return float(m.group(0)) if m else None


def _first(v):
    if isinstance(v, (list, tuple)):
        v = v[0] if v else ""
    return "" if v is None else str(v)


class NotASong(ValueError):
    """A file Folio Chord leaves out of the library (a video, say)."""


def _mp4_has_video(path):
    """True when an MP4 file holds a picture track: a video, not a song (C8-22)."""
    try:
        from mutagen.mp4 import Atoms
        with open(path, "rb") as fh:
            atoms = Atoms(fh)
            moov = [a for a in atoms.atoms if a.name == b"moov"]
            if not moov:
                return False
            for trak in moov[0].findall(b"trak"):
                try:
                    hdlr = trak[b"mdia", b"hdlr"]
                except KeyError:
                    continue
                ok, data = hdlr.read(fh)
                if ok and data[8:12] == b"vide":
                    return True
    except Exception:       # noqa: BLE001
        return False
    return False


def _open(path):
    import mutagen
    if path.lower().endswith(".aac"):
        # a raw AAC file with an ID3 tag in front would otherwise be taken for an MP3
        from mutagen.aac import AAC
        try:
            return AAC(path)
        except Exception:       # noqa: BLE001
            pass
    f = mutagen.File(path)
    if f is not None and type(f).__name__ == "MP4" and _mp4_has_video(path):
        raise NotASong("%s is a video, not a song" % os.path.basename(path))
    return f


def _aac_id3(path):
    """The ID3 tag at the start of a raw AAC (.aac) file, the way other players keep its details."""
    from mutagen.id3 import ID3, ID3NoHeaderError
    try:
        return ID3(path)
    except ID3NoHeaderError:
        return ID3()


def _save(f):
    """Save, keeping an ID3 tag at the version it was (v2.3 stays v2.3 for older players, C8-22)."""
    t = f.tags
    ver = getattr(t, "version", None)
    if ver is not None and tuple(ver[:2]) == (2, 3) and hasattr(t, "update_to_v23"):
        t.update_to_v23()
        try:
            f.save(v2_version=3)
            return
        except TypeError:
            pass
    f.save()


def _riff_info(path):
    """The LIST/INFO details other programs write into WAV files (title, artist, ...)."""
    import struct
    out = {}
    names = {b"INAM": "title", b"IART": "artist", b"IPRD": "album", b"ICRD": "year", b"IGNR": "genre",
             b"ICMT": "comments", b"ITRK": "track", b"IPRT": "track", b"IMUS": "composer"}
    try:
        with open(path, "rb") as fh:
            head = fh.read(12)
            if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
                return out
            while True:
                h = fh.read(8)
                if len(h) < 8:
                    break
                cid, size = h[:4], struct.unpack("<I", h[4:])[0]
                if cid == b"LIST":
                    body = fh.read(size)
                    if size & 1:
                        fh.seek(1, 1)
                    if body[:4] == b"INFO":
                        i = 4
                        while i + 8 <= len(body):
                            sid, sl = body[i:i + 4], struct.unpack("<I", body[i + 4:i + 8])[0]
                            raw = body[i + 8:i + 8 + sl].split(b"\0")[0]
                            if sid in names:
                                try:
                                    out[names[sid]] = raw.decode("utf-8")
                                except UnicodeDecodeError:
                                    out[names[sid]] = raw.decode("cp1252", "replace")
                            i += 8 + sl + (sl & 1)
                else:
                    fh.seek(size + (size & 1), 1)
    except OSError:
        pass
    return out


def _riff_info_write(path, values):
    """Write the WAV file's LIST/INFO chunk afresh from these values, so other programs (which read
    INFO rather than the ID3 chunk) see the same details; an empty set removes it."""
    import struct
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return
    chunks, i = [], 12
    while i + 8 <= len(data):
        cid, size = data[i:i + 4], struct.unpack("<I", data[i + 4:i + 8])[0]
        body = data[i + 8:i + 8 + size]
        if not (cid == b"LIST" and body[:4] == b"INFO"):
            chunks.append((cid, body))
        i += 8 + size + (size & 1)
    names = (("title", b"INAM"), ("artist", b"IART"), ("album", b"IPRD"), ("year", b"ICRD"), ("genre", b"IGNR"),
             ("comments", b"ICMT"), ("track", b"ITRK"))
    info = b""
    for key, sid in names:
        v = values.get(key)
        if v in ("", None, 0):
            continue
        raw = str(v).encode("utf-8") + b"\0"
        info += sid + struct.pack("<I", len(raw)) + raw + (b"\0" if len(raw) & 1 else b"")
    if info:
        chunks.append((b"LIST", b"INFO" + info))
    out = b"".join(cid + struct.pack("<I", len(body)) + body + (b"\0" if len(body) & 1 else b"") for cid, body in chunks)
    tmp = path + ".tmp-chord"
    with open(tmp, "wb") as fh:
        fh.write(b"RIFF" + struct.pack("<I", 4 + len(out)) + b"WAVE" + out)
    os.replace(tmp, path)


def _discover(path):
    """Duration, stream details and tags of a file through GStreamer (Matroska audio)."""
    import gi
    gi.require_version("Gst", "1.0")
    gi.require_version("GstPbutils", "1.0")
    from gi.repository import Gst, GstPbutils
    Gst.init(None)
    d = GstPbutils.Discoverer.new(10 * Gst.SECOND)
    info = d.discover_uri(Gst.filename_to_uri(os.path.abspath(path)))
    vids = [v for v in info.get_video_streams() if not v.is_image()]
    if vids:
        raise NotASong("%s is a video, not a song" % os.path.basename(path))
    aud = info.get_audio_streams()
    if not aud:
        raise ValueError("not an audio file: %s" % path)
    a = aud[0]
    tl = info.get_tags()
    t = {}
    if tl is not None:
        for key, tag in (("title", Gst.TAG_TITLE), ("artist", Gst.TAG_ARTIST), ("album_artist", Gst.TAG_ALBUM_ARTIST),
                         ("album", Gst.TAG_ALBUM), ("genre", Gst.TAG_GENRE), ("composer", Gst.TAG_COMPOSER),
                         ("comments", Gst.TAG_COMMENT), ("grouping", Gst.TAG_GROUPING)):
            ok, v = tl.get_string(tag)
            if ok:
                t[key] = v
        for key, tag in (("track_no", Gst.TAG_TRACK_NUMBER), ("track_count", Gst.TAG_TRACK_COUNT),
                         ("disc_no", Gst.TAG_ALBUM_VOLUME_NUMBER), ("disc_count", Gst.TAG_ALBUM_VOLUME_COUNT)):
            ok, v = tl.get_uint(tag)
            if ok:
                t[key] = int(v)
        ok, dt = tl.get_date_time(Gst.TAG_DATE_TIME)
        if ok and dt.has_year():
            t["year"] = dt.get_year()
        ok, g = tl.get_double(Gst.TAG_TRACK_GAIN)
        if ok:
            t["rg_track"] = g
        ok, g = tl.get_double(Gst.TAG_ALBUM_GAIN)
        if ok:
            t["rg_album"] = g
        t["has_art"] = bool(tl.get_sample(Gst.TAG_IMAGE)[0])
    return {"duration": info.get_duration() / Gst.SECOND, "bitrate": int((a.get_bitrate() or 0) / 1000),
            "sample_rate": a.get_sample_rate(), "channels": a.get_channels(), "tags": t}


def _kind(f, path):
    n = type(f).__name__
    ext = os.path.splitext(path)[1].lower()
    if n == "MP3":
        return "MPEG audio file"
    if n == "MP4":
        codec = getattr(f.info, "codec", "") or ""
        return "Apple Lossless audio file" if codec.startswith("alac") else "AAC audio file"
    if n == "FLAC":
        return "FLAC audio file"
    if n in ("OggVorbis",):
        return "Ogg Vorbis audio file"
    if n == "OggOpus":
        return "Opus audio file"
    if n == "WAVE":
        return "WAV audio file"
    if n == "AIFF":
        return "AIFF audio file"
    if n == "ASF":
        return "Windows Media audio file"
    if n == "MonkeysAudio":
        return "Monkey's Audio file"
    if n == "WavPack":
        return "WavPack audio file"
    if n == "OggFLAC":
        return "FLAC audio file"
    if n == "AAC":
        return "AAC audio file"
    return (ext[1:].upper() + " audio file") if ext else "Audio file"


def read(path):
    out = {k: "" for k in FIELDS}
    out.update({"track_no": 0, "track_count": 0, "disc_no": 0, "disc_count": 0, "year": 0, "bpm": 0,
                "compilation": False, "rg_track": None, "rg_album": None, "duration": 0.0, "bitrate": 0,
                "sample_rate": 0, "channels": 0, "kind": "", "has_art": False})
    if path.lower().endswith(".mka"):
        d = _discover(path)
        for k in ("duration", "bitrate", "sample_rate", "channels"):
            out[k] = d[k]
        out.update({k: v for k, v in d["tags"].items() if k in out})
        out.update(_mka_tags(path))         # the file's own tags, read exactly, when mkvtoolnix is there
        out["kind"] = "Matroska audio file"
        return _finish(out, path)
    f = _open(path)
    if f is None:
        raise ValueError("not an audio file: %s" % path)
    info = f.info
    out["duration"] = float(getattr(info, "length", 0) or 0)
    out["bitrate"] = int((getattr(info, "bitrate", 0) or 0) / 1000)
    out["sample_rate"] = int(getattr(info, "sample_rate", 0) or 0)
    out["channels"] = int(getattr(info, "channels", 0) or 0)
    out["kind"] = _kind(f, path)
    n = type(f).__name__
    t = f.tags
    if n == "AAC":
        t = _aac_id3(path)
        if not t.keys():
            t = None
    if n == "OggOpus" and not out["sample_rate"]:
        out["sample_rate"] = 48000
    if t is None:
        pass
    elif n == "ASF":
        def a(key):
            v = t.get(key)
            return str(v[0]) if v else ""
        for k, key in _ASF.items():
            if t.get(key):
                out[k] = a(key)
        out["track_no"], out["track_count"] = _num_pair(a("WM/TrackNumber") or a("WM/Track"))
        out["disc_no"], out["disc_count"] = _num_pair(a("WM/PartOfSet"))
        out["compilation"] = a("WM/IsCompilation").lower() in ("1", "true")
        out["rg_track"] = _gain(a("replaygain_track_gain")) if t.get("replaygain_track_gain") else None
        out["rg_album"] = _gain(a("replaygain_album_gain")) if t.get("replaygain_album_gain") else None
        out["has_art"] = bool(t.get("WM/Picture"))
    elif n in ("MonkeysAudio", "WavPack") or type(t).__name__ == "APEv2":
        def a(key):
            for kk in t.keys():
                if kk.lower() == key.lower():
                    return str(t[kk])
            return ""
        for k, key in _APE.items():
            if a(key):
                out[k] = a(key)
        out["track_no"], out["track_count"] = _num_pair(a("Track"))
        out["disc_no"], out["disc_count"] = _num_pair(a("Disc"))
        out["rg_track"] = _gain(a("REPLAYGAIN_TRACK_GAIN")) if a("REPLAYGAIN_TRACK_GAIN") else None
        out["rg_album"] = _gain(a("REPLAYGAIN_ALBUM_GAIN")) if a("REPLAYGAIN_ALBUM_GAIN") else None
        out["has_art"] = any(kk.lower().startswith("cover art") for kk in t.keys())
    elif n in ("MP3", "WAVE", "AIFF", "AAC") or hasattr(t, "getall"):
        for k, fr in _ID3.items():
            if fr in t:
                out[k] = str(t[fr].text[0]) if t[fr].text else ""
        if "TRCK" in t:
            out["track_no"], out["track_count"] = _num_pair(t["TRCK"].text[0])
        if "TPOS" in t:
            out["disc_no"], out["disc_count"] = _num_pair(t["TPOS"].text[0])
        com = [c for c in t.getall("COMM") if c.desc in ("", "Comment")]
        if com:
            out["comments"] = str(com[0].text[0]) if com[0].text else ""
        for x in t.getall("TXXX"):
            d = x.desc.lower()
            if d == "replaygain_track_gain":
                out["rg_track"] = _gain(x.text[0])
            elif d == "replaygain_album_gain":
                out["rg_album"] = _gain(x.text[0])
        out["has_art"] = bool(t.getall("APIC"))
    elif n == "MP4":
        for k, at in _MP4.items():
            if at in t:
                out[k] = _first(t[at])
        if "trkn" in t:
            out["track_no"], out["track_count"] = _num_pair(t["trkn"][0])
        if "disk" in t:
            out["disc_no"], out["disc_count"] = _num_pair(t["disk"][0])
        if "cpil" in t:
            out["compilation"] = bool(t["cpil"])
        if "tmpo" in t:
            out["bpm"] = int(t["tmpo"][0])
        for key in t.keys():
            if key.lower().endswith(":replaygain_track_gain"):
                out["rg_track"] = _gain(bytes(t[key][0]).decode("utf-8", "replace"))
            elif key.lower().endswith(":replaygain_album_gain"):
                out["rg_album"] = _gain(bytes(t[key][0]).decode("utf-8", "replace"))
        out["has_art"] = bool(t.get("covr"))
    else:   # Vorbis comments
        for k, name in _VC.items():
            v = t.get(name) or t.get(name.lower())
            if v:
                out[k] = _first(v)
        if not out["comments"]:
            out["comments"] = _first(t.get("DESCRIPTION") or t.get("description") or "")     # C8-22
        if not out["year"]:
            out["year"] = _first(t.get("YEAR") or t.get("year") or "")
        tn = _first(t.get("TRACKNUMBER") or "")
        out["track_no"], tc = _num_pair(tn)
        out["track_count"] = tc or _num_pair(_first(t.get("TRACKTOTAL") or t.get("TOTALTRACKS") or ""))[0]
        dn = _first(t.get("DISCNUMBER") or "")
        out["disc_no"], dc = _num_pair(dn)
        out["disc_count"] = dc or _num_pair(_first(t.get("DISCTOTAL") or t.get("TOTALDISCS") or ""))[0]
        out["rg_track"] = _gain(_first(t.get("REPLAYGAIN_TRACK_GAIN") or "")) if t.get("REPLAYGAIN_TRACK_GAIN") else None
        out["rg_album"] = _gain(_first(t.get("REPLAYGAIN_ALBUM_GAIN") or "")) if t.get("REPLAYGAIN_ALBUM_GAIN") else None
        # Opus keeps loudness as R128 gain (Q7.8 dB against -23 LUFS); ReplayGain is against -18
        if out["rg_track"] is None and t.get("R128_TRACK_GAIN"):
            g = _gain(_first(t.get("R128_TRACK_GAIN")))
            out["rg_track"] = None if g is None else round(g / 256.0 + 5.0, 2)
        if out["rg_album"] is None and t.get("R128_ALBUM_GAIN"):
            g = _gain(_first(t.get("R128_ALBUM_GAIN")))
            out["rg_album"] = None if g is None else round(g / 256.0 + 5.0, 2)
        out["has_art"] = bool(getattr(f, "pictures", None)) or bool(t.get("METADATA_BLOCK_PICTURE"))
    if n == "WAVE":
        info_tags = _riff_info(path)
        for k in ("title", "artist", "album", "genre", "comments", "composer", "year"):
            if not out[k] and info_tags.get(k):
                out[k] = info_tags[k]
        if not out["track_no"] and info_tags.get("track"):
            out["track_no"], out["track_count"] = _num_pair(info_tags["track"])
    if not out["bitrate"] and out["duration"] > 0:
        try:
            out["bitrate"] = int(os.path.getsize(path) * 8 / out["duration"] / 1000)
        except OSError:
            pass
    return _finish(out, path)


def _finish(out, path):
    if not isinstance(out["compilation"], bool):
        out["compilation"] = str(out["compilation"]).strip() in ("1", "true", "True", "yes")
    out["year"] = _year(out["year"])
    try:
        out["bpm"] = int(float(out["bpm"] or 0))
    except ValueError:
        out["bpm"] = 0
    if not out["title"]:
        out["title"] = os.path.splitext(os.path.basename(path))[0]
    return out


def _pair(no, count):
    no, count = int(no or 0), int(count or 0)
    if not no and not count:
        return ""
    return "%d/%d" % (no, count) if count else str(no)


def write(path, changes):
    """Write the given fields into the file; the others stay as they are."""
    if path.lower().endswith(".mka"):
        return _write_mka(path, changes)
    f = _open(path)
    if f is None:
        raise ValueError("not an audio file: %s" % path)
    n = type(f).__name__
    if n == "AAC":
        t = _aac_id3(path)
    else:
        if f.tags is None:
            f.add_tags()
        t = f.tags
    cur = read(path)
    cur.update({k: v for k, v in changes.items() if k in FIELDS})
    if n == "ASF":
        from mutagen.asf import ASFUnicodeAttribute, ASFBoolAttribute
        for k, key in _ASF.items():
            if k in changes:
                if changes[k] in ("", None, 0):
                    if key in t:
                        del t[key]
                else:
                    t[key] = [ASFUnicodeAttribute(str(changes[k]))]
        for k, key, pair in (("track", "WM/TrackNumber", False), ("disc", "WM/PartOfSet", True)):
            if k + "_no" in changes or k + "_count" in changes:
                no, count = cur[k + "_no"], cur[k + "_count"]
                val = _pair(no, count) if pair else (str(int(no)) if no else "")
                if val:
                    t[key] = [ASFUnicodeAttribute(val)]
                elif key in t:
                    del t[key]
        if "compilation" in changes:
            t["WM/IsCompilation"] = [ASFBoolAttribute(bool(changes["compilation"]))]
        f.save()
        return
    if n in ("MonkeysAudio", "WavPack"):
        for k, key in _APE.items():
            if k in changes:
                for kk in [x for x in t.keys() if x.lower() == key.lower()]:
                    del t[kk]
                if k == "compilation":
                    if changes[k]:
                        t[key] = "1"
                elif changes[k] not in ("", None, 0):
                    t[key] = str(changes[k])
        for k, key in (("track", "Track"), ("disc", "Disc")):
            if k + "_no" in changes or k + "_count" in changes:
                for kk in [x for x in t.keys() if x.lower() == key.lower()]:
                    del t[kk]
                val = _pair(cur[k + "_no"], cur[k + "_count"])
                if val:
                    t[key] = val
        f.save()
        return
    if n in ("MP3", "WAVE", "AIFF", "AAC") or hasattr(t, "getall"):
        from mutagen import id3
        for k, fr in _ID3.items():
            if k not in changes:
                continue
            v = changes[k]
            t.delall(fr)
            if k == "compilation":
                if v:
                    t.add(id3.TCMP(encoding=3, text=["1"]))
            elif k == "year":
                if v:
                    t.add(id3.TDRC(encoding=3, text=[str(v)]))
            elif v not in ("", None, 0):
                t.add(getattr(id3, fr)(encoding=3, text=[str(v)]))
        if "track_no" in changes or "track_count" in changes:
            t.delall("TRCK")
            s = _pair(cur["track_no"], cur["track_count"])
            if s:
                t.add(id3.TRCK(encoding=3, text=[s]))
        if "disc_no" in changes or "disc_count" in changes:
            t.delall("TPOS")
            s = _pair(cur["disc_no"], cur["disc_count"])
            if s:
                t.add(id3.TPOS(encoding=3, text=[s]))
        if "comments" in changes:
            t.setall("COMM", [c for c in t.getall("COMM") if c.desc not in ("", "Comment")])
            if changes["comments"]:
                t.add(id3.COMM(encoding=3, lang="eng", desc="", text=[changes["comments"]]))
    elif n == "MP4":
        for k, at in _MP4.items():
            if k not in changes:
                continue
            v = changes[k]
            if v in ("", None, 0):
                t.pop(at, None)
            else:
                t[at] = [str(v)]
        if "track_no" in changes or "track_count" in changes:
            if cur["track_no"] or cur["track_count"]:
                t["trkn"] = [(int(cur["track_no"] or 0), int(cur["track_count"] or 0))]
            else:
                t.pop("trkn", None)
        if "disc_no" in changes or "disc_count" in changes:
            if cur["disc_no"] or cur["disc_count"]:
                t["disk"] = [(int(cur["disc_no"] or 0), int(cur["disc_count"] or 0))]
            else:
                t.pop("disk", None)
        if "compilation" in changes:
            if changes["compilation"]:
                t["cpil"] = True
            else:
                t.pop("cpil", None)
        if "bpm" in changes:
            if changes["bpm"]:
                t["tmpo"] = [int(changes["bpm"])]
            else:
                t.pop("tmpo", None)
    else:
        for k, name in _VC.items():
            if k not in changes:
                continue
            v = changes[k]
            # DESCRIPTION is read as the comment too (C8-22), so it goes with it
            for nm in (name, name.lower()) + (("DESCRIPTION", "description") if k == "comments" else ()):
                if nm in t:
                    del t[nm]
            if k == "compilation":
                if v:
                    t[name] = ["1"]
            elif v not in ("", None, 0):
                t[name] = [str(v)]
        if "track_no" in changes or "track_count" in changes:
            for nm in ("TRACKNUMBER", "TRACKTOTAL", "TOTALTRACKS"):
                if nm in t:
                    del t[nm]
            if cur["track_no"]:
                t["TRACKNUMBER"] = [str(int(cur["track_no"]))]
            if cur["track_count"]:
                t["TRACKTOTAL"] = [str(int(cur["track_count"]))]
        if "disc_no" in changes or "disc_count" in changes:
            for nm in ("DISCNUMBER", "DISCTOTAL", "TOTALDISCS"):
                if nm in t:
                    del t[nm]
            if cur["disc_no"]:
                t["DISCNUMBER"] = [str(int(cur["disc_no"]))]
            if cur["disc_count"]:
                t["DISCTOTAL"] = [str(int(cur["disc_count"]))]
    if n == "AAC":
        t.save(path)
    else:
        _save(f)
    if n == "WAVE":
        _riff_info_write(path, {"title": cur["title"], "artist": cur["artist"], "album": cur["album"], "year": cur["year"],
                                "genre": cur["genre"], "comments": cur["comments"], "track": cur["track_no"]})


def _mka_tags(path):
    """The album-level tags of a Matroska file, through mkvextract (mkvtoolnix); {} without it."""
    import shutil
    import subprocess
    exe = shutil.which("mkvextract")
    if not exe:
        return {}
    try:
        r = subprocess.run([exe, "tags", path], capture_output=True, text=True, timeout=20)
        import xml.etree.ElementTree as ET
        text = r.stdout.lstrip("\ufeff").strip()          # newer mkvextract starts with a byte-order mark
        root = ET.fromstring(text) if text.startswith("<?xml") or text.startswith("<Tags") else None
    except Exception:       # noqa: BLE001
        return {}
    if root is None:
        return {}
    names = {v: k for k, v in _MKA.items()}
    names.update({"PART_NUMBER": "track_no", "TOTAL_PARTS": "track_count"})
    out = {}
    for tag in root.findall("Tag"):
        tt = tag.findtext("Targets/TargetTypeValue") or "50"
        if tt not in ("50", ""):
            continue
        for sm in tag.findall("Simple"):
            k = names.get((sm.findtext("Name") or "").upper())
            v = sm.findtext("String")
            if k and v is not None:
                out[k] = int(v) if k in ("track_no", "track_count") and v.isdigit() else v
    return out


def _write_mka(path, changes):
    """Matroska tags through mkvpropedit (the mkvtoolnix package), the program made for it."""
    import shutil
    import subprocess
    import tempfile
    from xml.sax.saxutils import escape
    exe = shutil.which("mkvpropedit")
    if not exe:
        raise ValueError("changing the details of Matroska (.mka) files needs the mkvtoolnix package "
                         "(sudo apt install mkvtoolnix)")
    cur = read(path)
    cur.update({k: v for k, v in changes.items() if k in FIELDS})
    simple = []
    for k, name in _MKA.items():
        v = cur.get(k)
        if v not in ("", None, 0, False):
            simple.append((name, str(v)))
    for k, name in (("track_no", "PART_NUMBER"), ("track_count", "TOTAL_PARTS")):
        if cur.get(k):
            simple.append((name, str(int(cur[k]))))
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', "<Tags><Tag><Targets><TargetTypeValue>50</TargetTypeValue></Targets>"]
    xml += ["<Simple><Name>%s</Name><String>%s</String></Simple>" % (escape(a), escape(b)) for a, b in simple]
    xml.append("</Tag></Tags>")
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as fh:
        fh.write("\n".join(xml))
        tmp = fh.name
    try:
        r = subprocess.run([exe, path, "--tags", "global:" + tmp], capture_output=True, text=True)
        # some builds of mkvpropedit crash on the way out after writing (seen with 65.0 on 22.04):
        # what counts is whether the file now holds the details
        want = {names_k: str(v) for names_k, v in cur.items() if names_k in _MKA and v not in ("", None, 0, False)}
        got = _mka_tags(path) if r.returncode not in (0, 1) else {}
        if r.returncode not in (0, 1) and not (want and all(str(got.get(k)) == v for k, v in want.items())):
            raise ValueError("mkvpropedit couldn't change the file: %s" % (r.stdout or r.stderr).strip()[-200:])
    finally:
        os.remove(tmp)


def _asf_picture(data, mime):
    import struct

    def enc(s):
        return s.encode("utf-16-le") + b"\0\0"
    return struct.pack("<bI", 3, len(data)) + enc(mime) + enc("") + data


def _asf_unpicture(blob):
    import struct
    _typ, size = struct.unpack("<bI", blob[:5])
    i = 5
    parts = []
    for _ in range(2):
        j = i
        while blob[j:j + 2] != b"\0\0":
            j += 2
        parts.append(blob[i:j].decode("utf-16-le", "replace"))
        i = j + 2
    return blob[i:i + size], parts[0] or "image/jpeg"


def artwork(path):
    if path.lower().endswith(".mka"):
        return None
    f = _open(path)
    if f is None:
        return None
    n = type(f).__name__
    if n == "AAC":
        t = _aac_id3(path)
        pics = t.getall("APIC")
        if pics:
            front = [p for p in pics if p.type == 3] or pics
            return bytes(front[0].data), front[0].mime or "image/jpeg"
        return None
    if f.tags is None and not getattr(f, "pictures", None):
        return None
    t = f.tags
    if n == "ASF":
        v = t.get("WM/Picture")
        return _asf_unpicture(bytes(v[0].value)) if v else None
    if n in ("MonkeysAudio", "WavPack"):
        for kk in t.keys():
            if kk.lower().startswith("cover art"):
                blob = bytes(t[kk].value)
                data = blob.split(b"\0", 1)[1] if b"\0" in blob[:256] else blob
                return data, "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
        return None
    if t is not None and hasattr(t, "getall"):
        pics = t.getall("APIC")
        if pics:
            front = [p for p in pics if p.type == 3] or pics
            return bytes(front[0].data), front[0].mime or "image/jpeg"
        return None
    if n == "MP4":
        c = t.get("covr") if t is not None else None
        if c:
            from mutagen.mp4 import MP4Cover
            fmt = getattr(c[0], "imageformat", MP4Cover.FORMAT_JPEG)
            return bytes(c[0]), "image/png" if fmt == MP4Cover.FORMAT_PNG else "image/jpeg"
        return None
    pics = list(getattr(f, "pictures", None) or [])
    if not pics and t is not None and t.get("METADATA_BLOCK_PICTURE"):
        from mutagen.flac import Picture
        for b in t["METADATA_BLOCK_PICTURE"]:
            try:
                pics.append(Picture(base64.b64decode(b)))
            except Exception:
                pass
    if pics:
        front = [p for p in pics if p.type == 3] or pics
        return bytes(front[0].data), front[0].mime or "image/jpeg"
    return None


def _image_size(data):
    """(width, height) of a PNG or JPEG."""
    import struct
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        mk = data[i + 1]
        ln = struct.unpack(">H", data[i + 2:i + 4])[0]
        if mk in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        i += 2 + ln
    return 0, 0


def set_artwork(path, data, mime="image/jpeg"):
    if path.lower().endswith(".mka"):
        raise ValueError("artwork can't be added to Matroska (.mka) files")
    f = _open(path)
    if f is None:
        raise ValueError("not an audio file: %s" % path)
    n = type(f).__name__
    if n == "AAC":
        t = _aac_id3(path)
    else:
        if f.tags is None:
            f.add_tags()
        t = f.tags
    if data is not None and data[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    if n == "ASF":
        from mutagen.asf import ASFByteArrayAttribute
        if "WM/Picture" in t:
            del t["WM/Picture"]
        if data is not None:
            t["WM/Picture"] = [ASFByteArrayAttribute(_asf_picture(data, mime))]
        f.save()
        return
    if n in ("MonkeysAudio", "WavPack"):
        from mutagen.apev2 import APEValue, BINARY
        for kk in [x for x in t.keys() if x.lower().startswith("cover art")]:
            del t[kk]
        if data is not None:
            t["Cover Art (Front)"] = APEValue(b"cover" + (b".png" if mime == "image/png" else b".jpg") + b"\0" + data, BINARY)
        f.save()
        return
    if hasattr(t, "getall"):
        from mutagen import id3
        t.delall("APIC")
        if data is not None:
            t.add(id3.APIC(encoding=3, mime=mime, type=3, desc="Cover", data=data))
    elif n == "MP4":
        from mutagen.mp4 import MP4Cover
        if data is None:
            t.pop("covr", None)
        else:
            t["covr"] = [MP4Cover(data, MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG)]
    else:
        from mutagen.flac import Picture
        if data is not None:
            p = Picture()
            p.type = 3
            p.mime = mime
            p.desc = "Cover"
            p.data = data
            p.width, p.height = _image_size(data)
            p.depth = 24
        if n == "FLAC":
            f.clear_pictures()
            if data is not None:
                f.add_picture(p)
        else:
            for nm in ("METADATA_BLOCK_PICTURE", "metadata_block_picture"):
                if nm in t:
                    del t[nm]
            if data is not None:
                t["METADATA_BLOCK_PICTURE"] = [base64.b64encode(p.write()).decode("ascii")]
    if n == "AAC":
        t.save(path)
    else:
        _save(f)


def lyrics(path):
    """The lyrics kept in the file ("" when there are none)."""
    if path.lower().endswith(".mka"):
        return ""
    f = _open(path)
    if f is None:
        return ""
    t = _aac_id3(path) if type(f).__name__ == "AAC" else f.tags
    if t is None:
        return ""
    if type(f).__name__ == "ASF":
        v = t.get("WM/Lyrics")
        return str(v[0]) if v else ""
    if type(f).__name__ in ("MonkeysAudio", "WavPack"):
        for kk in t.keys():
            if kk.lower() == "lyrics":
                return str(t[kk])
        return ""
    if hasattr(t, "getall"):
        for u in t.getall("USLT"):
            if u.text:
                return str(u.text)
        return ""
    if type(f).__name__ == "MP4":
        return _first(t.get("\xa9lyr") or "")
    for nm in ("LYRICS", "UNSYNCEDLYRICS", "lyrics", "unsyncedlyrics"):
        if t.get(nm):
            return _first(t[nm])
    return ""


def set_lyrics(path, text):
    if path.lower().endswith(".mka"):
        raise ValueError("lyrics can't be kept in Matroska (.mka) files")
    f = _open(path)
    if f is None:
        raise ValueError("not an audio file: %s" % path)
    n = type(f).__name__
    if n == "AAC":
        t = _aac_id3(path)
    else:
        if f.tags is None:
            f.add_tags()
        t = f.tags
    text = (text or "").strip()
    if n == "ASF":
        if "WM/Lyrics" in t:
            del t["WM/Lyrics"]
        if text:
            t["WM/Lyrics"] = [text]
        f.save()
        return
    if n in ("MonkeysAudio", "WavPack"):
        for kk in [x for x in t.keys() if x.lower() == "lyrics"]:
            del t[kk]
        if text:
            t["Lyrics"] = text
        f.save()
        return
    if hasattr(t, "getall"):
        from mutagen import id3
        t.delall("USLT")
        if text:
            t.add(id3.USLT(encoding=3, lang="eng", desc="", text=text))
    elif type(f).__name__ == "MP4":
        if text:
            t["\xa9lyr"] = [text]
        else:
            t.pop("\xa9lyr", None)
    else:
        for nm in ("LYRICS", "UNSYNCEDLYRICS", "lyrics", "unsyncedlyrics"):
            if nm in t:
                del t[nm]
        if text:
            t["LYRICS"] = [text]
    if n == "AAC":
        t.save(path)
    else:
        _save(f)
