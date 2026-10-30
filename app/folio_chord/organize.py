"""Keeping the music folder in order (C3-26, C3-12): every song in Music / Artist / Album / NN Song,
from its tags (the album artist when there is one, so an album stays together).

  plan(lib, roots) -> [(track id, old path, new path)]     what would move (nothing is touched)
  apply(lib, moves) -> (moved, errors, undo record)        move the files; the library follows
  undo(lib, record) -> (moved, errors)
  place(path, root, info) -> where a song belongs under root
  copy_in(lib, path, root) -> the copy's path                 for "copy files to the media folder"
"""
import os
import re
import shutil

from . import tags

PICTURES = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")


def safe(s):
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", (s or "").strip())
    s = s.strip(". ")
    return s[:120] or ""


def place(root, info, ext):
    """root / Artist / Album / [D-]NN Title.ext for a song's tags."""
    artist = safe(info.get("album_artist") or info.get("artist")) or "Unknown Artist"
    album = safe(info.get("album")) or "Unknown Album"
    title = safe(info.get("title")) or "Untitled"
    n = int(info.get("track_no") or 0)
    disc = int(info.get("disc_no") or 0) if int(info.get("disc_count") or 0) > 1 else 0
    name = ("%d-" % disc if disc else "") + ("%02d " % n if n else "") + title + ext.lower()
    return os.path.join(root, artist, album, name)


def root_of(path, roots):
    best = None
    for r in roots:
        r = os.path.abspath(r).rstrip("/")
        if path.startswith(r + "/") and (best is None or len(r) > len(best)):
            best = r
    return best


def plan(lib, roots):
    """Every song under the roots that isn't where its tags say: [(id, old, new)]. Two songs that
    would land on the same name get "(2)", "(3)" added."""
    roots = [os.path.abspath(r) for r in roots if r]
    taken = {}
    moves = []
    rows = lib.q("select * from tracks where not missing order by album_artist, album, disc_no, track_no, id")
    # files already in place keep their names
    want = {}
    for r in rows:
        root = root_of(r["path"], roots)
        if root is None:
            continue
        want[r["id"]] = (r, place(root, dict(r), os.path.splitext(r["path"])[1]))
    for tid, (r, target) in want.items():
        if os.path.normcase(r["path"]) == os.path.normcase(target):
            taken[target.lower()] = tid
    for tid, (r, target) in want.items():
        if os.path.normcase(r["path"]) == os.path.normcase(target):
            continue
        base, ext = os.path.splitext(target)
        cand, k = target, 2
        while cand.lower() in taken or (os.path.exists(cand) and os.path.normcase(cand) != os.path.normcase(r["path"])):
            cand = "%s (%d)%s" % (base, k, ext)
            k += 1
        taken[cand.lower()] = tid
        if os.path.normcase(cand) != os.path.normcase(r["path"]):
            moves.append((tid, r["path"], cand))
    return moves


def _move(old, new):
    os.makedirs(os.path.dirname(new), exist_ok=True)
    if os.path.exists(new):
        raise OSError("%s is already there" % new)
    shutil.move(old, new)


def _prune(d, roots):
    """Remove folders left empty (or holding only pictures that moved) up to the root."""
    roots = {os.path.abspath(r).rstrip("/") for r in roots}
    d = os.path.abspath(d)
    while d and d not in roots and d != "/":
        try:
            left = os.listdir(d)
        except OSError:
            return
        hidden = [x for x in left if x in (".directory", "Thumbs.db", "desktop.ini", ".DS_Store")]
        if len(left) != len(hidden):
            return
        for x in hidden:
            try:
                os.remove(os.path.join(d, x))
            except OSError:
                return
        try:
            os.rmdir(d)
        except OSError:
            return
        d = os.path.dirname(d)


def apply(lib, moves, roots):
    """Move the files and update the library. Pictures in a folder all of whose songs went to one
    album folder go along. Returns (moved, errors, record) — record undoes it."""
    done, errors = [], []
    olddirs = {}
    for tid, old, new in moves:
        try:
            _move(old, new)
        except OSError as e:
            errors.append("%s: %s" % (os.path.basename(old), e))
            continue
        lib.update([tid], path=new)
        done.append((tid, old, new))
        olddirs.setdefault(os.path.dirname(old), set()).add(os.path.dirname(new))
    pics = []
    for od, nds in olddirs.items():
        if len(nds) != 1 or not os.path.isdir(od):
            continue
        nd = next(iter(nds))
        if any(f.lower().endswith(tags.EXTENSIONS) for f in os.listdir(od)):
            continue       # songs left behind: the pictures stay with them
        for f in os.listdir(od):
            if f.lower().endswith(PICTURES) and not os.path.exists(os.path.join(nd, f)):
                try:
                    _move(os.path.join(od, f), os.path.join(nd, f))
                    pics.append((os.path.join(od, f), os.path.join(nd, f)))
                except OSError:
                    pass
    for od in olddirs:
        _prune(od, roots)
    lib.changed()
    return done, errors, {"songs": done, "pictures": pics}


def undo(lib, record, roots):
    moved, errors = [], []
    for old, new in reversed(record.get("pictures", [])):
        try:
            _move(new, old)
        except OSError:
            pass
    for tid, old, new in reversed(record.get("songs", [])):
        try:
            _move(new, old)
            lib.update([tid], path=old)
            moved.append(tid)
        except OSError as e:
            errors.append("%s: %s" % (os.path.basename(new), e))
    for tid, old, new in record.get("songs", []):
        _prune(os.path.dirname(new), roots)
    lib.changed()
    return moved, errors


def copy_in(path, root, info):
    """A copy of the song in its place under root (C3-12); the existing copy when one is there."""
    dest = place(root, info, os.path.splitext(path)[1])
    if os.path.abspath(path) == os.path.abspath(dest):
        return dest
    base, ext = os.path.splitext(dest)
    k = 2
    while os.path.exists(dest):
        if os.path.getsize(dest) == os.path.getsize(path):
            return dest
        dest = "%s (%d)%s" % (base, k, ext)
        k += 1
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(path, dest)
    return dest
