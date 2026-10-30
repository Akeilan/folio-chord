"""Fetching from the internet for radio and podcasts: plain HTTPS GETs with Folio Chord's name as
the user agent, nothing else sent. Runs off the main thread (in_thread)."""
import json
import threading
import urllib.parse
import urllib.request

from . import VERSION

AGENT = "FolioChord/%s" % VERSION
TIMEOUT = 20


def get(url, headers=None, timeout=TIMEOUT):
    h = {"User-Agent": AGENT, "Accept": "*/*"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def get_json(url, headers=None, timeout=TIMEOUT):
    return json.loads(get(url, headers, timeout).decode("utf-8", "replace"))


def url(base, path, **params):
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    return base.rstrip("/") + path + ("?" + q if q else "")


def download(url_, dest, progress=None, stop=None, headers=None):
    """Save url_ to dest (through a .part file). progress(done, total)."""
    import os
    h = {"User-Agent": AGENT}
    h.update(headers or {})
    req = urllib.request.Request(url_, headers=h)
    part = dest + ".part"
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if stop and stop():
                f.close()
                os.remove(part)
                return False
            b = r.read(65536)
            if not b:
                break
            f.write(b)
            done += len(b)
            if progress:
                progress(done, total)
    os.replace(part, dest)
    return True


def in_thread(work, done=None, error=None):
    """Run work() on a thread; done(result) or error(exception) on the main loop."""
    from gi.repository import GLib

    def run():
        try:
            res = work()
        except Exception as e:      # noqa: BLE001
            if error:
                GLib.idle_add(lambda: (error(e), False)[1])
            return
        if done:
            GLib.idle_add(lambda: (done(res), False)[1])
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t
