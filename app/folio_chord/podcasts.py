"""Podcasts (C3-06): find shows in a directory, subscribe, and keep their episodes.

Directories (Options > Podcasts):
  apple         Apple's public podcast search and charts (no account, no sign-in): the directory
                MusicPod searches, so the same shows turn up. The default.
  podcastindex  Podcast Index (podcastindex.org), the independent directory; needs a free API key
                and secret from podcastindex.org, entered in Options.

Subscriptions and episodes live in the library database. Episodes stream, or download into the
podcast folder; played marks and the place you stopped are kept per episode.
"""
import email.utils
import hashlib
import os
import re
import time
import xml.etree.ElementTree as ET

from . import net

APPLE = os.environ.get("FOLIO_CHORD_APPLE_API", "https://itunes.apple.com")
PODCASTINDEX = os.environ.get("FOLIO_CHORD_PODCASTINDEX_API", "https://api.podcastindex.org/api/1.0")

# Apple's podcast categories (the chart genres)
GENRES = [("All", 26), ("Arts", 1301), ("Business", 1321), ("Comedy", 1303), ("Education", 1304),
          ("Fiction", 1483), ("Government", 1511), ("Health & Fitness", 1512), ("History", 1487),
          ("Kids & Family", 1305), ("Leisure", 1502), ("Music", 1310), ("News", 1489),
          ("Religion & Spirituality", 1314), ("Science", 1533), ("Society & Culture", 1324),
          ("Sports", 1545), ("Technology", 1318), ("True Crime", 1488), ("TV & Film", 1309)]
COUNTRIES = [("United States", "us"), ("Netherlands", "nl"), ("United Kingdom", "gb"), ("Canada", "ca"),
             ("Australia", "au"), ("Ireland", "ie"), ("New Zealand", "nz"), ("Germany", "de"), ("Belgium", "be"),
             ("France", "fr"), ("Spain", "es"), ("Italy", "it"), ("Sweden", "se"), ("Norway", "no"),
             ("Denmark", "dk"), ("Austria", "at"), ("Switzerland", "ch"), ("Brazil", "br"), ("Mexico", "mx"),
             ("India", "in"), ("Japan", "jp"), ("South Africa", "za")]

SCHEMA = """
create table if not exists podcasts(
  id integer primary key, feed text unique, title text, author text, description text, artwork text,
  link text, genre text, added real, refreshed real, auto_download integer default 1, keep integer default 0,
  etag text);
create table if not exists episodes(
  id integer primary key, podcast integer, guid text, title text, published real, duration real,
  url text, mime text, size integer, description text, link text, played integer default 0,
  position real default 0, file text, new integer default 1, unique(podcast, guid));
create index if not exists ep_pod on episodes(podcast, published);
"""

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"


# ---------------------------------------------------------------- directories
def _show(title, author, feed, artwork, genre="", count=0, ident=""):
    return {"title": title or "", "author": author or "", "feed": feed or "", "artwork": artwork or "",
            "genre": genre or "", "episodes": int(count or 0), "id": str(ident or "")}


class Apple:
    name = "Apple Podcasts directory"

    def search(self, term, country="us", limit=50):
        d = net.get_json(net.url(APPLE, "/search", term=term, media="podcast", entity="podcast",
                                 country=country, limit=limit))
        return [_show(r.get("collectionName"), r.get("artistName"), r.get("feedUrl"),
                      r.get("artworkUrl600") or r.get("artworkUrl100"), r.get("primaryGenreName"),
                      r.get("trackCount"), r.get("collectionId"))
                for r in d.get("results", []) if r.get("feedUrl")]

    def charts(self, country="us", genre=26, limit=50):
        """The top shows in a country, for a category: Apple's chart, then each show looked up for
        its feed."""
        ids = []
        try:
            d = net.get_json(net.url(APPLE, "/%s/rss/toppodcasts/limit=%d/genre=%d/json" % (country, limit, genre)))
            for e in (d.get("feed", {}).get("entry") or []):
                i = (e.get("id") or {}).get("attributes", {}).get("im:id")
                if i:
                    ids.append(i)
        except Exception:      # noqa: BLE001 — the newer chart feed has no categories
            d = net.get_json("https://rss.applemarketingtools.com/api/v2/%s/podcasts/top/%d/podcasts.json" % (country, limit)) \
                if APPLE.startswith("https://itunes.apple.com") else {"feed": {"results": []}}
            ids = [r["id"] for r in d.get("feed", {}).get("results", []) if r.get("id")]
        if not ids:
            return []
        out = []
        for i in range(0, len(ids), 100):
            d = net.get_json(net.url(APPLE, "/lookup", id=",".join(ids[i:i + 100]), entity="podcast", country=country))
            by = {str(r.get("collectionId")): r for r in d.get("results", [])}
            for k in ids[i:i + 100]:
                r = by.get(str(k))
                if r and r.get("feedUrl"):
                    out.append(_show(r.get("collectionName"), r.get("artistName"), r.get("feedUrl"),
                                     r.get("artworkUrl600") or r.get("artworkUrl100"), r.get("primaryGenreName"),
                                     r.get("trackCount"), r.get("collectionId")))
        return out


class PodcastIndex:
    name = "Podcast Index"

    def __init__(self, key, secret):
        self.key, self.secret = key or "", secret or ""

    def _headers(self):
        now = str(int(time.time()))
        return {"X-Auth-Date": now, "X-Auth-Key": self.key,
                "Authorization": hashlib.sha1((self.key + self.secret + now).encode()).hexdigest()}

    def _feeds(self, d):
        return [_show(f.get("title"), f.get("author") or f.get("ownerName"), f.get("url"),
                      f.get("artwork") or f.get("image"), ", ".join((f.get("categories") or {}).values()),
                      f.get("episodeCount"), f.get("id"))
                for f in d.get("feeds", []) if f.get("url")]

    def search(self, term, country=None, limit=50):
        if not self.key:
            raise ValueError("Podcast Index needs an API key and secret: File > Options > Podcasts.")
        return self._feeds(net.get_json(net.url(PODCASTINDEX, "/search/byterm", q=term, max=limit), self._headers()))

    def charts(self, country="us", genre=26, limit=50):
        if not self.key:
            raise ValueError("Podcast Index needs an API key and secret: File > Options > Podcasts.")
        cat = dict((g, n) for n, g in GENRES).get(genre)
        return self._feeds(net.get_json(net.url(PODCASTINDEX, "/podcasts/trending", max=limit,
                                                cat=None if genre == 26 else cat, lang=None), self._headers()))


def directory(settings):
    if settings.get("podcast_directory") == "podcastindex":
        return PodcastIndex(settings.get("podcastindex_key"), settings.get("podcastindex_secret"))
    return Apple()


# ---------------------------------------------------------------- feeds
def _text(el, path, ns=None):
    x = el.find(path, ns or {})
    return (x.text or "").strip() if x is not None and x.text else ""


def _duration(s):
    s = (s or "").strip()
    if not s:
        return 0.0
    try:
        parts = [float(p) for p in s.split(":")]
    except ValueError:
        return 0.0
    v = 0.0
    for p in parts:
        v = v * 60 + p
    return v


def _date(s):
    try:
        return email.utils.parsedate_to_datetime(s).timestamp()
    except Exception:       # noqa: BLE001
        return 0.0


def parse_feed(data):
    """A podcast RSS feed: ({"title", "author", "description", "artwork", "link", "genre"}, [episode])."""
    root = ET.fromstring(data)
    ch = root.find("channel")
    if ch is None:
        raise ValueError("not a podcast feed")
    ns = {"itunes": ITUNES_NS, "content": CONTENT_NS}
    img = ch.find("itunes:image", ns)
    art = img.get("href") if img is not None else _text(ch, "image/url")
    cat = ch.find("itunes:category", ns)
    show = {"title": _text(ch, "title"), "author": _text(ch, "itunes:author", ns) or _text(ch, "managingEditor"),
            "description": _text(ch, "description") or _text(ch, "itunes:summary", ns), "artwork": art or "",
            "link": _text(ch, "link"), "genre": cat.get("text") if cat is not None else ""}
    eps = []
    for it in ch.findall("item"):
        enc = it.find("enclosure")
        if enc is None or not enc.get("url"):
            continue
        guid = _text(it, "guid") or enc.get("url")
        eps.append({"guid": guid, "title": _text(it, "title"), "published": _date(_text(it, "pubDate")),
                    "duration": _duration(_text(it, "itunes:duration", ns)), "url": enc.get("url"),
                    "mime": enc.get("type") or "", "size": int(enc.get("length") or 0) if (enc.get("length") or "").isdigit() else 0,
                    "description": _text(it, "content:encoded", ns) or _text(it, "description") or _text(it, "itunes:summary", ns),
                    "link": _text(it, "link")})
    return show, eps


def plain(html):
    """Show notes as text."""
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", html or "")
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    import html as H
    return re.sub(r"\n{3,}", "\n\n", H.unescape(s)).strip()


# ---------------------------------------------------------------- subscriptions
class Podcasts:
    def __init__(self, lib, folder):
        self.lib = lib
        self.folder = folder
        with lib.lock:
            lib.db.executescript(SCHEMA)
            lib.db.commit()

    def shows(self):
        return self.lib.q("select p.*, (select count(*) from episodes e where e.podcast=p.id and not e.played) as unplayed "
                          "from podcasts p order by title collate nocase")

    def show(self, pid):
        r = self.lib.q("select * from podcasts where id=?", (pid,))
        return r[0] if r else None

    def episodes(self, pid=None, where="1", params=()):
        if pid is not None:
            return self.lib.q("select * from episodes where podcast=? and %s order by published desc" % where, (pid,) + tuple(params))
        return self.lib.q("select * from episodes where %s order by published desc" % where, params)

    def episode(self, eid):
        r = self.lib.q("select * from episodes where id=?", (eid,))
        return r[0] if r else None

    def subscribe(self, feed, data=None):
        """Subscribe to a feed (fetching it unless data is given); returns the show's id."""
        data = data if data is not None else net.get(feed)
        show, eps = parse_feed(data)
        with self.lib.lock:
            self.lib.db.execute("insert or ignore into podcasts(feed, title, author, description, artwork, link, genre, added, refreshed) "
                                "values(?,?,?,?,?,?,?,?,?)", (feed, show["title"], show["author"], show["description"],
                                                               show["artwork"], show["link"], show["genre"], time.time(), time.time()))
            pid = self.lib.db.execute("select id from podcasts where feed=?", (feed,)).fetchone()[0]
            self.lib.db.commit()
        self._store(pid, eps, first=True)
        self.lib.changed("podcasts")
        return pid

    def _store(self, pid, eps, first=False):
        new = []
        with self.lib.lock:
            for i, e in enumerate(eps):
                cur = self.lib.db.execute(
                    "insert or ignore into episodes(podcast, guid, title, published, duration, url, mime, size, description, link, new) "
                    "values(?,?,?,?,?,?,?,?,?,?,?)", (pid, e["guid"], e["title"], e["published"], e["duration"], e["url"],
                                                      e["mime"], e["size"], e["description"], e["link"],
                                                      0 if first and i > 0 else 1))
                if cur.rowcount:
                    new.append(cur.lastrowid)
                else:
                    self.lib.db.execute("update episodes set title=?, url=?, duration=coalesce(nullif(?,0),duration), description=? "
                                        "where podcast=? and guid=?", (e["title"], e["url"], e["duration"], e["description"], pid, e["guid"]))
            self.lib.db.execute("update podcasts set refreshed=? where id=?", (time.time(), pid))
            self.lib.db.commit()
        return new

    def refresh(self, pid, data=None):
        """Fetch the feed again; returns the ids of new episodes."""
        p = self.show(pid)
        data = data if data is not None else net.get(p["feed"])
        show, eps = parse_feed(data)
        with self.lib.lock:
            self.lib.db.execute("update podcasts set title=?, author=?, description=?, artwork=? where id=?",
                                (show["title"] or p["title"], show["author"], show["description"], show["artwork"] or p["artwork"], pid))
            self.lib.db.commit()
        new = self._store(pid, eps)
        self.lib.changed("podcasts")
        return new

    def unsubscribe(self, pid, delete_files=True):
        if delete_files:
            for e in self.episodes(pid, "file is not null"):
                try:
                    os.remove(e["file"])
                except OSError:
                    pass
        with self.lib.lock:
            self.lib.db.execute("delete from episodes where podcast=?", (pid,))
            self.lib.db.execute("delete from podcasts where id=?", (pid,))
            self.lib.db.commit()
        self.lib.changed("podcasts")

    def set(self, eid, **fields):
        with self.lib.lock:
            self.lib.db.execute("update episodes set %s where id=?" % ", ".join("%s=?" % k for k in fields),
                                list(fields.values()) + [eid])
            self.lib.db.commit()
        self.lib.changed("episodes")

    def mark_played(self, eids, played=True):
        for e in eids:
            self.set(e, played=1 if played else 0, position=0, new=0)

    def set_auto_download(self, pid, on):
        with self.lib.lock:
            self.lib.db.execute("update podcasts set auto_download=? where id=?", (1 if on else 0, pid))
            self.lib.db.commit()

    def file_for(self, ep):
        p = self.show(ep["podcast"])
        ext = os.path.splitext(ep["url"].split("?")[0])[1] or {"audio/mpeg": ".mp3", "audio/x-m4a": ".m4a",
                                                                "audio/mp4": ".m4a", "audio/ogg": ".ogg"}.get(ep["mime"], ".mp3")
        safe = lambda s: re.sub(r"[^\w\- .,()']+", "_", s or "untitled").strip()[:80]  # noqa: E731
        d = os.path.join(self.folder, safe(p["title"] if p else "Podcast"))
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, safe(ep["title"]) + "-" + hashlib.md5(ep["guid"].encode()).hexdigest()[:6] + ext)

    def download(self, eid, progress=None, stop=None):
        ep = self.episode(eid)
        dest = self.file_for(ep)
        if net.download(ep["url"], dest, progress, stop):
            self.set(eid, file=dest)
            return dest
        return None

    def delete_download(self, eid):
        ep = self.episode(eid)
        if ep and ep["file"]:
            try:
                os.remove(ep["file"])
            except OSError:
                pass
            self.set(eid, file=None)

    def to_download(self):
        """New episodes of shows set to download them automatically."""
        return [e["id"] for e in self.lib.q(
            "select e.id from episodes e join podcasts p on p.id=e.podcast "
            "where p.auto_download and e.new and e.file is null and not e.played order by e.published desc")]

    # ---------------------------------------------------------------- OPML
    def export_opml(self, path):
        from xml.sax.saxutils import quoteattr
        with open(path, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<opml version="2.0">\n<head><title>Folio Chord podcasts</title></head>\n<body>\n')
            for p in self.shows():
                f.write('  <outline type="rss" text=%s title=%s xmlUrl=%s/>\n' % (quoteattr(p["title"] or ""), quoteattr(p["title"] or ""), quoteattr(p["feed"])))
            f.write("</body>\n</opml>\n")

    @staticmethod
    def read_opml(path):
        root = ET.parse(path).getroot()
        return [(o.get("text") or o.get("title") or "", o.get("xmlUrl")) for o in root.iter("outline") if o.get("xmlUrl")]
