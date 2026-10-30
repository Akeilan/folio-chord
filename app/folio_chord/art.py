"""Album artwork for the lists, grid, status display and Mini Player: from the song file, else a
cover picture in the album's folder (cover.jpg, folder.jpg, ...), else a plain placeholder.
Pictures from the internet (podcasts, stations) are fetched once and kept in the cache folder."""
import hashlib
import os

from gi.repository import GdkPixbuf, GLib

from . import net, tags

_cache = {}
_ORDER = []
COVERS = ("cover.jpg", "cover.png", "folder.jpg", "folder.png", "front.jpg", "front.png", "album.jpg", "albumart.jpg")


def _remember(key, pb):
    _cache[key] = pb
    _ORDER.append(key)
    while len(_ORDER) > 600:
        _cache.pop(_ORDER.pop(0), None)
    return pb


def _from_bytes(data, size):
    loader = GdkPixbuf.PixbufLoader()
    try:
        loader.write(data)
        loader.close()
    except GLib.Error:
        return None
    pb = loader.get_pixbuf()
    return _scale(pb, size) if pb else None


def _scale(pb, size):
    w, h = pb.get_width(), pb.get_height()
    if not w or not h:
        return None
    k = size / float(max(w, h))
    return pb.scale_simple(max(1, int(w * k)), max(1, int(h * k)), GdkPixbuf.InterpType.BILINEAR)


def for_song(path, size=128):
    key = ("song", path, size)
    if key in _cache:
        return _cache[key]
    pb = None
    try:
        a = tags.artwork(path)
        if a:
            pb = _from_bytes(a[0], size)
    except Exception:       # noqa: BLE001
        pb = None
    if pb is None:
        d = os.path.dirname(path)
        try:
            names = {n.lower(): n for n in os.listdir(d)}
        except OSError:
            names = {}
        for c in COVERS:
            if c in names:
                try:
                    pb = _scale(GdkPixbuf.Pixbuf.new_from_file(os.path.join(d, names[c])), size)
                except GLib.Error:
                    pb = None
                if pb:
                    break
    return _remember(key, pb)


def cache_dir():
    d = os.path.join(GLib.get_user_cache_dir(), "folio-chord", "art")
    os.makedirs(d, exist_ok=True)
    return d


def for_url(url, size, done):
    """done(pixbuf or None), later, for a picture on the internet."""
    if not url:
        done(None)
        return
    key = ("url", url, size)
    if key in _cache:
        done(_cache[key])
        return
    f = os.path.join(cache_dir(), hashlib.sha1(url.encode()).hexdigest())
    if os.path.exists(f):
        try:
            done(_remember(key, _scale(GdkPixbuf.Pixbuf.new_from_file(f), size)))
            return
        except GLib.Error:
            pass

    def fetch():
        data = net.get(url, timeout=15)
        with open(f, "wb") as fh:
            fh.write(data)
        return data

    def got(data):
        done(_remember(key, _from_bytes(data, size)))
    net.in_thread(fetch, got, lambda e: done(None))


def placeholder(size, dark=False):
    key = ("ph", size, dark)
    if key in _cache:
        return _cache[key]
    import cairo
    from gi.repository import Gdk
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(s)
    g = cairo.LinearGradient(0, 0, 0, size)
    a, b = ((0.30, 0.31, 0.34), (0.20, 0.21, 0.24)) if dark else ((0.86, 0.87, 0.89), (0.74, 0.75, 0.78))
    g.add_color_stop_rgb(0, *a)
    g.add_color_stop_rgb(1, *b)
    cr.set_source(g)
    cr.paint()
    cr.set_source_rgba(1, 1, 1, 0.55 if not dark else 0.35)
    k = size / 16.0
    cr.scale(k, k)
    # a note
    cr.move_to(6, 3.5)
    cr.line_to(12.5, 2.3)
    cr.line_to(12.5, 10.4)
    cr.arc(11, 10.8, 1.6, 0, 6.3)
    cr.fill()
    cr.rectangle(6, 3.5, 1.2, 8)
    cr.fill()
    cr.arc(5.5, 11.7, 1.6, 0, 6.3)
    cr.fill()
    pb = Gdk.pixbuf_get_from_surface(s, 0, 0, size, size)
    return _remember(key, pb)
