"""Song information in the files themselves (C3-01, C3-04): read and write the tags and artwork
of MP3, MP4/M4A (AAC, ALAC), FLAC, Ogg Vorbis, Opus, WAV and AIFF files, through mutagen.

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
EXTENSIONS = (".mp3", ".m4a", ".m4b", ".mp4", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wav", ".aif", ".aiff")

# Vorbis comment names (FLAC, Ogg, Opus)
_VC = {"title": "TITLE", "artist": "ARTIST", "album_artist": "ALBUMARTIST", "album": "ALBUM",
       "genre": "GENRE", "composer": "COMPOSER", "year": "DATE", "comments": "COMMENT",
       "compilation": "COMPILATION", "bpm": "BPM", "grouping": "GROUPING"}
# MP4 atoms
_MP4 = {"title": "\xa9nam", "artist": "\xa9ART", "album_artist": "aART", "album": "\xa9alb",
        "genre": "\xa9gen", "composer": "\xa9wrt", "year": "\xa9day", "comments": "\xa9cmt",
        "grouping": "\xa9grp"}
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


def _open(path):
    import mutagen
    return mutagen.File(path)


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
    return (ext[1:].upper() + " audio file") if ext else "Audio file"


def read(path):
    out = {k: "" for k in FIELDS}
    out.update({"track_no": 0, "track_count": 0, "disc_no": 0, "disc_count": 0, "year": 0, "bpm": 0,
                "compilation": False, "rg_track": None, "rg_album": None, "duration": 0.0, "bitrate": 0,
                "sample_rate": 0, "channels": 0, "kind": "", "has_art": False})
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
    if t is None:
        pass
    elif n in ("MP3", "WAVE", "AIFF") or hasattr(t, "getall"):
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
        tn = _first(t.get("TRACKNUMBER") or "")
        out["track_no"], tc = _num_pair(tn)
        out["track_count"] = tc or _num_pair(_first(t.get("TRACKTOTAL") or t.get("TOTALTRACKS") or ""))[0]
        dn = _first(t.get("DISCNUMBER") or "")
        out["disc_no"], dc = _num_pair(dn)
        out["disc_count"] = dc or _num_pair(_first(t.get("DISCTOTAL") or t.get("TOTALDISCS") or ""))[0]
        out["rg_track"] = _gain(_first(t.get("REPLAYGAIN_TRACK_GAIN") or "")) if t.get("REPLAYGAIN_TRACK_GAIN") else None
        out["rg_album"] = _gain(_first(t.get("REPLAYGAIN_ALBUM_GAIN") or "")) if t.get("REPLAYGAIN_ALBUM_GAIN") else None
        out["has_art"] = bool(getattr(f, "pictures", None)) or bool(t.get("METADATA_BLOCK_PICTURE"))
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
    f = _open(path)
    if f is None:
        raise ValueError("not an audio file: %s" % path)
    n = type(f).__name__
    if f.tags is None:
        f.add_tags()
    t = f.tags
    cur = read(path)
    cur.update({k: v for k, v in changes.items() if k in FIELDS})
    if n in ("MP3", "WAVE", "AIFF") or hasattr(t, "getall"):
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
            for nm in (name, name.lower()):
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
    f.save()


def artwork(path):
    f = _open(path)
    if f is None or f.tags is None and not getattr(f, "pictures", None):
        return None
    n = type(f).__name__
    t = f.tags
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
    f = _open(path)
    if f is None:
        raise ValueError("not an audio file: %s" % path)
    n = type(f).__name__
    if f.tags is None:
        f.add_tags()
    t = f.tags
    if data is not None and data[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
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
    f.save()


def lyrics(path):
    """The lyrics kept in the file ("" when there are none)."""
    f = _open(path)
    if f is None or f.tags is None:
        return ""
    t = f.tags
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
    f = _open(path)
    if f is None:
        raise ValueError("not an audio file: %s" % path)
    if f.tags is None:
        f.add_tags()
    t = f.tags
    text = (text or "").strip()
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
    f.save()
