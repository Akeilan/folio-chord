"""Bringing an iTunes library across (C3-23): iTunes Library.xml (iTunes on Windows or a Mac,
File > Library > Export Library, or the file iTunes keeps next to its library).

Songs are matched to the library here by where they are (the Windows or Mac path turned into
this computer's music folder), else by name, artist, album and length. Ratings, play counts,
skips, last played and date added come across, and the playlists (folders too). Smart Playlists
come across as plain playlists of the songs they held, because iTunes keeps their rules in a
form of its own.
"""
import os
import plistlib
import re
import urllib.parse

SKIP_KINDS = ("Master", "Distinguished Kind", "Music", "Movies", "TV Shows", "Podcasts", "Audiobooks",
              "Purchased Music", "Genius Track ID")


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _tail(location):
    """The last parts of the file's path (Artist/Album/Song.mp3), whatever computer it was on."""
    p = urllib.parse.unquote(urllib.parse.urlparse(location or "").path)
    parts = [x for x in re.split(r"[\\/]", p) if x]
    return [x.lower() for x in parts[-3:]]


def read(path):
    with open(path, "rb") as f:
        return plistlib.load(f)


def import_library(lib, path):
    """Bring ratings, counts, dates and playlists across. Returns a summary dict."""
    d = read(path)
    rows = lib.q("select * from tracks where not missing")
    by_tail = {}
    by_tags = {}
    for r in rows:
        parts = [x.lower() for x in r["path"].split("/")[-3:]]
        by_tail.setdefault(tuple(parts), r["id"])
        by_tail.setdefault(tuple(parts[-1:]), r["id"])
        key = (_norm(r["title"]), _norm(r["artist"]), _norm(r["album"]))
        by_tags.setdefault(key, []).append(r)
    matched = {}
    unmatched = []
    for tid, t in (d.get("Tracks") or {}).items():
        if t.get("Podcast") or t.get("Movie") or t.get("TV Show") or t.get("Has Video"):
            continue
        tail = _tail(t.get("Location"))
        mine = by_tail.get(tuple(tail)) if tail else None
        if mine is None:
            cands = by_tags.get((_norm(t.get("Name")), _norm(t.get("Artist")), _norm(t.get("Album"))), [])
            secs = (t.get("Total Time") or 0) / 1000.0
            cands = [c for c in cands if not secs or abs((c["duration"] or 0) - secs) < 3] or cands
            mine = cands[0]["id"] if cands else None
        if mine is None and tail:
            mine = by_tail.get(tuple(tail[-1:]))
        if mine is None:
            unmatched.append(t.get("Name") or tail[-1:] and tail[-1] or "?")
            continue
        matched[str(tid)] = mine
        fields = {}
        if t.get("Rating") is not None and not t.get("Rating Computed"):
            fields["rating"] = int(t["Rating"])
        if t.get("Play Count"):
            fields["play_count"] = int(t["Play Count"])
        if t.get("Skip Count"):
            fields["skip_count"] = int(t["Skip Count"])
        for key, col in (("Play Date UTC", "last_played"), ("Date Added", "date_added"), ("Skip Date", "last_skipped")):
            if t.get(key) is not None:
                fields[col] = t[key].timestamp()
        if t.get("Disabled"):
            fields["checked"] = 0
        if fields:
            mine_row = lib.track(mine)
            # counts add up with what was played here; dates keep the later (or, added, the earlier)
            if "play_count" in fields:
                fields["play_count"] += int(mine_row["play_count"] or 0)
            if "last_played" in fields and (mine_row["last_played"] or 0) > fields["last_played"]:
                del fields["last_played"]
            if "date_added" in fields and mine_row["date_added"] and mine_row["date_added"] < fields["date_added"]:
                del fields["date_added"]
            lib.update([mine], **fields)
    # playlists and folders
    made = 0
    ids = {}
    pls = d.get("Playlists") or []
    for p in pls:
        if any(p.get(k) for k in SKIP_KINDS) or p.get("Visible") is False:
            continue
        name = p.get("Name") or "untitled playlist"
        if p.get("Folder"):
            ids[p.get("Playlist Persistent ID")] = lib.new_playlist(name, kind="folder")
            made += 1
    for p in pls:
        if any(p.get(k) for k in SKIP_KINDS) or p.get("Visible") is False or p.get("Folder"):
            continue
        tracks = [matched[str(i["Track ID"])] for i in p.get("Playlist Items") or [] if str(i.get("Track ID")) in matched]
        if not tracks and p.get("Smart Info"):
            continue
        pid = lib.new_playlist(p.get("Name") or "untitled playlist", tracks=tracks)
        ids[p.get("Playlist Persistent ID")] = pid
        made += 1
    for p in pls:
        par = p.get("Parent Persistent ID")
        me = ids.get(p.get("Playlist Persistent ID"))
        if par and me and par in ids:
            lib.move_playlist(me, ids[par])
    lib.changed("playlists")
    return {"songs": len(matched), "unmatched": unmatched, "playlists": made}
