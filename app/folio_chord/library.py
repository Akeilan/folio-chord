"""The library (C3-01, C3-03): songs, playlists, Smart Playlists, play counts and ratings, kept in
SQLite in the data folder. Songs come from the music folders the library watches.

Ratings are 0-100 in steps of 20 (one to five stars), as iTunes keeps them.
"""
import json
import os
import sqlite3
import threading
import time

from . import tags

SCHEMA = """
create table if not exists tracks(
  id integer primary key, path text unique, title text, artist text, album_artist text, album text,
  genre text, composer text, year integer, track_no integer, track_count integer, disc_no integer,
  disc_count integer, comments text, compilation integer, bpm integer, grouping text,
  rg_track real, rg_album real, duration real, bitrate integer, sample_rate integer, channels integer,
  kind text, size integer, mtime real, date_added real, date_modified real, play_count integer default 0,
  last_played real, skip_count integer default 0, last_skipped real, rating integer default 0,
  checked integer default 1, has_art integer default 0, missing integer default 0,
  start_time real default 0, stop_time real default 0, volume_adjust integer default 0, eq text default '',
  remember_position integer default 0, position real default 0, skip_shuffle integer default 0,
  rg_measured integer default 0);
create table if not exists folders(path text primary key);
create table if not exists playlists(
  id integer primary key, name text, kind text, parent integer, rules text, position integer default 0);
create table if not exists playlist_items(playlist integer, track integer, pos integer);
create index if not exists pi_pl on playlist_items(playlist, pos);
create table if not exists kv(k text primary key, v text);
"""

# what a Smart Playlist rule can look at: (label, column, kind)
FIELDS = [
    ("Album", "album", "text"), ("Album Artist", "album_artist", "text"), ("Artist", "artist", "text"),
    ("BPM", "bpm", "number"), ("Bit Rate", "bitrate", "number"), ("Comments", "comments", "text"),
    ("Compilation", "compilation", "bool"), ("Composer", "composer", "text"),
    ("Date Added", "date_added", "date"), ("Date Modified", "date_modified", "date"),
    ("Disc Number", "disc_no", "number"), ("Genre", "genre", "text"), ("Grouping", "grouping", "text"),
    ("Kind", "kind", "text"), ("Last Played", "last_played", "date"), ("Last Skipped", "last_skipped", "date"),
    ("Name", "title", "text"), ("Plays", "play_count", "number"), ("Rating", "rating", "rating"),
    ("Sample Rate", "sample_rate", "number"), ("Size", "size", "number"), ("Skips", "skip_count", "number"),
    ("Time", "duration", "number"), ("Track Number", "track_no", "number"), ("Year", "year", "number"),
]
FIELD = {c: (label, kind) for label, c, kind in FIELDS}
OPS = {
    "text": ["contains", "does not contain", "is", "is not", "begins with", "ends with"],
    "number": ["is", "is not", "is greater than", "is less than", "is in the range"],
    "rating": ["is", "is not", "is greater than", "is less than", "is in the range"],
    "date": ["is in the last", "is not in the last", "is after", "is before"],
    "bool": ["is true", "is false"],
}
UNITS = {"days": 86400, "weeks": 7 * 86400, "months": 30 * 86400}
LIMIT_BY = {"items": None, "minutes": "duration", "hours": "duration", "MB": "size", "GB": "size"}
SELECTED_BY = {
    "random": "random()", "album": "album collate nocase, disc_no, track_no", "artist": "artist collate nocase, album collate nocase, track_no",
    "genre": "genre collate nocase", "name": "title collate nocase", "highest rating": "rating desc",
    "lowest rating": "rating", "most recently played": "last_played desc", "least recently played": "coalesce(last_played,0)",
    "most often played": "play_count desc", "least often played": "play_count", "most recently added": "date_added desc",
    "least recently added": "date_added",
}

DEFAULT_SMART = [
    ("90's Music", {"match": "all", "rules": [["year", "is in the range", 1990, 1999]]}),
    ("Classical Music", {"match": "all", "rules": [["genre", "is", "Classical"]]}),
    ("My Top Rated", {"match": "all", "rules": [["rating", "is greater than", 60]]}),
    ("Recently Added", {"match": "all", "rules": [["date_added", "is in the last", 2, "weeks"]]}),
    ("Recently Played", {"match": "all", "rules": [["last_played", "is in the last", 2, "weeks"]]}),
    ("Top 25 Most Played", {"match": "all", "rules": [["play_count", "is greater than", 0]],
                            "limit": [25, "items"], "selected_by": "most often played"}),
]


def _clause(spec, now, members, depth=0):
    """SQL for one group of rules: (expression, params). A rule is [column, op, value, value2/unit],
    or a nested group {"match": "all"|"any", "rules": [...]} (C3-22)."""
    parts, params = [], []
    for r in spec.get("rules", []):
        if isinstance(r, dict):
            if depth < 8:
                sub, sp = _clause(r, now, members, depth + 1)
                parts.append(sub)
                params += sp
            continue
        col, op = r[0], r[1]
        if col == "playlist":
            ids = members(int(r[2])) if members and len(r) > 2 and r[2] not in (None, "") else []
            inside = "id in (%s)" % ",".join(str(int(i)) for i in ids) if ids else "0"
            parts.append(inside if op == "is" else "not (%s)" % inside)
            continue
        if col not in FIELD:
            continue
        kind = FIELD[col][1]
        v = r[2] if len(r) > 2 else None
        v2 = r[3] if len(r) > 3 else None
        c = col if kind != "text" else "coalesce(%s,'')" % col
        if kind == "text":
            v = str(v or "")
            if op == "contains":
                parts.append("%s like ? escape '\\'" % c); params.append("%" + _esc(v) + "%")
            elif op == "does not contain":
                parts.append("%s not like ? escape '\\'" % c); params.append("%" + _esc(v) + "%")
            elif op == "is":
                parts.append("%s = ? collate nocase" % c); params.append(v)
            elif op == "is not":
                parts.append("%s <> ? collate nocase" % c); params.append(v)
            elif op == "begins with":
                parts.append("%s like ? escape '\\'" % c); params.append(_esc(v) + "%")
            elif op == "ends with":
                parts.append("%s like ? escape '\\'" % c); params.append("%" + _esc(v))
        elif kind in ("number", "rating"):
            c = "coalesce(%s,0)" % col
            if op == "is":
                parts.append("%s = ?" % c); params.append(float(v or 0))
            elif op == "is not":
                parts.append("%s <> ?" % c); params.append(float(v or 0))
            elif op == "is greater than":
                parts.append("%s > ?" % c); params.append(float(v or 0))
            elif op == "is less than":
                parts.append("%s < ?" % c); params.append(float(v or 0))
            elif op == "is in the range":
                parts.append("%s between ? and ?" % c); params += [float(v or 0), float(v2 or 0)]
        elif kind == "date":
            if op in ("is in the last", "is not in the last"):
                since = now - float(v or 0) * UNITS.get(v2 or "days", 86400)
                parts.append(("coalesce(%s,0) >= ?" if op == "is in the last" else "coalesce(%s,0) < ?") % col)
                params.append(since)
            elif op == "is after":
                parts.append("coalesce(%s,0) > ?" % col); params.append(float(v or 0))
            elif op == "is before":
                parts.append("coalesce(%s,0) < ?" % col); params.append(float(v or 0))
        elif kind == "bool":
            parts.append("coalesce(%s,0) %s 0" % (col, "<>" if op == "is true" else "="))
    joiner = " and " if spec.get("match", "all") == "all" else " or "
    return (joiner.join("(%s)" % p for p in parts) if parts else "1"), params


def rules_sql(spec, now=None, members=None):
    """(where clause, params, order, limit) for a Smart Playlist spec:
    {"match": "all"|"any", "rules": [rule or nested group, ...], "limit": [n, unit] or None,
     "selected_by": key, "checked_only": bool}. members(playlist id) -> track ids, for the
    "Playlist is / is not" rule."""
    now = time.time() if now is None else now
    where, params = _clause(spec, now, members)
    if spec.get("checked_only"):
        where = "(%s) and checked" % where
    where = "(%s) and not missing" % where
    order = SELECTED_BY.get(spec.get("selected_by") or "", None)
    return where, params, order, spec.get("limit")


def _esc(s):
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class Library:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript(SCHEMA)
            # columns added since the first release, for libraries made by it
            have = {r[1] for r in self.db.execute("pragma table_info(tracks)")}
            for col, decl in (("rg_measured", "integer default 0"),):
                if col not in have:
                    self.db.execute("alter table tracks add column %s %s" % (col, decl))
            if not self.get("seeded"):
                for i, (name, spec) in enumerate(DEFAULT_SMART):
                    self.db.execute("insert into playlists(name, kind, rules, position) values(?,?,?,?)",
                                    (name, "smart", json.dumps(spec), i))
                self.put("seeded", "1")
            self.db.commit()
        self.listeners = []
        self.version = 0

    # ---------------------------------------------------------------- small things
    def get(self, k, default=None):
        with self.lock:
            r = self.db.execute("select v from kv where k=?", (k,)).fetchone()
        return r[0] if r else default

    def put(self, k, v):
        with self.lock:
            self.db.execute("insert or replace into kv(k, v) values(?,?)", (k, v))
            self.db.commit()

    def changed(self, what="tracks"):
        self.version += 1
        for fn in list(self.listeners):
            try:
                fn(what)
            except Exception:
                import traceback
                traceback.print_exc()

    def q(self, sql, params=()):
        with self.lock:
            return self.db.execute(sql, params).fetchall()

    # ---------------------------------------------------------------- folders
    def folders(self):
        return [r[0] for r in self.q("select path from folders order by path")]

    def add_folder(self, path):
        path = os.path.abspath(path)
        with self.lock:
            self.db.execute("insert or ignore into folders(path) values(?)", (path,))
            self.db.commit()

    def remove_folder(self, path):
        with self.lock:
            self.db.execute("delete from folders where path=?", (path,))
            self.db.commit()

    # ---------------------------------------------------------------- tracks
    def add_file(self, path, commit=True):
        """Add or refresh one song file; returns its id (None if it isn't a song)."""
        path = os.path.abspath(path)
        try:
            st = os.stat(path)
        except OSError:
            return None
        with self.lock:
            r = self.db.execute("select id, mtime, size from tracks where path=?", (path,)).fetchone()
        if r and r["mtime"] == st.st_mtime and r["size"] == st.st_size:
            with self.lock:
                self.db.execute("update tracks set missing=0 where id=?", (r["id"],))
            return r["id"]
        try:
            t = tags.read(path)
        except Exception:
            return None
        cols = ["title", "artist", "album_artist", "album", "genre", "composer", "year", "track_no", "track_count",
                "disc_no", "disc_count", "comments", "compilation", "bpm", "grouping", "rg_track", "rg_album",
                "duration", "bitrate", "sample_rate", "channels", "kind", "has_art"]
        vals = [t[c] if not isinstance(t[c], bool) else int(t[c]) for c in cols]
        now = time.time()
        with self.lock:
            if r:
                self.db.execute("update tracks set %s, size=?, mtime=?, date_modified=?, missing=0 where id=?"
                                % ", ".join("%s=?" % c for c in cols), vals + [st.st_size, st.st_mtime, now, r["id"]])
                tid = r["id"]
            else:
                cur = self.db.execute("insert into tracks(path, %s, size, mtime, date_added, date_modified) values(?, %s, ?, ?, ?, ?)"
                                      % (", ".join(cols), ", ".join("?" * len(cols))),
                                      [path] + vals + [st.st_size, st.st_mtime, now, now])
                tid = cur.lastrowid
            if commit:
                self.db.commit()
        return tid

    def scan(self, progress=None, stop=None):
        """Look through every music folder: new and changed songs come in, deleted ones are marked
        missing. Returns (added or refreshed, missing)."""
        seen = set()
        n = 0
        for top in self.folders():
            for d, dirs, files in os.walk(top):
                dirs[:] = sorted(x for x in dirs if not x.startswith("."))
                for fn in sorted(files):
                    if stop and stop():
                        return n, 0
                    p = os.path.join(d, fn)
                    if not tags.is_audio(p):
                        continue
                    tid = self.add_file(p, commit=False)
                    if tid:
                        seen.add(tid)
                        n += 1
                        if progress and n % 25 == 0:
                            progress(n)
        with self.lock:
            self.db.commit()
        tops = self.folders()
        gone = 0
        for r in self.q("select id, path from tracks where missing=0"):
            if r["id"] in seen:
                continue
            inside = any(r["path"].startswith(t.rstrip("/") + "/") for t in tops)
            if inside and not os.path.exists(r["path"]):
                with self.lock:
                    self.db.execute("update tracks set missing=1 where id=?", (r["id"],))
                gone += 1
        with self.lock:
            self.db.commit()
        self.changed()
        return n, gone

    def track(self, tid):
        r = self.q("select * from tracks where id=?", (tid,))
        return r[0] if r else None

    def tracks(self, where="not missing", params=(), order="album_artist_sort", limit=None):
        o = {"album_artist_sort": "coalesce(nullif(album_artist,''), artist) collate nocase, album collate nocase, disc_no, track_no, title collate nocase"}.get(order, order)
        sql = "select * from tracks where %s order by %s" % (where, o)
        if limit:
            sql += " limit %d" % int(limit)
        return self.q(sql, params)

    def update(self, ids, **fields):
        if not ids:
            return
        with self.lock:
            for tid in ids:
                self.db.execute("update tracks set %s where id=?" % ", ".join("%s=?" % k for k in fields),
                                list(fields.values()) + [tid])
            self.db.commit()
        self.changed()

    def remove(self, ids):
        with self.lock:
            for tid in ids:
                self.db.execute("delete from tracks where id=?", (tid,))
                self.db.execute("delete from playlist_items where track=?", (tid,))
            self.db.commit()
        self.changed()

    def played(self, tid):
        with self.lock:
            self.db.execute("update tracks set play_count=coalesce(play_count,0)+1, last_played=?, position=0 where id=?",
                            (time.time(), tid))
            self.db.commit()
        self.changed("plays")

    def skipped(self, tid):
        with self.lock:
            self.db.execute("update tracks set skip_count=coalesce(skip_count,0)+1, last_skipped=? where id=?",
                            (time.time(), tid))
            self.db.commit()

    def rate(self, ids, rating):
        self.update(ids, rating=max(0, min(100, int(rating))))

    def stats(self, rows):
        """'12 songs, 48.3 minutes, 92.1 MB' for these songs."""
        n = len(rows)
        secs = sum(r["duration"] or 0 for r in rows)
        size = sum(r["size"] or 0 for r in rows)
        if secs >= 86400:
            t = "%.1f days" % (secs / 86400)
        elif secs >= 3600:
            t = "%.1f hours" % (secs / 3600)
        else:
            t = "%.1f minutes" % (secs / 60)
        s = "%.1f GB" % (size / 1e9) if size >= 1e9 else "%.1f MB" % (size / 1e6)
        return "%d %s, %s, %s" % (n, "song" if n == 1 else "songs", t, s)

    def browse(self, rows, column):
        """The distinct values of a column (genre, artist, album) among rows, sorted."""
        vals = {}
        for r in rows:
            v = (r[column] or "") if column != "artist" else (r["album_artist"] or r["artist"] or "")
            vals[v.lower()] = vals.get(v.lower()) or v
        return [vals[k] for k in sorted(vals)]

    # ---------------------------------------------------------------- playlists
    def playlists(self):
        return self.q("select * from playlists order by kind='folder' desc, position, name collate nocase")

    def playlist(self, pid):
        r = self.q("select * from playlists where id=?", (pid,))
        return r[0] if r else None

    def new_playlist(self, name, kind="playlist", rules=None, parent=None, tracks=()):
        with self.lock:
            pos = (self.db.execute("select max(position) from playlists").fetchone()[0] or 0) + 1
            cur = self.db.execute("insert into playlists(name, kind, rules, parent, position) values(?,?,?,?,?)",
                                  (name, kind, json.dumps(rules) if rules is not None else None, parent, pos))
            pid = cur.lastrowid
            self.db.commit()
        if tracks:
            self.add_to_playlist(pid, tracks)
        self.changed("playlists")
        return pid

    def rename_playlist(self, pid, name):
        with self.lock:
            self.db.execute("update playlists set name=? where id=?", (name, pid))
            self.db.commit()
        self.changed("playlists")

    def set_rules(self, pid, rules):
        with self.lock:
            self.db.execute("update playlists set rules=? where id=?", (json.dumps(rules), pid))
            self.db.commit()
        self.changed("playlists")

    def move_playlist(self, pid, parent):
        with self.lock:
            self.db.execute("update playlists set parent=? where id=?", (parent, pid))
            self.db.commit()
        self.changed("playlists")

    def delete_playlist(self, pid):
        with self.lock:
            for c in self.db.execute("select id from playlists where parent=?", (pid,)).fetchall():
                self.db.execute("update playlists set parent=(select parent from playlists where id=?) where id=?", (pid, c[0]))
            self.db.execute("delete from playlist_items where playlist=?", (pid,))
            self.db.execute("delete from playlists where id=?", (pid,))
            self.db.commit()
        self.changed("playlists")

    def add_to_playlist(self, pid, tids, at=None):
        with self.lock:
            n = self.db.execute("select count(*) from playlist_items where playlist=?", (pid,)).fetchone()[0]
            if at is None or at >= n:
                for i, t in enumerate(tids):
                    self.db.execute("insert into playlist_items(playlist, track, pos) values(?,?,?)", (pid, t, n + i))
            else:
                self.db.execute("update playlist_items set pos=pos+? where playlist=? and pos>=?", (len(tids), pid, at))
                for i, t in enumerate(tids):
                    self.db.execute("insert into playlist_items(playlist, track, pos) values(?,?,?)", (pid, t, at + i))
            self.db.commit()
        self.changed("playlist-items")

    def remove_from_playlist(self, pid, positions):
        items = [r["track"] for r in self.q("select track from playlist_items where playlist=? order by pos", (pid,))]
        keep = [t for i, t in enumerate(items) if i not in set(positions)]
        self._set_items(pid, keep)

    def reorder_playlist(self, pid, positions, to):
        items = [r["track"] for r in self.q("select track from playlist_items where playlist=? order by pos", (pid,))]
        moving = [items[i] for i in sorted(positions)]
        rest = [t for i, t in enumerate(items) if i not in set(positions)]
        to = to - sum(1 for i in positions if i < to)
        rest[to:to] = moving
        self._set_items(pid, rest)

    def _set_items(self, pid, tids):
        with self.lock:
            self.db.execute("delete from playlist_items where playlist=?", (pid,))
            for i, t in enumerate(tids):
                self.db.execute("insert into playlist_items(playlist, track, pos) values(?,?,?)", (pid, t, i))
            self.db.commit()
        self.changed("playlist-items")

    def playlist_tracks(self, pid):
        p = self.playlist(pid)
        if p is None:
            return []
        if p["kind"] == "smart":
            return self.smart_tracks(json.loads(p["rules"] or "{}"), _seen={pid})
        if p["kind"] == "folder":
            out, seen = [], set()
            for c in self.q("select id from playlists where parent=? order by position", (pid,)):
                for r in self.playlist_tracks(c["id"]):
                    if r["id"] not in seen:
                        seen.add(r["id"])
                        out.append(r)
            return out
        return self.q("select t.* from playlist_items i join tracks t on t.id=i.track where i.playlist=? and not t.missing order by i.pos", (pid,))

    def smart_tracks(self, spec, now=None, _seen=None):
        seen = set(_seen or ())

        def members(pid):
            if pid in seen:          # a playlist that (through others) refers to itself
                return []
            p = self.playlist(pid)
            if p is None:
                return []
            if p["kind"] == "smart":
                return [r["id"] for r in self.smart_tracks(json.loads(p["rules"] or "{}"), now, seen | {pid})]
            return [r["id"] for r in self.playlist_tracks(pid)]
        where, params, order, limit = rules_sql(spec, now, members)
        rows = self.q("select * from tracks where %s order by %s" % (
            where, order or "coalesce(nullif(album_artist,''), artist) collate nocase, album collate nocase, disc_no, track_no"), params)
        if not limit:
            return rows
        n, unit = limit
        if unit == "items":
            return rows[:int(n)]
        cap = float(n) * {"minutes": 60, "hours": 3600, "MB": 1e6, "GB": 1e9}[unit]
        col = LIMIT_BY[unit]
        out, total = [], 0.0
        for r in rows:
            v = float(r[col] or 0)
            if total + v > cap:
                continue
            total += v
            out.append(r)
        return out

    # ---------------------------------------------------------------- import/export
    def export_m3u(self, rows, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for r in rows:
                f.write("#EXTINF:%d,%s - %s\n%s\n" % (int(r["duration"] or 0), r["artist"] or "", r["title"] or "", r["path"]))

    def import_m3u(self, path, name=None):
        base = os.path.dirname(os.path.abspath(path))
        tids = []
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("file://"):
                    from urllib.parse import unquote, urlparse
                    line = unquote(urlparse(line).path)
                p = line if os.path.isabs(line) else os.path.join(base, line)
                tid = self.add_file(p)
                if tid:
                    tids.append(tid)
        return self.new_playlist(name or os.path.splitext(os.path.basename(path))[0], tracks=tids)
