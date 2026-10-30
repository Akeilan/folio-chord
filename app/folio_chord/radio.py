"""Internet radio (C3-05): the community station directory radio-browser.info, the one MusicPod
uses. No account; Folio Chord only asks for stations and, when one is played, tells the directory
which (that is how its popular stations are counted, as its rules ask).

  d = Directory()
  d.search(name=, tag=, country=, language=, order="votes", limit=100) -> [station]
  d.top(n), d.tags(), d.countries(), d.languages()
  d.clicked(station)

A station: {"uuid", "name", "url", "homepage", "favicon", "tags": [..], "country", "countrycode",
"language", "codec", "bitrate", "votes", "clicks"}. Favourites are kept in the library (kv).
"""
import json
import os
import random
import socket

from . import net

FALLBACK = ["https://de1.api.radio-browser.info", "https://de2.api.radio-browser.info",
            "https://fi1.api.radio-browser.info", "https://at1.api.radio-browser.info"]


def servers():
    """The directory's servers, in random order (its rules: look them up, pick one, fall back)."""
    env = os.environ.get("FOLIO_CHORD_RADIO_API")
    if env:
        return [env]
    names = []
    try:
        for fam, _t, _p, _c, sa in socket.getaddrinfo("all.api.radio-browser.info", 443, proto=socket.IPPROTO_TCP):
            try:
                host = socket.gethostbyaddr(sa[0])[0]
            except OSError:
                continue
            if host.endswith(".radio-browser.info") and "https://" + host not in names:
                names.append("https://" + host)
    except OSError:
        pass
    random.shuffle(names)
    return names + [s for s in FALLBACK if s not in names]


def station(d):
    return {"uuid": d.get("stationuuid") or "", "name": (d.get("name") or "").strip(),
            "url": d.get("url_resolved") or d.get("url") or "", "homepage": d.get("homepage") or "",
            "favicon": d.get("favicon") or "",
            "tags": [t.strip() for t in (d.get("tags") or "").split(",") if t.strip()],
            "country": d.get("country") or "", "countrycode": d.get("countrycode") or "",
            "language": d.get("language") or "", "codec": d.get("codec") or "",
            "bitrate": int(d.get("bitrate") or 0), "votes": int(d.get("votes") or 0),
            "clicks": int(d.get("clickcount") or 0)}


class Directory:
    def __init__(self):
        self._servers = None
        self.base = None

    def _get(self, path, **params):
        if self._servers is None:
            self._servers = servers()
        last = None
        order = ([self.base] if self.base else []) + [s for s in self._servers if s != self.base]
        for base in order:
            try:
                r = net.get_json(net.url(base, path, **params))
                self.base = base
                return r
            except Exception as e:      # noqa: BLE001 — try the next server
                last = e
        raise last or OSError("no radio directory server answered")

    def search(self, name=None, tag=None, country=None, countrycode=None, language=None, order="votes",
               limit=100, offset=0):
        rows = self._get("/json/stations/search", name=name, tag=tag, country=country, countrycode=countrycode,
                         language=language, order=order, reverse="true" if order in ("votes", "clickcount", "bitrate") else "false",
                         limit=limit, offset=offset, hidebroken="true")
        return [station(d) for d in rows]

    def top(self, n=100, by="topvote"):
        return [station(d) for d in self._get("/json/stations/%s/%d" % (by, n), hidebroken="true")]

    def by_uuid(self, uuids):
        if not uuids:
            return []
        return [station(d) for d in self._get("/json/stations/byuuid", uuids=",".join(uuids))]

    def _names(self, what, limit):
        rows = self._get("/json/" + what, order="stationcount", reverse="true", hidebroken="true", limit=limit)
        return [(r.get("name") or "", int(r.get("stationcount") or 0), r.get("iso_3166_1") or "") for r in rows if r.get("name")]

    def tags(self, limit=200):
        return self._names("tags", limit)

    def countries(self, limit=300):
        return self._names("countries", limit)

    def languages(self, limit=200):
        return self._names("languages", limit)

    def clicked(self, st):
        try:
            self._get("/json/url/" + st["uuid"])
        except Exception:       # noqa: BLE001 — counting is a courtesy
            pass


# ---------------------------------------------------------------- favourites (kept in the library)
def favourites(lib):
    try:
        return json.loads(lib.get("radio_favourites") or "[]")
    except ValueError:
        return []


def is_favourite(lib, st):
    return any(f["uuid"] == st["uuid"] for f in favourites(lib))


def set_favourite(lib, st, on):
    favs = [f for f in favourites(lib) if f["uuid"] != st["uuid"]]
    if on:
        favs.append(st)
    lib.put("radio_favourites", json.dumps(favs))
    lib.changed("radio")


def recent(lib):
    try:
        return json.loads(lib.get("radio_recent") or "[]")
    except ValueError:
        return []


def played(lib, st):
    r = [x for x in recent(lib) if x["uuid"] != st["uuid"]]
    r.insert(0, st)
    lib.put("radio_recent", json.dumps(r[:30]))
