"""Chordamp (C3-27..C3-34): the classic small-player look. View > Look > Chordamp swaps the Standard
window for a set of small skinned windows — the player, the equalizer, the playlist editor and a
media library — that dock and snap together; View > Look > Standard (or Ctrl+Shift+W, or the
options menu) brings the Standard window back. Everything is drawn from a skin (skin.py):
Chordamp's own, or a classic .wsz skin you load.

  switch(win, look)   look: "standard" | "classic"; remembered in settings["look"]
"""
import os
import time

import cairo
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo

from . import skin as skinmod
from . import views

W, H = 275, 116
SNAP = 10


def switch(win, look):
    look = "classic" if look in ("classic", "chordamp") else "standard"
    app = win.app
    win.settings.set("look", look)
    ca = getattr(app, "chordamp", None)
    if look == "classic":
        if ca is None:
            ca = app.chordamp = Chordamp(win)
        ca.show()
        win.hide()
        return ca
    if ca is not None:
        ca.hide()
    win.show()
    win.present()
    return win


def wayland():
    d = Gdk.Display.get_default()
    return d is not None and type(d).__name__.lower().find("wayland") >= 0


def _text_bitmap_cols():
    rows = ['abcdefghijklmnopqrstuvwxyz"@   ', "0123456789….:()-'!_+\\/[]^&%,=$#", "ÅÖÄ?*"]
    m = {}
    for r, line in enumerate(rows):
        for c, ch in enumerate(line):
            if ch != " " or (r, c) == (0, 30):
                m.setdefault(ch, (c * 5, r * 6))
    return m


TEXT_MAP = _text_bitmap_cols()


def bitmap_text(sk, cr, s, x, y, maxw=None):
    """Classic text.bmp text (5x6 a letter); returns the width drawn."""
    cx = x
    for ch in s:
        if maxw is not None and cx - x >= maxw:
            break
        c = ch.lower()
        sx, sy = TEXT_MAP.get(c, TEXT_MAP.get(" ", (150, 0)))
        sk.blit(cr, "text", sx, sy, 5, 6, cx, y)
        cx += 5
    return cx - x


def plain_text(cr, s, x, y, col, size=7.5, bold=False, font="Sans"):
    layout = PangoCairo.create_layout(cr)
    fd = Pango.FontDescription.from_string("%s %s%.1fpx" % (font, "Bold " if bold else "", size))
    fd.set_absolute_size(size * Pango.SCALE)
    if bold:
        fd.set_weight(Pango.Weight.BOLD)
    layout.set_font_description(fd)
    layout.set_text(s, -1)
    cr.set_source_rgb(*col)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, layout)
    return layout.get_pixel_size()[0]


def text_width(cr, s, size=7.5, bold=False, font="Sans"):
    layout = PangoCairo.create_layout(cr)
    fd = Pango.FontDescription.from_string(font)
    fd.set_absolute_size(size * Pango.SCALE)
    if bold:
        fd.set_weight(Pango.Weight.BOLD)
    layout.set_font_description(fd)
    layout.set_text(s, -1)
    return layout.get_pixel_size()[0]


def item_name(ca, key):
    """'Artist - Title' for a playlist entry (a song id or ('e', episode id))."""
    if isinstance(key, (tuple, list)):
        e = ca.app.pods.episode(key[1])
        if not e:
            return "?"
        p = ca.app.pods.show(e["podcast"])
        return "%s - %s" % (p["title"] if p else "", e["title"])
    r = ca.lib.track(key)
    if not r:
        return "?"
    return "%s - %s" % (r["artist"], r["title"]) if r["artist"] else (r["title"] or os.path.basename(r["path"] or ""))


def item_length(ca, key):
    if isinstance(key, (tuple, list)):
        e = ca.app.pods.episode(key[1])
        return float((e or {"duration": 0})["duration"] or 0)
    r = ca.lib.track(key)
    return float((r or {"duration": 0})["duration"] or 0)


# ======================================================================== a skinned window
class SkinWindow(Gtk.Window):
    name = "?"
    base = (W, H)

    def __init__(self, ca, title):
        super().__init__(title=title)
        self.ca = ca
        self.set_application(ca.app)
        self.get_style_context().add_class("chord-classic")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_icon_name("folio-chord")
        self.area = Gtk.DrawingArea()
        self.area.set_can_focus(True)
        self.area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                             Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.SCROLL_MASK |
                             Gdk.EventMask.KEY_PRESS_MASK)
        self.area.connect("draw", self._draw)
        self.area.connect("button-press-event", self._press)
        self.area.connect("button-release-event", self._release)
        self.area.connect("motion-notify-event", self._motion)
        self.area.connect("scroll-event", self._scroll)
        self.add(self.area)
        self.connect("key-press-event", lambda w, e: ca.key(e))
        self.connect("delete-event", lambda *_: (self.ca.window_closed(self), True)[1])
        self.connect("focus-in-event", lambda *_: self.area.queue_draw())
        self.connect("focus-out-event", lambda *_: self.area.queue_draw())
        self.pressed = None         # the hit region held down
        self.drag = None            # ("move", x0, y0, wx, wy, docked) or ("slider", name)
        self.resize_to()

    # geometry ---------------------------------------------------------
    def size(self):
        return self.base

    def resize_to(self):
        w, h = self.size()
        s = self.ca.scale
        self.area.set_size_request(w * s, h * s)
        self.resize(w * s, h * s)
        if getattr(self.ca, "stack", None) is not None:
            self.ca.stack.resize(1, 1)      # shrink to fit when a part gets smaller

    def rect(self):
        x, y = self.get_position()
        w, h = self.size()
        return x, y, w * self.ca.scale, h * self.ca.scale

    def focused(self):
        return (self.ca.stack or self).is_active()

    # drawing ----------------------------------------------------------
    def _draw(self, area, cr):
        cr.scale(self.ca.scale, self.ca.scale)
        cr.set_antialias(cairo.ANTIALIAS_NONE if self.ca.scale == 1 else cairo.ANTIALIAS_DEFAULT)
        try:
            self.paint(cr)
        except Exception:       # noqa: BLE001 — a broken skin must not take the player down
            import traceback
            traceback.print_exc()
        return True

    def paint(self, cr):
        pass

    def regions(self):
        """[(name, x, y, w, h)] in skin pixels; the first hit wins."""
        return []

    def hit(self, x, y):
        for r in self.regions():
            name, rx, ry, rw, rh = r
            if rx <= x < rx + rw and ry <= y < ry + rh:
                return name
        return None

    def title_hit(self, x, y):
        return y < 14

    # mouse ------------------------------------------------------------
    def _xy(self, e):
        return e.x / self.ca.scale, e.y / self.ca.scale

    def _press(self, w, e):
        self.area.grab_focus()
        self.ca.active_part = self
        x, y = self._xy(e)
        if e.button == 3:
            self.ca.options_menu(e)
            return True
        if e.button != 1:
            return False
        if e.type == Gdk.EventType._2BUTTON_PRESS:
            self.double(x, y)
            return True
        name = self.hit(x, y)
        if name:
            self.pressed = name
            if self.is_slider(name):
                self.drag = ("slider", name)
                self.slide(name, x, y)
            self.area.queue_draw()
            return True
        if self.title_hit(x, y) or self.drag_anywhere(x, y):
            self.ca.begin_move(self, e)
        return True

    def _motion(self, w, e):
        if self.drag and self.drag[0] == "slider":
            x, y = self._xy(e)
            self.slide(self.drag[1], x, y)
            return True
        self.update_cursor(*self._xy(e))
        self.ca.move_motion(self, e)
        return False

    # the skin's own shape and pointers (C3-36) -------------------------
    def shape_key(self):
        return None

    def cursor_name(self, x, y):
        return "normal"

    def update_cursor(self, x, y):
        name = self.cursor_name(x, y) if self.ca.skin.cursors else None
        if name == getattr(self, "_cursor_name", None):
            return
        self._cursor_name = name
        gw = self.area.get_window()
        if gw is not None:
            gw.set_cursor(self.ca.cursor(name) if name else None)

    def shape_region(self):
        """The window's outline from the skin's region.txt, as a cairo region (None: a plain rectangle)."""
        polys = self.ca.skin.regions.get(self.shape_key() or "")
        if not polys:
            return None
        s = self.ca.scale
        w, h = self.size()
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * s, h * s)
        cr = cairo.Context(surf)
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        cr.scale(s, s)
        for poly in polys:
            cr.move_to(*poly[0])
            for p in poly[1:]:
                cr.line_to(*p)
            cr.close_path()
        cr.set_source_rgba(1, 1, 1, 1)
        cr.fill()
        return Gdk.cairo_region_create_from_surface(surf)

    def apply_shape(self):
        self.shape = self.shape_region()
        if self.ca.stack is None:
            self.shape_combine_region(self.shape)

    def _release(self, w, e):
        x, y = self._xy(e)
        was, self.pressed = self.pressed, None
        if self.drag and self.drag[0] == "slider":
            self.slide_done(self.drag[1], x, y)
            self.drag = None
            self.area.queue_draw()
            return True
        self.ca.end_move(self)
        if was and self.hit(x, y) == was:
            self.click(was)
        self.area.queue_draw()
        return True

    def _scroll(self, w, e):
        d = {Gdk.ScrollDirection.UP: 1, Gdk.ScrollDirection.DOWN: -1}.get(e.direction, 0)
        if e.direction == Gdk.ScrollDirection.SMOOTH:
            ok, dx, dy = e.get_scroll_deltas()
            d = -1 if dy > 0 else (1 if dy < 0 else 0)
        if d:
            self.scrolled(d, *self._xy(e))
        return True

    def is_slider(self, name):
        return False

    def slide(self, name, x, y):
        pass

    def slide_done(self, name, x, y):
        pass

    def click(self, name):
        pass

    def double(self, x, y):
        pass

    def drag_anywhere(self, x, y):
        return False

    def scrolled(self, d, x, y):
        pb = self.ca.pb
        pb.set_volume(max(0.0, min(1.0, pb.engine.volume + d * 0.04)))

    # shared pieces ----------------------------------------------------
    def btn_state(self, name):
        return self.pressed == name


# ======================================================================== the player window
class MainWindow(SkinWindow):
    name = "main"

    def __init__(self, ca):
        self.marquee = 0
        self.marquee_text = ""
        self.peaks = [0.0] * 19
        self.bars = [0.0] * 19
        self.osc_phase = 0.0
        self.show_left = False
        self.seek_to = None
        super().__init__(ca, "Chordamp")

    def size(self):
        return (W, 14) if self.ca.settings.get("classic_shade") else (W, H)

    def title_hit(self, x, y):
        return y < 14 and not (x >= 244 or x < 16)

    def shape_key(self):
        return "windowshade" if self.ca.settings.get("classic_shade") else "normal"

    def cursor_name(self, x, y):
        shade = self.ca.settings.get("classic_shade")
        name = self.hit(x, y)
        ws = "ws" if shade else ""
        if name == "close":
            return ws + "close"
        if name == "min":
            return ws + "min"
        if name == "menu":
            return "mainmenu"
        if name == "shade":
            return ws + "winbut"
        if name == "pos":
            return "posbar"
        if name in ("volume", "balance"):
            return "volbal"
        if shade:
            return "wsnormal"
        if 111 <= x < 265 and 24 <= y < 36:
            return "songname"
        if y < 14:
            return "titlebar"
        return "normal"

    def drag_anywhere(self, x, y):
        return not self.ca.settings.get("classic_shade") and y < 116

    def regions(self):
        r = [("menu", 6, 3, 9, 9), ("min", 244, 3, 9, 9), ("shade", 254, 3, 9, 9), ("close", 264, 3, 9, 9)]
        if self.ca.settings.get("classic_shade"):
            return r + [("prev", 169, 2, 7, 10), ("play", 177, 2, 9, 10), ("pause", 187, 2, 9, 10),
                        ("stop", 196, 2, 9, 10), ("next", 205, 2, 9, 10), ("eject", 215, 2, 9, 10)]
        return r + [
            ("prev", 16, 88, 23, 18), ("play", 39, 88, 23, 18), ("pause", 62, 88, 23, 18), ("stop", 85, 88, 23, 18),
            ("next", 108, 88, 22, 18), ("eject", 136, 89, 22, 16), ("shuffle", 164, 89, 47, 15),
            ("repeat", 210, 89, 28, 15), ("eqbtn", 219, 58, 23, 12), ("plbtn", 242, 58, 23, 12),
            ("pos", 16, 72, 248, 10), ("volume", 107, 57, 68, 13), ("balance", 177, 57, 38, 13),
            ("time", 36, 26, 63, 13), ("vis", 24, 43, 76, 16), ("about", 253, 91, 13, 15),
        ]

    def is_slider(self, name):
        return name in ("pos", "volume", "balance")

    def slide(self, name, x, y):
        pb = self.ca.pb
        if name == "volume":
            pb.set_volume(max(0.0, min(1.0, (x - 107 - 7) / 54.0)))
        elif name == "balance":
            b = max(-1.0, min(1.0, (x - 177 - 7 - 12) / 12.0))
            if abs(b) < 0.15:
                b = 0.0
            self.ca.set_balance(b)
        elif name == "pos":
            dur = pb.engine.duration()
            if dur > 0:
                self.seek_to = max(0.0, min(1.0, (x - 16 - 14) / 219.0)) * dur
        self.area.queue_draw()

    def slide_done(self, name, x, y):
        if name == "pos" and self.seek_to is not None:
            self.ca.pb.engine.seek(self.seek_to)
            self.seek_to = None

    def click(self, name):
        ca = self.ca
        if name == "menu":
            ca.options_menu(None, self)
        elif name == "min":
            for w in ([ca.stack] if ca.stack else ca.windows()):
                w.iconify()
        elif name == "shade":
            ca.toggle_shade()
        elif name == "close":
            ca.win.run("quit")
        elif name == "eject":
            ca.play_file()
        elif name == "shuffle":
            ca.pb.set_shuffle(not ca.pb.queue.shuffle)
        elif name == "repeat":
            ca.pb.set_repeat("off" if ca.pb.queue.repeat != "off" else "all")
        elif name == "eqbtn":
            ca.toggle_window("eq")
        elif name == "plbtn":
            ca.toggle_window("pl")
        elif name == "time":
            self.show_left = not self.show_left
        elif name == "vis":
            order = ["spectrum", "oscilloscope", "off"]
            cur = ca.settings.get("classic_vis", "spectrum")
            ca.set_vis(order[(order.index(cur) + 1) % 3 if cur in order else 0])
        elif name == "about":
            ca.win.run("about")
        else:
            ca.transport(name)

    def double(self, x, y):
        if y < 14:
            self.ca.toggle_shade()

    # drawing ----------------------------------------------------------
    def paint(self, cr):
        ca, sk, pb = self.ca, self.ca.skin, self.ca.pb
        foc = self.focused()
        if ca.settings.get("classic_shade"):
            if not sk.blit(cr, "titlebar", 27, 29 if foc else 42, W, 14, 0, 0):
                cr.set_source_rgb(0.2, 0.2, 0.24)
                cr.paint()
            self._title_buttons(cr, shade=True)
            pos, dur = pb.engine.position(), pb.engine.duration()
            if pb.engine.state != "stopped":
                t = views.fmt_time(pos)
                cr.save()
                plain_text(cr, t, 127, 1.5, sk.lcd if sk.text_font is None else sk.pl["normal"], 8)
                cr.restore()
                if dur > 0:
                    cr.set_source_rgb(*sk.pl["normal"])
                    cr.rectangle(226, 5, max(1, 17 * pos / dur), 3)
                    cr.fill()
            return
        if not sk.blit(cr, "main", 0, 0, W, H, 0, 0):
            cr.set_source_rgb(0.15, 0.15, 0.18)
            cr.paint()
        sk.blit(cr, "titlebar", 27, 0 if foc else 15, W, 14, 0, 0)
        self._title_buttons(cr)
        st = pb.engine.state
        # play state
        if st == "playing":
            sk.blit(cr, "playpaus", 0, 0, 9, 9, 26, 28)
        elif st == "paused":
            sk.blit(cr, "playpaus", 9, 0, 9, 9, 26, 28)
        else:
            sk.blit(cr, "playpaus", 18, 0, 9, 9, 26, 28)
        # time
        pos, dur = pb.engine.position(), pb.engine.duration()
        if self.seek_to is not None:
            pos = self.seek_to
        if st != "stopped" and not (st == "paused" and int(time.time() * 2) % 2):
            t = max(0, (dur - pos) if (self.show_left and dur > 0) else pos)
            m, s = int(t // 60) % 100, int(t % 60)
            for x, d in ((48, m // 10), (60, m % 10), (78, s // 10), (90, s % 10)):
                sk.blit(cr, "numbers", d * 9, 0, 9, 13, x, 26)
            if self.show_left and dur > 0:
                cr.set_source_rgb(*(sk.lcd if sk.text_font is None else sk.pl["normal"]))
                cr.rectangle(38, 32, 6, 1)
                cr.fill()
        # visualizer
        self._vis(cr)
        # song title, kbps, kHz
        self._title_text(cr)
        info = ca.stream_info()
        self._small(cr, info[0], 111, 43, 15)
        self._small(cr, info[1], 156, 43, 10)
        if info[2] == 1:
            sk.blit(cr, "monoster", 29, 0, 27, 12, 212, 41)
            sk.blit(cr, "monoster", 0, 12, 29, 12, 239, 41)
        elif info[2] >= 2:
            sk.blit(cr, "monoster", 29, 12, 27, 12, 212, 41)
            sk.blit(cr, "monoster", 0, 0, 29, 12, 239, 41)
        else:
            sk.blit(cr, "monoster", 29, 12, 27, 12, 212, 41)
            sk.blit(cr, "monoster", 0, 12, 29, 12, 239, 41)
        # volume and balance
        v = pb.engine.volume
        i = int(round(v * 27))
        sk.blit(cr, "volume", 0, i * 15, 68, 13, 107, 57)
        sk.blit(cr, "volume", 0 if self.pressed == "volume" else 15, 422, 14, 11, 107 + int(round(v * 54)), 58)
        b = pb.engine.balance
        i = int(round(abs(b) * 27))
        sk.blit(cr, "balance", 9, i * 15, 38, 13, 177, 57)
        sk.blit(cr, "balance", 0 if self.pressed == "balance" else 15, 422, 14, 11, 177 + 12 + int(round(b * 12)), 58)
        # EQ / PL toggles
        for name, sx, x in (("eqbtn", 0, 219), ("plbtn", 23, 242)):
            on = ca.settings.get("classic_eq" if name == "eqbtn" else "classic_pl")
            pressed = self.pressed == name
            sk.blit(cr, "shufrep", sx + (46 if pressed else 0), 73 if on else 61, 23, 12, x, 58)
        # position bar
        if dur > 0 and st != "stopped":
            sk.blit(cr, "posbar", 0, 0, 248, 10, 16, 72)
            sk.blit(cr, "posbar", 278 if self.pressed == "pos" else 248, 0, 29, 10, 16 + int(219 * min(1.0, pos / dur)), 72)
        # transport
        for name, sx, x, w in (("prev", 0, 16, 23), ("play", 23, 39, 23), ("pause", 46, 62, 23), ("stop", 69, 85, 23),
                               ("next", 92, 108, 22)):
            sk.blit(cr, "cbuttons", sx, 18 if self.pressed == name else 0, w, 18, x, 88)
        sk.blit(cr, "cbuttons", 114, 16 if self.pressed == "eject" else 0, 22, 16, 136, 89)
        sh, rp = pb.queue.shuffle, pb.queue.repeat != "off"
        sk.blit(cr, "shufrep", 28, (30 if sh else 0) + (15 if self.pressed == "shuffle" else 0), 47, 15, 164, 89)
        sk.blit(cr, "shufrep", 0, (30 if rp else 0) + (15 if self.pressed == "repeat" else 0), 28, 15, 210, 89)

    def _title_buttons(self, cr, shade=False):
        sk = self.ca.skin
        sk.blit(cr, "titlebar", 0, 9 if self.pressed == "menu" else 0, 9, 9, 6, 3)
        sk.blit(cr, "titlebar", 9, 9 if self.pressed == "min" else 0, 9, 9, 244, 3)
        if shade:
            sk.blit(cr, "titlebar", 0, 27 if self.pressed == "shade" else 18, 9, 9, 254, 3)
        else:
            sk.blit(cr, "titlebar", 0 if self.pressed != "shade" else 9, 18, 9, 9, 254, 3)
        sk.blit(cr, "titlebar", 18, 9 if self.pressed == "close" else 0, 9, 9, 264, 3)

    def _small(self, cr, s, x, y, w):
        sk = self.ca.skin
        if not s:
            return
        if sk.text_font:
            bitmap_text(sk, cr, s, x, y, w)
        else:
            cr.save()
            cr.rectangle(x - 1, y - 3, w + 6, 12)
            cr.clip()
            plain_text(cr, s, x - 1, y - 3, sk.lcd, 8)
            cr.restore()

    def _title_text(self, cr):
        sk = self.ca.skin
        text = self.ca.title_text()
        if text != self.marquee_text:
            self.marquee_text, self.marquee = text, 0
        if not text:
            return
        cr.save()
        cr.rectangle(111, 24 if not sk.text_font else 27, 154, 6 if sk.text_font else 12)
        cr.clip()
        if sk.text_font:
            full = text + "  ***  "
            tw = len(full) * 5
            if len(text) * 5 <= 154:
                bitmap_text(sk, cr, text, 111, 27)
            else:
                off = self.marquee % tw
                bitmap_text(sk, cr, full + full, 111 - off, 27)
        else:
            tw0 = text_width(cr, text, 8.5)
            if tw0 <= 152:
                plain_text(cr, text, 112, 24, sk.lcd, 8.5)
            else:
                full = text + "   ***   "
                tw = text_width(cr, full, 8.5)
                off = self.marquee % max(1, tw)
                plain_text(cr, full + full, 112 - off, 24, sk.lcd, 8.5)
        cr.restore()

    def tick(self):
        if self.ca.skin.text_font:
            self.marquee += 5
        else:
            self.marquee += 2
        self.osc_phase += 0.9
        for i in range(19):
            self.bars[i] = max(0.0, self.bars[i] - 1.2)
            if self.bars[i] > self.peaks[i]:
                self.peaks[i] = self.bars[i]
            else:
                self.peaks[i] = max(0.0, self.peaks[i] - 0.35)

    def feed(self, mags):
        """The spectrum ([dB] over 0..half the sample rate) into 19 bars, spaced as the ear hears."""
        n = len(mags)
        if not n:
            return
        rate = (self.ca.stream_info()[3] or 44100) / 2.0
        edges = [40 * (16000 / 40.0) ** (i / 19.0) for i in range(20)]
        for i in range(19):
            a = int(edges[i] / rate * n)
            b = max(a + 1, int(edges[i + 1] / rate * n))
            v = max(mags[a:b] or [-70])
            h = max(0.0, min(16.0, (v + 70) / 52.0 * 16))
            if h > self.bars[i]:
                self.bars[i] = h
        self._mags = mags

    def _vis(self, cr):
        sk = self.ca.skin
        mode = self.ca.settings.get("classic_vis", "spectrum")
        cr.save()
        cr.rectangle(24, 43, 76, 16)
        cr.clip()
        cr.set_source_rgb(*sk.vis[0])
        cr.paint()
        cr.set_source_rgb(*sk.vis[1])
        for y in range(43, 59, 2):
            for x in range(24, 100, 2):
                cr.rectangle(x, y + 1, 1, 1)
        cr.fill()
        playing = self.ca.pb.engine.state == "playing"
        if mode == "spectrum" and playing:
            for i in range(19):
                h = int(self.bars[i])
                x = 24 + i * 4
                for yy in range(h):
                    row = 15 - yy
                    cr.set_source_rgb(*sk.vis[2 + min(15, row)])
                    cr.rectangle(x, 43 + row, 3, 1)
                    cr.fill()
                p = int(self.peaks[i])
                if p > 0:
                    cr.set_source_rgb(*sk.vis[23])
                    cr.rectangle(x, 43 + 15 - p, 3, 1)
                    cr.fill()
        elif mode == "oscilloscope" and playing:
            wave = self.ca.pb.engine.scope
            if wave:
                # the real waveform (C3-35): 76 columns from the last stretch of sound, mono
                n = len(wave)
                step = max(1, n // 152)
                start = max(0, n - 76 * step)
                prev = None
                for x in range(76):
                    v = wave[min(n - 1, start + x * step)] / 32768.0
                    y = int(max(0, min(15, round(7.5 - v * 7.5 * 1.6))))
                    col = sk.vis[18 + min(4, abs(y - 8) // 2)]
                    cr.set_source_rgb(*col)
                    if prev is not None and abs(prev - y) > 1:
                        lo, hi = sorted((prev, y))
                        cr.rectangle(24 + x, 43 + lo, 1, hi - lo + 1)
                    else:
                        cr.rectangle(24 + x, 43 + y, 1, 1)
                    cr.fill()
                    prev = y
        cr.restore()


# ======================================================================== the equalizer window
class EqWindow(SkinWindow):
    name = "eq"

    def __init__(self, ca):
        super().__init__(ca, "Chordamp Equalizer")

    def shape_key(self):
        return "equalizer"

    def cursor_name(self, x, y):
        name = self.hit(x, y)
        if name == "close":
            return "eqclose"
        if name and self.is_slider(name):
            return "eqslid"
        if y < 14:
            return "eqtitle"
        return "eqnormal"

    def drag_anywhere(self, x, y):
        return True

    def regions(self):
        r = [("close", 264, 3, 9, 9), ("on", 14, 18, 26, 12), ("auto", 40, 18, 32, 12), ("presets", 217, 18, 44, 12),
             ("preamp", 21, 38, 14, 63)]
        for i in range(10):
            r.append(("band%d" % i, 78 + i * 18, 38, 14, 63))
        return r

    def is_slider(self, name):
        return name == "preamp" or name.startswith("band")

    def slide(self, name, x, y):
        s = self.ca.settings
        v = max(-12.0, min(12.0, (38 + 25 - y) / 25.0 * 12.0))
        if abs(v) < 0.6:
            v = 0.0
        if name == "preamp":
            s["eq_preamp"] = round(v, 1)
        else:
            bands = list(s["eq_bands"])
            bands[int(name[4:])] = round(v, 1)
            s["eq_bands"] = bands
        s["eq_preset"] = "Manual"
        self.ca.apply_eq(save=False)
        self.area.queue_draw()

    def slide_done(self, name, x, y):
        self.ca.apply_eq()

    def click(self, name):
        ca, s = self.ca, self.ca.settings
        if name == "close":
            ca.toggle_window("eq")
        elif name == "on":
            s["eq_on"] = not s["eq_on"]
            ca.apply_eq()
        elif name == "auto":
            s["eq_auto"] = not s.get("eq_auto", True)
            ca.pb.engine.auto_eq = s["eq_auto"]
            ca.apply_eq()
        elif name == "presets":
            ca.presets_menu(self)
        self.area.queue_draw()

    def double(self, x, y):
        name = self.hit(x, y)
        if name and self.is_slider(name):
            self.slide(name, x, 38 + 25)
            self.ca.apply_eq()

    def paint(self, cr):
        sk, s = self.ca.skin, self.ca.settings
        if not sk.blit(cr, "eqmain", 0, 0, W, H, 0, 0):
            cr.set_source_rgb(0.15, 0.15, 0.18)
            cr.paint()
        sk.blit(cr, "eqmain", 0, 134 if self.focused() else 149, W, 14, 0, 0)
        sk.blit(cr, "titlebar", 18, 9 if self.pressed == "close" else 0, 9, 9, 264, 3)
        on, auto = s["eq_on"], s.get("eq_auto", True)
        sk.blit(cr, "eqmain", (69 if on else 10) + (118 if self.pressed == "on" else 0), 119, 26, 12, 14, 18)
        sk.blit(cr, "eqmain", (95 if auto else 36) + (118 if self.pressed == "auto" else 0), 119, 32, 12, 40, 18)
        sk.blit(cr, "eqmain", 224, 176 if self.pressed == "presets" else 164, 44, 12, 217, 18)
        vals = [s["eq_preamp"]] + list(s["eq_bands"])
        for i, v in enumerate(vals):
            x = 21 if i == 0 else 78 + (i - 1) * 18
            n = int(round((v + 12) / 24.0 * 27))
            n = max(0, min(27, n))
            sk.blit(cr, "eqmain", 13 + (n % 14) * 15, 164 + (n // 14) * 65, 14, 63, x, 38)
            ty = 38 + int(round((12 - v) / 24.0 * 51))
            name = "preamp" if i == 0 else "band%d" % (i - 1)
            sk.blit(cr, "eqmain", 0, 176 if self.pressed == name else 164, 11, 11, x + 1, ty)
        # the curve
        sk.blit(cr, "eqmain", 0, 294, 113, 19, 86, 17)
        bands = list(s["eq_bands"])
        pts = [(86 + 2 + i * 12, 17 + 9 - b / 12.0 * 8) for i, b in enumerate(bands)]
        cr.save()
        cr.rectangle(86, 17, 113, 19)
        cr.clip()
        cr.set_antialias(cairo.ANTIALIAS_DEFAULT)
        cr.set_line_width(1)
        cr.move_to(*pts[0])
        for i in range(1, len(pts)):
            (x0, y0), (x1, y1) = pts[i - 1], pts[i]
            cr.curve_to(x0 + 6, y0, x1 - 6, y1, x1, y1)
        cr.set_source_rgb(*self.ca.skin.vis[4] if not on else self.ca.skin.vis[2])
        cr.stroke()
        cr.restore()


# ======================================================================== the playlist editor
class PlaylistWindow(SkinWindow):
    name = "pl"
    ROW = 14

    def __init__(self, ca):
        self.top = 0
        self.sel = set()
        self.anchor = None
        self.focus_row = 0
        self.rows_cache = []
        self.drag_rows = None
        self.sel_next = set()       # selected Up Next entries (indexes into the queue's up_next)
        super().__init__(ca, "Chordamp Playlist")

    def size(self):
        return (W, int(self.ca.settings.get("classic_pl_h", 232)))

    def visible_rows(self):
        return max(1, (self.size()[1] - 20 - 38 - 4) // self.ROW)

    def items(self):
        return list(self.ca.pb.queue.source)

    def rows(self):
        """What the editor shows, in play order (C3-38): the list, with Up Next right after the song
        playing (or at the top when nothing from the list is playing). ("src", i, key) | ("next", j, key)."""
        q = self.ca.pb.queue
        src, nxt = list(q.source), list(q.up_next)
        cur = q.current_index() if self.ca.pb.now and self.ca.pb.now.get("kind") != "station" else None
        out = []
        if cur is None:
            out += [("next", j, k) for j, k in enumerate(nxt)]
        for i, k in enumerate(src):
            out.append(("src", i, k))
            if i == cur:
                out += [("next", j, k2) for j, k2 in enumerate(nxt)]
        return out

    def display_index(self, i):
        for d, r in enumerate(self.rows()):
            if r[0] == "src" and r[1] == i:
                return d
        return i

    def title_hit(self, x, y):
        return y < 20

    def regions(self):
        w, h = self.size()
        return [("close", w - 11, 3, 9, 9), ("add", 14, h - 30, 22, 18), ("rem", 43, h - 30, 22, 18),
                ("sel", 72, h - 30, 22, 18), ("misc", 101, h - 30, 22, 18), ("list", w - 44, h - 30, 22, 18),
                ("grip", w - 20, h - 20, 20, 20), ("scroll", w - 15, 20, 8, h - 58), ("rows", 12, 20, w - 32, h - 58)]

    def is_slider(self, name):
        return name in ("grip", "scroll")

    def cursor_name(self, x, y):
        name = self.hit(x, y)
        return {"close": "pclose", "grip": "psize", "scroll": "pvscroll", "add": "pwinbut", "rem": "pwinbut",
                "sel": "pwinbut", "misc": "pwinbut", "list": "pwinbut"}.get(name, "ptbar" if y < 20 else "pnormal")

    def slide(self, name, x, y):
        if name == "grip":
            h = max(116, min(900, int(round((y + 10) / 29.0)) * 29))
            if h != self.size()[1]:
                self.ca.settings["classic_pl_h"] = h
                self.resize_to()
        elif name == "scroll":
            n = len(self.rows())
            span = self.size()[1] - 58 - 18
            f = max(0.0, min(1.0, (y - 20 - 9) / max(1, span)))
            self.top = int(round(f * max(0, n - self.visible_rows())))
        self.area.queue_draw()

    def slide_done(self, name, x, y):
        self.ca.settings.save()

    def _press(self, w, e):
        x, y = self._xy(e)
        self.ca.active_part = self
        if e.button == 1 and self.hit(x, y) == "rows":
            self.area.grab_focus()
            rows = self.rows()
            d = self.top + int((y - 22) // self.ROW)
            ctrl = e.state & Gdk.ModifierType.CONTROL_MASK
            if 0 <= d < len(rows) and rows[d][0] == "next":
                j = rows[d][1]
                if e.type == Gdk.EventType._2BUTTON_PRESS:
                    self.ca.play_up_next(j)
                    return True
                if ctrl:
                    self.sel_next ^= {j}
                else:
                    self.sel, self.sel_next = set(), {j}
                self.area.queue_draw()
                return True
            i = rows[d][1] if 0 <= d < len(rows) else -1
            n = len(self.items())
            if e.type == Gdk.EventType._2BUTTON_PRESS:
                if 0 <= i < n:
                    self.ca.play_index(i)
                return True
            if not ctrl:
                self.sel_next = set()
            if 0 <= i < n:
                if e.state & Gdk.ModifierType.SHIFT_MASK and self.anchor is not None:
                    a, b = sorted((self.anchor, i))
                    self.sel = set(range(a, b + 1))
                elif ctrl:
                    self.sel ^= {i}
                    self.anchor = i
                else:
                    if i not in self.sel:
                        self.sel = {i}
                    self.anchor = i
                    self.drag_rows = (i, i)
                self.focus_row = i
            else:
                self.sel = set()
            self.area.queue_draw()
            return True
        if e.button == 3 and self.hit(x, y) == "rows":
            self.row_menu(e)
            return True
        return super()._press(w, e)

    def _motion(self, w, e):
        if self.drag_rows is not None:
            x, y = self._xy(e)
            rows = self.rows()
            dd = max(0, min(len(rows) - 1, self.top + int((y - 22) // self.ROW)))
            if not rows or rows[dd][0] != "src":
                return True
            i = rows[dd][1]
            start, last = self.drag_rows
            d = i - last
            if d and self.sel:
                if self.ca.move_rows(sorted(self.sel), d, self):
                    self.drag_rows = (start, last + d)
            return True
        return super()._motion(w, e)

    def _release(self, w, e):
        if self.drag_rows is not None:
            self.drag_rows = None
            return True
        return super()._release(w, e)

    def scrolled(self, d, x, y):
        n = len(self.rows())
        self.top = max(0, min(max(0, n - self.visible_rows()), self.top - d * 3))
        self.area.queue_draw()

    def click(self, name):
        ca = self.ca
        if name == "close":
            ca.toggle_window("pl")
        elif name in ("add", "rem", "sel", "misc", "list"):
            ca.pl_menu(name, self)

    def show_row(self, i):
        i = self.display_index(i)
        vr = self.visible_rows()
        if i < self.top:
            self.top = i
        elif i >= self.top + vr:
            self.top = i - vr + 1

    def paint(self, cr):
        sk, ca = self.ca.skin, self.ca
        w, h = self.size()
        foc = 0 if self.focused() else 21
        # frame
        sk.blit(cr, "pledit", 0, foc, 25, 20, 0, 0)
        x = 25
        while x < w - 25:
            sk.blit(cr, "pledit", 127, foc, 25, 20, x, 0)
            x += 25
        sk.blit(cr, "pledit", 26, foc, 100, 20, (w - 100) // 2, 0)
        sk.blit(cr, "pledit", 153, foc, 25, 20, w - 25, 0)
        y = 20
        while y < h - 38:
            sk.blit(cr, "pledit", 0, 42, 12, 29, 0, y)
            sk.blit(cr, "pledit", 31, 42, 20, 29, w - 20, y)
            y += 29
        sk.blit(cr, "pledit", 0, 72, 125, 38, 0, h - 38)
        x = 125
        while x < w - 150:
            sk.blit(cr, "pledit", 179, 0, 25, 38, x, h - 38)
            x += 25
        sk.blit(cr, "pledit", 126, 72, 150, 38, w - 150, h - 38)
        if self.pressed == "close":
            sk.blit(cr, "pledit", 52, 42, 9, 9, w - 11, 3)
        # the list
        cr.save()
        cr.rectangle(12, 20, w - 32, h - 58)
        cr.clip()
        cr.set_source_rgb(*sk.pl["normalbg"])
        cr.paint()
        items = self.items()
        rows = self.rows()
        cur = ca.pb.queue.current_index() if ca.pb.now and ca.pb.now.get("kind") != "station" else None
        font = sk.pl.get("font") or "Sans"
        self.top = max(0, min(self.top, max(0, len(rows) - self.visible_rows())))
        for r in range(self.visible_rows()):
            d = self.top + r
            if d >= len(rows):
                break
            kind, i, key = rows[d]
            yy = 22 + r * self.ROW
            selected = (i in self.sel) if kind == "src" else (i in self.sel_next)
            if selected:
                cr.set_source_rgb(*sk.pl["selectedbg"])
                cr.rectangle(12, yy, w - 32, self.ROW)
                cr.fill()
            if kind == "src":
                col = sk.pl["current"] if i == cur else sk.pl["normal"]
                name = "%d. %s" % (i + 1, item_name(ca, key))
            else:
                col = sk.pl["normal"]
                name = "\u00bb Up Next: %s" % item_name(ca, key)
            length = views.fmt_time(item_length(ca, key))
            lw = text_width(cr, length, 9, font=font)
            cr.save()
            cr.rectangle(12, yy, w - 32 - lw - 8, self.ROW)
            cr.clip()
            plain_text(cr, name, 14 if kind == "src" else 20, yy, col, 9, font=font)
            cr.restore()
            plain_text(cr, length, w - 22 - lw, yy, col, 9, font=font)
        if not items and ca.pb.now and ca.pb.now.get("kind") == "station":
            plain_text(cr, "1. " + (ca.pb.now.get("title") or ""), 14, 22, sk.pl["current"], 9, font=font)
        cr.restore()
        # scroll thumb
        n = len(items)
        nr = len(rows)
        span = h - 58 - 18
        f = 0 if nr <= self.visible_rows() else self.top / max(1, nr - self.visible_rows())
        sk.blit(cr, "pledit", 61 if self.pressed == "scroll" else 52, 53, 8, 18, w - 15, 20 + int(f * span))
        # totals in the bottom bar
        total = sum(item_length(ca, r[2]) for r in rows[:2000])
        sel_total = sum(item_length(ca, items[i]) for i in self.sel if i < n)
        info = "%s/%s" % (views.fmt_time(sel_total), views.fmt_time(total))
        cr.save()
        cr.rectangle(w - 143, h - 29, 90, 12)
        cr.clip()
        plain_text(cr, info, w - 141, h - 29.5, sk.pl["normal"], 8.5, font=font)
        cr.restore()
        self.rows_cache = items


# ======================================================================== the media library
class LibraryWindow(Gtk.Window):
    def __init__(self, ca):
        super().__init__(title="Chordamp Library")
        self.ca = ca
        self.set_application(ca.app)
        self.get_style_context().add_class("chord-dialog")
        self.set_default_size(560, 380)
        self.set_icon_name("folio-chord")
        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        hb.set_title("Library")
        self.set_titlebar(hb)
        self.connect("delete-event", lambda *_: (self.hide(), ca.settings.set("classic_lib", False), True)[2])
        self.connect("key-press-event", self._key)
        paned = Gtk.Paned()
        self.add(paned)
        self.src = Gtk.ListStore(str, str)        # name, key
        sv = Gtk.TreeView(model=self.src)
        sv.set_headers_visible(False)
        sv.append_column(Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=0))
        sv.get_selection().connect("changed", lambda *_: self.fill())
        self.srcview = sv
        sw = Gtk.ScrolledWindow()
        sw.add(sv)
        sw.set_size_request(150, -1)
        paned.pack1(sw, False, False)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        right.set_border_width(4)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Search")
        self.search.connect("search-changed", lambda *_: self.fill())
        right.pack_start(self.search, False, False, 0)
        self.store = Gtk.ListStore(str, str, str, str, object)    # title, artist, album, time, key
        lv = Gtk.TreeView(model=self.store)
        for i, (t, wd) in enumerate((("Title", 200), ("Artist", 130), ("Album", 130), ("Time", 50))):
            c = Gtk.TreeViewColumn(t, Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END), text=i)
            c.set_resizable(True)
            c.set_fixed_width(wd)
            c.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            lv.append_column(c)
        lv.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        lv.connect("row-activated", lambda *_: self.play())
        self.list = lv
        sw2 = Gtk.ScrolledWindow()
        sw2.add(lv)
        right.pack_start(sw2, True, True, 0)
        bb = Gtk.Box(spacing=6)
        for label, fn in (("Play", self.play), ("Enqueue", self.enqueue)):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda *_, f=fn: f())
            bb.pack_start(b, False, False, 0)
        self.count = Gtk.Label(xalign=1)
        bb.pack_end(self.count, False, False, 0)
        right.pack_start(bb, False, False, 0)
        paned.pack2(right, True, False)
        self.fill_sources()

    def _key(self, w, e):
        if e.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False

    def fill_sources(self):
        self.src.clear()
        self.src.append(["Music", "music"])
        self.src.append(["Podcasts", "podcasts"])
        self.src.append(["Radio", "radio"])
        for p in self.ca.lib.playlists():
            if p["kind"] != "folder":
                self.src.append([p["name"], "pl:%d" % p["id"]])
        self.srcview.get_selection().select_path(Gtk.TreePath.new_first())

    def source(self):
        m, it = self.srcview.get_selection().get_selected()
        return m[it][1] if it else "music"

    def fill(self):
        self.store.clear()
        key = self.source()
        q = self.search.get_text().strip().lower()
        rows = []
        if key == "music":
            for r in self.ca.lib.tracks():
                rows.append((r["title"] or "", r["artist"] or "", r["album"] or "", r["duration"] or 0, r["id"]))
        elif key.startswith("pl:"):
            for r in self.ca.lib.playlist_tracks(int(key[3:])):
                rows.append((r["title"] or "", r["artist"] or "", r["album"] or "", r["duration"] or 0, r["id"]))
        elif key == "podcasts":
            pods = self.ca.app.pods
            for p in pods.shows():
                for e in pods.episodes(p["id"]):
                    rows.append((e["title"] or "", p["title"] or "", "", e["duration"] or 0, ("e", e["id"])))
        elif key == "radio":
            from . import radio
            for st in radio.favourites(self.ca.lib):
                rows.append((st["name"], ", ".join(st.get("tags", [])[:3]), st.get("country", ""), 0, ("s", st)))
        for t, a, al, d, k in rows:
            if q and q not in ("%s %s %s" % (t, a, al)).lower():
                continue
            self.store.append([t, a, al, views.fmt_time(d) if d else "", k])
        self.count.set_text("%d items" % len(self.store))

    def keys(self, selected=True):
        m, paths = self.list.get_selection().get_selected_rows()
        if selected and paths:
            return [m[p][4] for p in paths]
        return [r[4] for r in self.store]

    def play(self):
        keys = self.keys()
        if not keys:
            return
        if isinstance(keys[0], tuple) and keys[0][0] == "s":
            return self.ca.pb.play_station(keys[0][1])
        allk = self.keys(selected=False) if len(keys) == 1 else keys
        idx = allk.index(keys[0]) if keys[0] in allk else 0
        allk = [k for k in allk if not (isinstance(k, tuple) and k[0] == "s")]
        self.ca.play_list(allk, idx)

    def enqueue(self):
        keys = [k for k in self.keys() if not (isinstance(k, tuple) and k[0] == "s")]
        self.ca.add_items(keys)


# ======================================================================== Chordamp itself
class Chordamp:
    def __init__(self, win):
        self.win = win
        self.app = win.app
        self.lib = win.lib
        self.pb = win.app.playback
        self.settings = win.settings
        self.scale = 2 if self.settings.get("classic_double") else 1
        self.skin = skinmod.by_name(self.settings.get("skin"))
        self.main = MainWindow(self)
        self.eq = EqWindow(self)
        self.pl = PlaylistWindow(self)
        self.libwin = None
        self.visible = False
        self._move = None
        self.active_part = self.main
        self._cursors = {}
        self.stack = None
        if wayland() or os.environ.get("FOLIO_CHORD_CLASSIC_STACK"):
            self._make_stack()
        self.pb.listen(self._event)
        self._timer = None
        self._info = ("", "", 0, 44100)
        self._info_key = None
        self.apply_ontop()

    # windows ----------------------------------------------------------
    def _make_stack(self):
        """On Wayland a program can't place its own windows, so they couldn't dock: the player, the
        equalizer and the playlist editor then live docked in one window and move as one."""
        st = self.stack = Gtk.Window(title="Chordamp")
        st.set_application(self.app)
        st.get_style_context().add_class("chord-classic")
        st.set_decorated(False)
        st.set_resizable(False)
        st.set_icon_name("folio-chord")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        st.add(box)
        for w in self.all_windows():
            w.remove(w.area)
            w.area.set_no_show_all(True)
            box.pack_start(w.area, False, False, 0)
        st.connect("key-press-event", lambda _w, e: self.key(e))
        st.connect("delete-event", lambda *_: (self.win.run("quit"), True)[1])
        for sig in ("focus-in-event", "focus-out-event"):
            st.connect(sig, lambda *_: [w.area.queue_draw() for w in self.all_windows()] and False)
        box.show()

    def top_window(self):
        return self.stack or self.main

    def cursor(self, name):
        """The skin's pointer by name (falling back to its normal one), at the current size."""
        cur = self.skin.cursors.get(name) or self.skin.cursors.get("normal")
        if not cur:
            return None
        key = (id(self.skin), name, self.scale)
        c = self._cursors.get(key)
        if c is None:
            pb, hx, hy = cur
            if self.scale != 1:
                from gi.repository import GdkPixbuf
                pb = pb.scale_simple(pb.get_width() * self.scale, pb.get_height() * self.scale, GdkPixbuf.InterpType.NEAREST)
            c = Gdk.Cursor.new_from_pixbuf(Gdk.Display.get_default(), pb, hx * self.scale, hy * self.scale)
            self._cursors[key] = c
        return c

    def apply_shapes(self):
        for w in self.all_windows():
            w.apply_shape()
            w._cursor_name = None
            gw = w.area.get_window()
            if gw is not None:
                gw.set_cursor(None)

    def shown(self, w):
        """Is this part (the player, equalizer or playlist editor) on screen?"""
        if self.stack is not None:
            return self.stack.get_visible() and w.area.get_visible()
        return w.get_visible()

    def show_part(self, w):
        if self.stack is not None:
            w.area.show()
        else:
            w.show_all()
            w.present()

    def hide_part(self, w):
        if self.stack is not None:
            w.area.hide()
            self.stack.resize(1, 1)
        else:
            w.hide()

    def pl_active(self):
        if self.stack is not None:
            return self.active_part is self.pl and self.stack.is_active()
        return self.pl.is_active()

    def windows(self):
        out = [self.main]
        if self.settings.get("classic_eq"):
            out.append(self.eq)
        if self.settings.get("classic_pl"):
            out.append(self.pl)
        return out

    def all_windows(self):
        return [self.main, self.eq, self.pl]

    def place(self):
        pos = self.settings.get("classic_pos") or {}
        s = self.scale
        mx, my = pos.get("main", (120, 120))
        defaults = {"main": (mx, my), "eq": (mx, my + H * s), "pl": (mx, my + 2 * H * s)}
        for w in self.all_windows():
            x, y = pos.get(w.name, defaults[w.name])
            w.move(int(x), int(y))

    def save_positions(self):
        if self.stack is not None:
            return
        pos = {}
        for w in self.all_windows():
            pos[w.name] = list(w.get_position())
        self.settings["classic_pos"] = pos
        self.settings.save()

    def show(self):
        self.visible = True
        if self.stack is not None:
            for w in self.all_windows():
                w.area.set_visible(w in self.windows())
            self.stack.show()
            self.stack.present()
        else:
            self.place()
            for w in self.windows():
                w.show_all()
        if self.settings.get("classic_lib"):
            self.show_library()
        self.top_window().present()
        self.pb.engine.set_spectrum(True)
        self.pb.engine.set_scope(self.settings.get("classic_vis") == "oscilloscope")
        self.apply_shapes()
        if self._timer is None:
            self._timer = GLib.timeout_add(50, self._tick)

    def hide(self):
        if self.visible:
            self.save_positions()
        self.visible = False
        for w in self.all_windows():
            w.hide()
        if self.stack is not None:
            self.stack.hide()
        if self.libwin is not None:
            self.libwin.hide()
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        self.pb.engine.set_scope(False)
        vis = getattr(self.win, "vis", None)
        if not (vis and vis.get_visible()):
            self.pb.engine.set_spectrum(False)

    def window_closed(self, w):
        if w is self.main:
            self.win.run("quit")
        else:
            self.toggle_window(w.name)

    def toggle_window(self, name, on=None):
        key = {"eq": "classic_eq", "pl": "classic_pl"}[name]
        w = self.eq if name == "eq" else self.pl
        on = (not self.settings.get(key)) if on is None else on
        self.settings.set(key, bool(on))
        if self.visible:
            if on:
                self.show_part(w)
            else:
                self.hide_part(w)
        self.main.area.queue_draw()
        return on

    def show_library(self, on=True):
        if self.libwin is None:
            self.libwin = LibraryWindow(self)
        self.settings.set("classic_lib", bool(on))
        if on:
            self.libwin.fill_sources()
            self.libwin.show_all()
            self.libwin.present()
        else:
            self.libwin.hide()
        return self.libwin

    def toggle_shade(self):
        sh = not self.settings.get("classic_shade")
        old = self.main.rect()
        self.settings.set("classic_shade", sh)
        self.main.resize_to()
        self.main.apply_shape()
        # windows docked under the player follow its new height
        dh = self.main.size()[1] * self.scale - old[3]
        for w in ((self.eq, self.pl) if self.stack is None else ()):
            x, y, ww, hh = w.rect()
            if y >= old[1] + old[3] - 1:
                w.move(x, y + dh)
        self.main.area.queue_draw()

    def set_double(self, on):
        on = bool(on)
        self.settings.set("classic_double", on)
        old = self.scale
        self.scale = 2 if on else 1
        mx, my = self.main.get_position()
        for w in self.all_windows():
            x, y = w.get_position()
            w.resize_to()
            if self.stack is None:
                w.move(mx + (x - mx) * self.scale // old, my + (y - my) * self.scale // old)
            w.area.queue_draw()
        self.apply_shapes()

    def apply_ontop(self):
        on = bool(self.settings.get("classic_ontop"))
        for w in self.all_windows() + ([self.stack] if self.stack else []):
            w.set_keep_above(on)

    def set_ontop(self, on):
        self.settings.set("classic_ontop", bool(on))
        self.apply_ontop()

    def set_vis(self, mode):
        self.settings.set("classic_vis", mode)
        self.pb.engine.set_scope(self.visible and mode == "oscilloscope")
        self.main.area.queue_draw()

    def set_skin(self, name):
        self.skin = skinmod.by_name(name)
        self.settings.set("skin", name or "")
        self.apply_shapes()
        for w in self.all_windows():
            w.area.queue_draw()

    def set_balance(self, b):
        self.pb.engine.set_balance(b)
        self.settings["balance"] = b
        ew = getattr(self.win, "eq_win", None)
        if ew is not None and hasattr(ew, "balance") and abs(ew.balance.get_value() - b) > 0.01:
            ew.balance.set_value(b)

    def apply_eq(self, save=True):
        s = self.settings
        self.pb.engine.set_eq(s["eq_on"], s["eq_preamp"], s["eq_bands"])
        if save:
            s.save()
        ew = getattr(self.win, "eq_win", None)
        if ew is not None and hasattr(ew, "fill_presets"):
            try:
                ew._quiet = True
                ew.on.set_active(s["eq_on"])
                ew.preamp.set_value(s["eq_preamp"])
                for sc, v in zip(ew.scales, s["eq_bands"]):
                    sc.set_value(v)
            finally:
                ew._quiet = False
        self.eq.area.queue_draw()

    def load_preset(self, name):
        pr = self.app.eq_preset(name)
        if pr:
            s = self.settings
            s["eq_preamp"], s["eq_bands"], s["eq_preset"] = float(pr[0]), list(pr[1]), name
            s["eq_on"] = True
            self.apply_eq()

    # moving: snapping and docking (X11; Wayland moves windows itself) ---
    def begin_move(self, w, e):
        if self.stack is not None:
            self.stack.begin_move_drag(e.button, int(e.x_root), int(e.y_root), e.time)
            return
        if wayland():
            w.begin_move_drag(e.button, int(e.x_root), int(e.y_root), e.time)
            return
        docked = self.docked_to(w) if w is self.main else []
        self._move = (w, e.x_root, e.y_root, w.get_position(), [(d, d.get_position()) for d in docked])

    def move_motion(self, w, e):
        m = self._move
        if not m or m[0] is not w:
            return
        _w, x0, y0, (wx, wy), docked = m
        nx, ny = int(wx + e.x_root - x0), int(wy + e.y_root - y0)
        nx, ny = self.snap(w, nx, ny, [d for d, _p in docked])
        dx, dy = nx - wx, ny - wy
        w.move(nx, ny)
        for d, (px, py) in docked:
            d.move(px + dx, py + dy)

    def end_move(self, w):
        if self._move and self._move[0] is w:
            self._move = None
            self.save_positions()

    @staticmethod
    def touching(a, b):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        h_overlap = ax < bx + bw and bx < ax + aw
        v_overlap = ay < by + bh and by < ay + ah
        return (h_overlap and (abs(ay + ah - by) <= 1 or abs(by + bh - ay) <= 1)) or \
            (v_overlap and (abs(ax + aw - bx) <= 1 or abs(bx + bw - ax) <= 1))

    def docked_to(self, w):
        """The windows joined to w, directly or through one another."""
        shown = [x for x in self.windows() if x.get_visible()]
        found, todo = {w}, [w]
        while todo:
            a = todo.pop()
            for b in shown:
                if b not in found and self.touching(a.rect(), b.rect()):
                    found.add(b)
                    todo.append(b)
        return [x for x in found if x is not w]

    def snap(self, w, x, y, ignore=()):
        _x, _y, ww, hh = w.rect()
        targets = []
        for o in self.windows():
            if o is w or o in ignore or not o.get_visible():
                continue
            ox, oy, ow, oh = o.rect()
            targets.append((ox, oy, ow, oh, True))
        scr = w.get_screen()
        try:
            mon = Gdk.Display.get_default().get_monitor_at_window(w.get_window()).get_workarea()
            targets.append((mon.x, mon.y, mon.width, mon.height, False))
        except Exception:       # noqa: BLE001
            targets.append((0, 0, scr.get_width(), scr.get_height(), False))
        bx, by = x, y
        best_x = best_y = SNAP + 1
        for ox, oy, ow, oh, outside in targets:
            xs = [ox, ox + ow - ww] + ([ox + ow, ox - ww] if outside else [])
            ys = [oy, oy + oh - hh] + ([oy + oh, oy - hh] if outside else [])
            near_v = not outside or (y < oy + oh + SNAP and oy < y + hh + SNAP)
            near_h = not outside or (x < ox + ow + SNAP and ox < x + ww + SNAP)
            if near_v:
                for c in xs:
                    if abs(c - x) < best_x:
                        best_x, bx = abs(c - x), c
            if near_h:
                for c in ys:
                    if abs(c - y) < best_y:
                        best_y, by = abs(c - y), c
        return bx, by

    # what's playing -----------------------------------------------------
    def title_text(self):
        now = self.pb.now
        if not now:
            return "Chordamp"
        if now.get("kind") == "station":
            t = self.pb.stream_title or now.get("title") or ""
            return "%s (%s)" % (t, now.get("title")) if self.pb.stream_title else t
        i = self.pb.queue.current_index()
        name = "%s - %s" % (now.get("artist"), now.get("title")) if now.get("artist") else (now.get("title") or "")
        dur = now.get("duration") or self.pb.engine.duration()
        return "%s%s (%s)" % ("%d. " % (i + 1) if i is not None else "", name, views.fmt_time(dur))

    def stream_info(self):
        """(kbps, kHz, channels, sample rate) for the display."""
        now = self.pb.now
        key = (now or {}).get("kind"), (now or {}).get("id")
        if key == self._info_key:
            return self._info
        info = ("", "", 0, 44100)
        if now and now.get("kind") == "song":
            r = self.lib.track(now["id"])
            if r:
                info = ("%3d" % min(999, r["bitrate"] or 0) if r["bitrate"] else "", "%d" % round((r["sample_rate"] or 0) / 1000.0)
                        if r["sample_rate"] else "", r["channels"] or 2, r["sample_rate"] or 44100)
        elif now and now.get("kind") == "station":
            st = now.get("station") or {}
            info = ("%3d" % st["bitrate"] if st.get("bitrate") else "", "44", 2, 44100)
        elif now:
            info = ("", "44", 2, 44100)
        self._info, self._info_key = info, key
        return info

    def _event(self, ev, val):
        if not self.visible:
            return
        if ev == "spectrum":
            self.main.feed(val)
        elif ev in ("track", "state", "modes", "volume"):
            self._info_key = None
            for w in self.all_windows():
                w.area.queue_draw()
            if ev == "track" and self.shown(self.pl):
                ci = self.pb.queue.current_index()
                if ci is not None:
                    self.pl.show_row(ci)

    def _tick(self):
        self.main.tick()
        self.main.area.queue_draw()
        self._ticks = getattr(self, "_ticks", 0) + 1
        if self._ticks % 10 == 0 and self.shown(self.pl):
            q = self.pb.queue
            sig = (tuple(q.up_next), len(q.source), q.current)
            if sig != getattr(self, "_pl_sig", None):      # Up Next changed from the menus or the library
                self._pl_sig = sig
                self.pl.area.queue_draw()
        return True

    # transport --------------------------------------------------------
    def transport(self, name):
        pb = self.pb
        if name == "prev":
            pb.previous()
        elif name == "play":
            st = pb.engine.state
            if st == "paused":
                pb.engine.resume()
            elif st == "playing":
                pb.engine.seek(0)
            else:
                if self.pb.queue.source or pb.now:
                    pb.toggle()
                elif self.pl.rows_cache:
                    self.play_index(0)
        elif name == "pause":
            if pb.engine.state in ("playing", "paused"):
                pb.engine.toggle()
        elif name == "stop":
            pb.stop()
        elif name == "next":
            pb.next()

    def play_index(self, i):
        q = self.pb.queue
        items = list(q.source)
        if not (0 <= i < len(items)):
            return
        q.start(items, i)
        k = items[i]
        self.pb._start(self.pb._item_for(k))
        self.pl.area.queue_draw()

    def play_up_next(self, j):
        """Play an Up Next entry now (double-click in the playlist editor)."""
        q = self.pb.queue
        if not (0 <= j < len(q.up_next)):
            return
        k = q.up_next.pop(j)
        q.current = k
        q.history.append(k)
        self.pb._start(self.pb._item_for(k))
        self.pl.sel_next = set()
        self.pl.area.queue_draw()

    def play_list(self, keys, index=0):
        keys = list(keys)
        if not keys:
            return
        self.pb.queue.start(keys, index)
        self.pb._start(self.pb._item_for(keys[index]))
        self.pl.area.queue_draw()

    def add_items(self, keys):
        q = self.pb.queue
        if not keys:
            return
        q.set_source(list(q.source) + list(keys), q.current_index())
        self.pl.area.queue_draw()

    def set_items(self, keys, cur_index=None):
        self.pb.queue.set_source(keys, cur_index)
        self.pl.sel = {i for i in self.pl.sel if i < len(keys)}
        self.pl.area.queue_draw()

    def move_rows(self, rows, d, plw=None):
        q = self.pb.queue
        items = list(q.source)
        cur = q.current_index()
        if not rows or rows[0] + d < 0 or rows[-1] + d >= len(items):
            return False
        mark = list(range(len(items)))
        moving = [mark[i] for i in rows]
        rest = [m for m in mark if m not in set(moving)]
        ins = rows[0] + d
        new = rest[:ins] + moving + rest[ins:]
        q.set_source([items[m] for m in new], new.index(cur) if cur is not None else None)
        if plw is not None:
            plw.sel = {new.index(m) for m in moving}
            plw.focus_row = min(plw.sel)
            plw.anchor = plw.focus_row
            plw.show_row(plw.focus_row)
            plw.area.queue_draw()
        return True

    # menus --------------------------------------------------------------
    def _menu(self, entries):
        m = Gtk.Menu()
        m.get_style_context().add_class("chord-menu")
        for e in entries:
            if e is None:
                m.append(Gtk.SeparatorMenuItem())
                continue
            label, what = e[0], e[1]
            check = e[2] if len(e) > 2 else None
            if isinstance(what, list):
                mi = Gtk.MenuItem(label=label)
                mi.set_submenu(self._menu(what))
            elif check is not None:
                mi = Gtk.CheckMenuItem(label=label)
                mi.set_active(bool(check))
                mi.connect("activate", lambda *_, f=what: f())
            else:
                mi = Gtk.MenuItem(label=label)
                mi.connect("activate", lambda *_, f=what: f())
            m.append(mi)
        m.show_all()
        return m

    def _popup(self, m, e=None, w=None):
        self._last_menu = m
        m.attach_to_widget((w or self.main).area, None)
        if e is not None:
            m.popup_at_pointer(e)
        else:
            m.popup_at_widget((w or self.main).area, Gdk.Gravity.NORTH_WEST, Gdk.Gravity.NORTH_WEST, None)

    def options_entries(self):
        s = self.settings
        skins = [("Chordamp", lambda: self.set_skin(""), not s.get("skin"))]
        for f in skinmod.installed():
            skins.append((os.path.splitext(f)[0], lambda f=f: self.set_skin(f), s.get("skin") == f))
        skins += [None, ("Load Skin…", self.load_skin), ("Save Chordamp Skin As…", self.export_skin)]
        vis = s.get("classic_vis", "spectrum")
        return [
            ("Standard Look", lambda: self.win.run("look:standard")),
            None,
            ("Play File…", self.play_file),
            ("Play Stream…", lambda: self.win.run("open-stream")),
            ("Jump to File…", self.jump),
            None,
            ("Equalizer", lambda: self.toggle_window("eq"), s.get("classic_eq")),
            ("Playlist Editor", lambda: self.toggle_window("pl"), s.get("classic_pl")),
            ("Library", lambda: self.show_library(not (self.libwin and self.libwin.get_visible())),
             bool(self.libwin and self.libwin.get_visible())),
            None,
            ("Skins", skins),
            ("Visualization", [("Spectrum", lambda: self.set_vis("spectrum"), vis == "spectrum"),
                               ("Oscilloscope", lambda: self.set_vis("oscilloscope"), vis == "oscilloscope"),
                               ("Off", lambda: self.set_vis("off"), vis == "off")]),
            ("Double Size", lambda: self.set_double(not s.get("classic_double")), s.get("classic_double")),
            ("Always on Top", lambda: self.set_ontop(not s.get("classic_ontop")), s.get("classic_ontop")),
            ("Shade Player", self.toggle_shade, s.get("classic_shade")),
            None,
            ("Playback", [("Previous", lambda: self.transport("prev")), ("Play", lambda: self.transport("play")),
                          ("Pause", lambda: self.transport("pause")), ("Stop", lambda: self.transport("stop")),
                          ("Next", lambda: self.transport("next")), None,
                          ("Back 5 Seconds", lambda: self.seek_by(-5)), ("Forward 5 Seconds", lambda: self.seek_by(5)),
                          None,
                          ("Shuffle", lambda: self.pb.set_shuffle(not self.pb.queue.shuffle), self.pb.queue.shuffle),
                          ("Repeat", lambda: self.pb.set_repeat("off" if self.pb.queue.repeat != "off" else "all"),
                           self.pb.queue.repeat != "off")]),
            ("Options…", lambda: self.win.run("options")),
            ("About Folio Chord", lambda: self.win.run("about")),
            None,
            ("Quit", lambda: self.win.run("quit")),
        ]

    def options_menu(self, e=None, w=None):
        self._popup(self._menu(self.options_entries()), e, w)

    def presets_menu(self, w):
        names = self.app.eq_presets()
        entries = [(n, lambda n=n: self.load_preset(n)) for n in names]
        entries += [None, ("Reset to Flat", lambda: self.load_preset("Flat")),
                    ("Make Preset…", self.make_preset)]
        self._popup(self._menu(entries), None, w)

    def make_preset(self):
        from . import dialogs
        name = dialogs.ask_text(self.top_window(), "Make Preset", "Name of the preset:", "")
        if name:
            c = dict(self.settings.get("eq_custom") or {})
            c[name.strip()] = [self.settings["eq_preamp"], list(self.settings["eq_bands"])]
            self.settings.set("eq_custom", c)
            self.settings.set("eq_preset", name.strip())
        return name

    def pl_entries(self, which):
        pl = self.pl
        if which == "add":
            return [("Add File…", self.add_files), ("Add Folder…", self.add_folder), ("Add Stream…", self.add_stream)]
        if which == "rem":
            return [("Remove Selected", self.remove_selected), ("Crop", self.crop), ("Remove All", self.remove_all),
                    ("Remove Missing Files", self.remove_missing)]
        if which == "sel":
            return [("Select All", lambda: self.select("all")), ("Select None", lambda: self.select("none")),
                    ("Invert Selection", lambda: self.select("invert"))]
        if which == "misc":
            return [("Sort by Title", lambda: self.sort("title")), ("Sort by Artist", lambda: self.sort("artist")),
                    ("Sort by File Name", lambda: self.sort("path")), ("Reverse List", lambda: self.sort("reverse")),
                    ("Randomize List", lambda: self.sort("random")), None,
                    ("Get Info", self.info_selected, None) if pl.sel else ("Get Info", lambda: None)]
        return [("New List", self.remove_all), ("Open List…", self.load_list), ("Save List…", self.save_list)]

    def pl_menu(self, which, w):
        self._popup(self._menu(self.pl_entries(which)), None, w)

    def row_menu(self, e):
        entries = [("Play", lambda: self.play_index(min(self.pl.sel)) if self.pl.sel else None)] + \
            [None] + self.pl_entries("rem")[:2] + [None] + self.pl_entries("misc")[-1:]
        self._popup(self._menu(entries), e, self.pl)

    # playlist commands ----------------------------------------------------
    def add_files(self, files=None):
        from . import dialogs
        files = files if files is not None else dialogs.choose_files(self.top_window(), "Add Files to Playlist", audio=True)
        ids = self.win.add_paths(files) if files else []
        self.add_items(ids)
        return ids

    def add_folder(self, folder=None):
        from . import dialogs
        folder = folder or dialogs.choose_folder(self.top_window(), "Add Folder to Playlist")
        ids = self.win.add_paths([folder]) if folder else []
        self.add_items(ids)
        return ids

    def add_stream(self):
        return self.win.run("open-stream")

    def play_file(self, files=None):
        from . import dialogs
        files = files if files is not None else dialogs.choose_files(self.top_window(), "Play File", audio=True)
        ids = self.win.add_paths(files) if files else []
        if ids:
            self.play_list(ids, 0)
        return ids

    def remove_selected(self):
        q = self.pb.queue
        if self.pl.sel_next:
            q.up_next = [k for j, k in enumerate(q.up_next) if j not in self.pl.sel_next]
            self.pl.sel_next = set()
            if not self.pl.sel:
                self.pl.area.queue_draw()
                return
        items = list(q.source)
        cur = q.current_index()
        keep = [i for i in range(len(items)) if i not in self.pl.sel]
        self.pl.sel = set()
        self.set_items([items[i] for i in keep], keep.index(cur) if cur in keep else None)

    def crop(self):
        q = self.pb.queue
        items = list(q.source)
        cur = q.current_index()
        keep = sorted(i for i in self.pl.sel if i < len(items))
        self.pl.sel = set(range(len(keep)))
        self.set_items([items[i] for i in keep], keep.index(cur) if cur in keep else None)

    def remove_all(self):
        self.pl.sel = set()
        self.set_items([])

    def remove_missing(self):
        q = self.pb.queue
        items = list(q.source)
        cur = q.current_index()
        keep = []
        for i, k in enumerate(items):
            if isinstance(k, (tuple, list)):
                keep.append(i)
                continue
            r = self.lib.track(k)
            if r and r["path"] and os.path.exists(r["path"]):
                keep.append(i)
        self.set_items([items[i] for i in keep], keep.index(cur) if cur in keep else None)

    def select(self, how):
        n = len(self.pb.queue.source)
        if how == "all":
            self.pl.sel = set(range(n))
        elif how == "none":
            self.pl.sel = set()
            self.pl.sel_next = set()
        else:
            self.pl.sel = set(range(n)) - self.pl.sel
        self.pl.area.queue_draw()

    def sort(self, how):
        q = self.pb.queue
        items = list(q.source)
        cur = q.current_index()
        idx = list(range(len(items)))
        if how == "reverse":
            idx.reverse()
        elif how == "random":
            import random
            random.shuffle(idx)
        else:
            def key(i):
                k = items[i]
                if isinstance(k, (tuple, list)):
                    return item_name(self, k).lower()
                r = self.lib.track(k) or {}
                if how == "path":
                    return os.path.basename(r["path"] or "").lower() if r else ""
                if how == "artist":
                    return ((r["artist"] or "").lower(), (r["album"] or "").lower(), r["track_no"] or 0) if r else ("",)
                return (r["title"] or "").lower() if r else ""
            idx.sort(key=key)
        self.set_items([items[i] for i in idx], idx.index(cur) if cur is not None else None)

    def info_selected(self):
        items = list(self.pb.queue.source)
        ids = [items[i] for i in sorted(self.pl.sel) if i < len(items) and not isinstance(items[i], (tuple, list))]
        if not ids:
            return None
        from . import dialogs
        return dialogs.get_info(self.win, ids)

    def save_list(self, path=None):
        from . import dialogs
        path = path or dialogs.save_file(self.top_window(), "Save Playlist", "Playlist.m3u")
        if not path:
            return None
        lines = ["#EXTM3U"]
        for k in self.pb.queue.source:
            if isinstance(k, (tuple, list)):
                e = self.app.pods.episode(k[1])
                if e:
                    lines += ["#EXTINF:%d,%s" % (int(e["duration"] or 0), e["title"]), e["file"] or e["url"]]
                continue
            r = self.lib.track(k)
            if r:
                lines += ["#EXTINF:%d,%s" % (int(r["duration"] or 0), item_name(self, k)), r["path"]]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path

    def load_list(self, path=None):
        from . import dialogs, radio
        if path is None:
            got = dialogs.choose_files(self.top_window(), "Open Playlist", multiple=False,
                                       patterns=[("Playlists", ["*.m3u", "*.m3u8", "*.pls", "*.xspf"])])
            path = got[0] if got else None
        if not path:
            return []
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        base = os.path.dirname(path)
        entries = []
        if "[playlist]" in text.lower() or "<playlist" in text.lower():
            entries = radio.parse_playlist(text) or []
            import re
            if not entries:
                entries = re.findall(r"(?im)^File\d+\s*=\s*(.+)$", text) + re.findall(r"(?i)<location>\s*([^<]+)</location>", text)
        else:
            entries = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
        paths = []
        for e in entries:
            if e.startswith("file://"):
                from urllib.parse import unquote, urlparse
                e = unquote(urlparse(e).path)
            if "://" in e:
                continue
            p = e if os.path.isabs(e) else os.path.join(base, e)
            if os.path.exists(p):
                paths.append(p)
        ids = self.win.add_paths(paths) if paths else []
        self.set_items(ids)
        return ids

    def jump(self):
        """Jump to File (J): type part of a name, pick it, play it."""
        from . import dialogs
        items = list(self.pb.queue.source)
        d = dialogs.Dialog(self.top_window(), "Jump to File", (("Close", Gtk.ResponseType.CANCEL), ("Jump to File", Gtk.ResponseType.OK)))
        d.set_default_size(420, 360)
        entry = Gtk.SearchEntry()
        store = Gtk.ListStore(int, str)
        view = Gtk.TreeView(model=store)
        view.set_headers_visible(False)
        view.append_column(Gtk.TreeViewColumn("", Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END), text=1))
        names = [item_name(self, k) for k in items]

        def refill(*_):
            store.clear()
            q = entry.get_text().strip().lower().split()
            for i, n in enumerate(names):
                if all(w in n.lower() for w in q):
                    store.append([i, "%d. %s" % (i + 1, n)])
            if len(store):
                view.get_selection().select_path(Gtk.TreePath.new_first())
        entry.connect("search-changed", refill)
        entry.connect("activate", lambda *_: d.response(Gtk.ResponseType.OK))
        view.connect("row-activated", lambda *_: d.response(Gtk.ResponseType.OK))
        sw = Gtk.ScrolledWindow()
        sw.add(view)
        sw.set_vexpand(True)
        d.body.pack_start(entry, False, False, 0)
        d.body.pack_start(sw, True, True, 0)
        d.entry, d.store, d.refill = entry, store, refill
        refill()
        r = d.ask()
        pick = None
        if r == Gtk.ResponseType.OK:
            m, it = view.get_selection().get_selected()
            if it is not None:
                pick = m[it][0]
        d.destroy()
        if pick is not None:
            self.play_index(pick)
        return pick

    def load_skin(self, path=None):
        from . import dialogs
        if path is None:
            got = dialogs.choose_files(self.top_window(), "Load Skin", multiple=False, patterns=[("Skins", ["*.wsz", "*.zip"])])
            path = got[0] if got else None
        if not path:
            return None
        import shutil
        import zipfile
        try:
            skinmod.load_wsz(path)
        except (zipfile.BadZipFile, OSError) as e:
            dialogs.message(self.top_window(), "“%s” isn't a skin Chordamp can read: %s" % (os.path.basename(path), e))
            return None
        name = os.path.basename(path)
        dest = os.path.join(skinmod.skins_dir(), name)
        if os.path.abspath(path) != os.path.abspath(dest):
            shutil.copyfile(path, dest)
        self.set_skin(name)
        return name

    def export_skin(self, path=None):
        from . import dialogs
        path = path or dialogs.save_file(self.top_window(), "Save Chordamp Skin", "Chordamp.wsz")
        if path:
            skinmod.export_folio(path)
        return path

    def seek_by(self, secs):
        e = self.pb.engine
        if e.state in ("playing", "paused") and e.duration() > 0:
            e.seek(max(0.0, min(e.duration() - 1, e.position() + secs)))

    # keys ---------------------------------------------------------------
    def key(self, e):
        k = Gdk.keyval_to_lower(e.keyval)
        ctrl = e.state & Gdk.ModifierType.CONTROL_MASK
        alt = e.state & Gdk.ModifierType.MOD1_MASK
        shift = e.state & Gdk.ModifierType.SHIFT_MASK
        if ctrl and shift and k == Gdk.KEY_w:
            self.win.run("look:standard")
        elif ctrl and k == Gdk.KEY_d:
            self.set_double(not self.settings.get("classic_double"))
        elif ctrl and k == Gdk.KEY_t:
            self.set_ontop(not self.settings.get("classic_ontop"))
        elif ctrl and k == Gdk.KEY_w:
            self.toggle_shade()
        elif ctrl and k == Gdk.KEY_q:
            self.win.run("quit")
        elif ctrl and k == Gdk.KEY_p:
            self.win.run("options")
        elif alt and k == Gdk.KEY_g:
            self.toggle_window("eq")
        elif alt and k == Gdk.KEY_e:
            self.toggle_window("pl")
        elif alt and k == Gdk.KEY_l:
            self.show_library(not (self.libwin and self.libwin.get_visible()))
        elif ctrl and k == Gdk.KEY_a and self.pl_active():
            self.select("all")
        elif alt and k in (Gdk.KEY_Up, Gdk.KEY_Down) and self.pl_active():
            self.move_rows(sorted(self.pl.sel), -1 if k == Gdk.KEY_Up else 1, self.pl)
        elif ctrl or alt:
            return False
        elif k == Gdk.KEY_z:
            self.transport("prev")
        elif k == Gdk.KEY_x:
            self.transport("play")
        elif k == Gdk.KEY_c:
            self.transport("pause")
        elif k == Gdk.KEY_v:
            self.transport("stop")
        elif k == Gdk.KEY_b:
            self.transport("next")
        elif k == Gdk.KEY_j:
            self.jump()
        elif k == Gdk.KEY_l:
            self.play_file()
        elif k == Gdk.KEY_s:
            self.pb.set_shuffle(not self.pb.queue.shuffle)
        elif k == Gdk.KEY_r:
            self.pb.set_repeat("off" if self.pb.queue.repeat != "off" else "all")
        elif k in (Gdk.KEY_Left, Gdk.KEY_Right) and not self.pl_active():
            self.seek_by(-5 if k == Gdk.KEY_Left else 5)
        elif k in (Gdk.KEY_Up, Gdk.KEY_Down) and not self.pl_active():
            self.pb.set_volume(max(0.0, min(1.0, self.pb.engine.volume + (0.04 if k == Gdk.KEY_Up else -0.04))))
        elif k in (Gdk.KEY_Up, Gdk.KEY_Down) and self.pl_active():
            d = -1 if k == Gdk.KEY_Up else 1
            n = len(self.pb.queue.source)
            if n:
                self.pl.focus_row = max(0, min(n - 1, self.pl.focus_row + d))
                self.pl.sel = {self.pl.focus_row}
                self.pl.anchor = self.pl.focus_row
                self.pl.show_row(self.pl.focus_row)
                self.pl.area.queue_draw()
        elif k in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self.pl_active():
            if self.pl.sel:
                self.play_index(min(self.pl.sel))
        elif k == Gdk.KEY_Delete and self.pl_active():
            self.remove_selected()
        else:
            return False
        return True
