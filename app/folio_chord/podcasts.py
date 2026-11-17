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
  etag text, speed real default 1.0);
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
    """A feed's date in any of the forms feeds use: RFC 822 (the standard), ISO 8601 (Atom and many
    hand-made feeds) or plain "1 Sep 2025" (C8-32)."""
    import datetime
    s = (s or "").strip()
    if not s:
        return 0.0
    try:
        d = email.utils.parsedate_to_datetime(s)
        if d is not None:
            if d.tzinfo is None:
                d = d.replace(tzinfo=datetime.timezone.utc)
            return d.timestamp()
    except Exception:       # noqa: BLE001
        pass
    iso = s.replace("Z", "+00:00")
    try:
        d = datetime.datetime.fromisoformat(iso)
        if d.tzinfo is None:
            d = d.replace(tzinfo=datetime.timezone.utc)
        return d.timestamp()
    except ValueError:
        pass
    for fmt in ("%d %b %Y", "%d %B %Y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%a, %d %b %Y", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).replace(tzinfo=datetime.timezone.utc).timestamp()
        except ValueError:
            continue
    return 0.0


ATOM_NS = "http://www.w3.org/2005/Atom"


def _xml(data):
    """The feed's XML, forgiving what real feeds get wrong: blank lines before the declaration and
    a bare & in a title (C8-32)."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    data = data.lstrip(b"\xef\xbb\xbf").lstrip()
    try:
        return ET.fromstring(data)
    except ET.ParseError as first:
        fixed = re.sub(rb"&(?!(?:#\d+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);)", b"&amp;", data)
        if fixed == data:
            raise first
        return ET.fromstring(fixed)


def _parse_atom(root, base):
    from urllib.parse import urljoin
    a = {"a": ATOM_NS}

    def text(el, path):
        x = el.find(path, a)
        return (x.text or "").strip() if x is not None and x.text else ""
    link = next((l.get("href") for l in root.findall("a:link", a) if l.get("rel", "alternate") == "alternate"), "")
    icon = text(root, "a:logo") or text(root, "a:icon")
    show = {"title": text(root, "a:title"), "author": text(root, "a:author/a:name"),
            "description": text(root, "a:subtitle"), "artwork": icon, "link": link or "", "genre": ""}
    eps = []
    for en in root.findall("a:entry", a):
        enc = next((l for l in en.findall("a:link", a) if l.get("rel") == "enclosure"), None)
        if enc is None or not enc.get("href"):
            continue
        url = urljoin(base, enc.get("href")) if base else enc.get("href")
        eps.append({"guid": text(en, "a:id") or url, "title": text(en, "a:title"),
                    "published": _date(text(en, "a:published") or text(en, "a:updated")), "duration": 0.0,
                    "url": url, "mime": enc.get("type") or "",
                    "size": int(enc.get("length")) if (enc.get("length") or "").isdigit() else 0,
                    "description": text(en, "a:content") or text(en, "a:summary"),
                    "link": next((l.get("href") for l in en.findall("a:link", a) if l.get("rel", "alternate") == "alternate"), "")})
    return show, eps


def parse_feed(data, base=None):
    """A podcast RSS or Atom feed: ({"title", "author", "description", "artwork", "link", "genre"},
    [episode]). base: the feed's address, for episode addresses given relative to it."""
    from urllib.parse import urljoin
    root = _xml(data)
    if root.tag == "{%s}feed" % ATOM_NS:
        return _parse_atom(root, base)
    ch = root.find("channel")
    if ch is None:
        raise ValueError("the address doesn't lead to a podcast feed")
    ns = {"itunes": ITUNES_NS, "content": CONTENT_NS}
    img = ch.find("itunes:image", ns)
    art = img.get("href") if img is not None else _text(ch, "image/url")
    cat = ch.find("itunes:category", ns)
    show = {"title": _text(ch, "title"), "author": _text(ch, "itunes:author", ns) or _text(ch, "managingEditor"),
            "description": _text(ch, "description") or _text(ch, "itunes:summary", ns), "artwork": art or "",
            "link": _text(ch, "link"), "genre": cat.get("text") if cat is not None else ""}
    eps = []
    seen_guids = set()
    for it in ch.findall("item"):
        enc = it.find("enclosure")
        if enc is None or not enc.get("url"):
            continue
        url = urljoin(base, enc.get("url")) if base else enc.get("url")
        guid = _text(it, "guid") or url
        if guid in seen_guids:
            guid = "%s#%s" % (guid, url)        # a feed that repeats one guid keeps every episode
        seen_guids.add(guid)
        eps.append({"guid": guid, "title": _text(it, "title"),
                    "published": _date(_text(it, "pubDate") or _text(it, "{http://purl.org/dc/elements/1.1/}date")),
                    "duration": _duration(_text(it, "itunes:duration", ns)), "url": url,
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
            have = {r[1] for r in lib.db.execute("pragma table_info(podcasts)")}
            if "speed" not in have:
                lib.db.execute("alter table podcasts add column speed real default 1.0")
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
        if data is None:
            data, moved = net.fetch(feed)
            feed = moved or feed            # a feed that has moved is kept at its new address (C8-32)
        show, eps = parse_feed(data, feed)
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
        # on subscribing only the newest episode is new, whichever end of the feed it is at (C8-31)
        newest = max(range(len(eps)), key=lambda i: (eps[i]["published"], -i)) if eps else -1
        with self.lib.lock:
            for i, e in enumerate(eps):
                cur = self.lib.db.execute(
                    "insert or ignore into episodes(podcast, guid, title, published, duration, url, mime, size, description, link, new) "
                    "values(?,?,?,?,?,?,?,?,?,?,?)", (pid, e["guid"], e["title"], e["published"], e["duration"], e["url"],
                                                      e["mime"], e["size"], e["description"], e["link"],
                                                      0 if first and i != newest else 1))
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
        feed = p["feed"]
        if data is None:
            data, moved = net.fetch(feed)
            if moved and moved != feed:
                with self.lib.lock:
                    try:
                        self.lib.db.execute("update podcasts set feed=? where id=?", (moved, pid))
                        self.lib.db.commit()
                        feed = moved
                    except Exception:       # noqa: BLE001 — already subscribed at the new address
                        pass
        show, eps = parse_feed(data, feed)
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

    def set_speed(self, pid, speed):
        with self.lib.lock:
            self.lib.db.execute("update podcasts set speed=? where id=?", (float(speed), pid))
            self.lib.db.commit()

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
        """The shows in an OPML file, folders included; the feed attribute is read whatever its
        case (xmlUrl, xmlurl) and as url when a program wrote that instead."""
        root = _xml(open(path, "rb").read())
        out = []
        for o in root.iter("outline"):
            attrs = {k.lower(): v for k, v in o.attrib.items()}
            feed = attrs.get("xmlurl") or (attrs.get("url") if (attrs.get("type") or "rss").lower() in ("rss", "atom", "link", "") else None)
            if feed and feed.lower().startswith(("http://", "https://")):
                out.append((attrs.get("text") or attrs.get("title") or "", feed))
        return out
