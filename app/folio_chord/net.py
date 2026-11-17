"""Fetching from the internet for radio and podcasts: plain HTTPS GETs with Folio Chord's name as
the user agent, nothing else sent. Runs off the main thread (in_thread)."""
import json
import threading
import urllib.parse
import urllib.request

from . import VERSION

AGENT = "FolioChord/%s" % VERSION
TIMEOUT = 20


class _Redirects(urllib.request.HTTPRedirectHandler):
    """Remembers where a permanent redirect (301, 308) led, so a podcast feed that has moved can
    be kept at its new address (C8-32)."""

    def __init__(self):
        self.moved_to = None

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if code in (301, 308):
            self.moved_to = newurl
        return super().redirect_request(req, fp, code, msg, headers, newurl)

    http_error_308 = urllib.request.HTTPRedirectHandler.http_error_302


def fetch(url, headers=None, timeout=TIMEOUT):
    """(body, the address it has permanently moved to or None). A compressed reply is unpacked."""
    h = {"User-Agent": AGENT, "Accept": "*/*", "Accept-Encoding": "gzip"}
    h.update(headers or {})
    red = _Redirects()
    opener = urllib.request.build_opener(red)
    req = urllib.request.Request(url, headers=h)
    with opener.open(req, timeout=timeout) as r:
        data = r.read()
        enc = (r.headers.get("Content-Encoding") or "").lower()
    if enc == "gzip" or data[:2] == b"\x1f\x8b":
        import gzip
        try:
            data = gzip.decompress(data)
        except OSError:
            pass
    return data, red.moved_to


def get(url, headers=None, timeout=TIMEOUT):
    return fetch(url, headers, timeout)[0]


def explain(e):
    """An error from the network in words a person can act on (C8-33)."""
    import socket
    import urllib.error
    import xml.etree.ElementTree as ET
    if isinstance(e, urllib.error.HTTPError):
        return {404: "the address wasn't found there (404)", 403: "the site refused (403)", 401: "the site asks for a sign-in",
                410: "it has been taken down (410)", 429: "the site asks to wait before trying again"}.get(
                    e.code, "the site answered with an error (%d)" % e.code)
    reason = getattr(e, "reason", e)
    if isinstance(reason, socket.gaierror):
        return "the address couldn't be found; check the internet connection"
    if isinstance(reason, ConnectionRefusedError):
        return "nothing answered there; check the internet connection"
    if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(reason):
        return "it took too long to answer; try again later"
    if isinstance(reason, OSError) and getattr(reason, "errno", None) in (101, 113):
        return "this computer isn't connected to the internet"
    if "CERTIFICATE" in str(reason).upper():
        return "the site's security certificate isn't valid"
    if isinstance(e, ET.ParseError):
        return "the address doesn't lead to a podcast feed"
    if isinstance(e, IncompleteDownload):
        return str(e)
    return str(e)


class IncompleteDownload(OSError):
    pass


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
    try:
        return _download(req, dest, part, progress, stop)
    except BaseException:
        if os.path.exists(part):
            os.remove(part)
        raise


def _download(req, dest, part, progress, stop):
    import os
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r, open(part, "wb") as f:
        if (r.headers.get("Content-Type") or "").lower().startswith("text/html"):
            raise IncompleteDownload("the site sent a web page instead of the episode (it may ask you to sign in)")
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
    if total and done < total:
        # the connection ended early: a cut-off file is not a download (C8-07)
        os.remove(part)
        raise IncompleteDownload("the download stopped after %.1f of %.1f MB; try again" % (done / 1e6, total / 1e6))
    os.replace(part, dest)
    return True


def in_thread(work, done=None, error=None):
    """Run work() on a thread; done(result) or error(exception) on the main loop."""
    from gi.repository import GLib

    def run():
        try:
            res = work()
        except Exception as e:      # noqa: BLE001
            err = e
            if error:
                GLib.idle_add(lambda: (error(err), False)[1])
            return
        if done:
            GLib.idle_add(lambda: (done(res), False)[1])
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t
