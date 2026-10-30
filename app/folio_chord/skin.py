"""Chordamp skins (C3-33). A skin is a set of sprite sheets laid out as classic player skins
(.wsz files, a zip of bitmaps) lay them out, so downloaded skins and Chordamp's own work alike.

  folio()            Chordamp's own skin, drawn here (graphite and fuchsia; nothing copied)
  load_wsz(path)     a downloaded classic skin
  Skin.blit(cr, sheet, sx, sy, w, h, dx, dy)
  Skin.vis           24 visualizer colours; Skin.pl: the playlist editor's colours
"""
import os
import zipfile

import cairo
from gi.repository import Gdk, GdkPixbuf, GLib

SHEETS = ("main", "titlebar", "cbuttons", "numbers", "playpaus", "monoster", "posbar", "volume", "balance",
          "shufrep", "eqmain", "pledit", "text")


class Skin:
    def __init__(self, name):
        self.name = name
        self.sheets = {}
        self.vis = [(0, 0, 0)] * 24
        self.pl = {"normal": (0, 1, 0), "current": (1, 1, 1), "normalbg": (0, 0, 0), "selectedbg": (0, 0, 0.78),
                   "font": "Sans"}
        self.text_font = None          # None: draw text with Pango (Chordamp's own skin)
        self.lcd = (1.0, 0.31, 0.78)   # text colour when there is no text.bmp

    def has(self, sheet):
        return sheet in self.sheets

    def blit(self, cr, sheet, sx, sy, w, h, dx, dy):
        s = self.sheets.get(sheet)
        if s is None or w <= 0 or h <= 0:
            return False
        cr.save()
        cr.rectangle(dx, dy, w, h)
        cr.clip()
        cr.set_source_surface(s, dx - sx, dy - sy)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint()
        cr.restore()
        return True


# ---------------------------------------------------------------- loading .wsz
def _surface_from_bytes(data):
    loader = GdkPixbuf.PixbufLoader()
    loader.write(data)
    loader.close()
    pb = loader.get_pixbuf()
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, pb.get_width(), pb.get_height())
    cr = cairo.Context(s)
    Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0)
    cr.paint()
    return s


def _colour(t):
    t = t.strip().lstrip("#")
    if len(t) >= 6:
        try:
            return tuple(int(t[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        except ValueError:
            return None
    return None


def load_wsz(path):
    """A classic skin from a .wsz (or .zip) file; sheets it lacks come from Chordamp's own skin."""
    base = folio()
    sk = Skin(os.path.splitext(os.path.basename(path))[0])
    sk.sheets = dict(base.sheets)
    sk.vis = list(base.vis)
    sk.pl = dict(base.pl)
    with zipfile.ZipFile(path) as z:
        names = {os.path.basename(n).lower(): n for n in z.namelist() if not n.endswith("/")}
        for sheet in SHEETS:
            n = names.get(sheet + ".bmp") or names.get(sheet + ".png")
            if n:
                try:
                    sk.sheets[sheet] = _surface_from_bytes(z.read(n))
                except (GLib.Error, Exception):      # noqa: BLE001 — a damaged picture: keep Chordamp's
                    pass
        if "text" in sk.sheets:
            sk.text_font = "text"
        if "viscolor.txt" in names:
            cols = []
            for line in z.read(names["viscolor.txt"]).decode("latin-1").splitlines():
                parts = [p for p in line.split("//")[0].replace(",", " ").split() if p.strip()]
                if len(parts) >= 3:
                    try:
                        cols.append(tuple(max(0, min(255, int(p))) / 255.0 for p in parts[:3]))
                    except ValueError:
                        pass
            if len(cols) >= 24:
                sk.vis = cols[:24]
        if "pledit.txt" in names:
            for line in z.read(names["pledit.txt"]).decode("latin-1").splitlines():
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().lower()
                if k == "font":
                    sk.pl["font"] = v.strip() or "Sans"
                elif k in ("normal", "current", "normalbg", "selectedbg"):
                    c = _colour(v)
                    if c:
                        sk.pl[k] = c
    return sk


# ---------------------------------------------------------------- Chordamp's own skin
BODY1, BODY2 = (0.20, 0.20, 0.24), (0.11, 0.11, 0.14)
EDGE_HI, EDGE_LO = (0.42, 0.42, 0.48), (0.04, 0.04, 0.05)
LCD = (1.0, 0.31, 0.78)
LCD_DIM = (0.36, 0.08, 0.27)
ACCENT = (0.85, 0.16, 0.6)


def _new(w, h):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    return s, cairo.Context(s)


def _body(cr, x, y, w, h, top=BODY1, bottom=BODY2):
    g = cairo.LinearGradient(0, y, 0, y + h)
    g.add_color_stop_rgb(0, *top)
    g.add_color_stop_rgb(1, *bottom)
    cr.set_source(g)
    cr.rectangle(x, y, w, h)
    cr.fill()
    # fine brushed lines
    cr.set_line_width(1)
    for i in range(0, h, 2):
        cr.set_source_rgba(1, 1, 1, 0.025)
        cr.move_to(x, y + i + 0.5)
        cr.line_to(x + w, y + i + 0.5)
        cr.stroke()


def _bevel(cr, x, y, w, h, raised=True):
    hi, lo = (EDGE_HI, EDGE_LO) if raised else (EDGE_LO, EDGE_HI)
    cr.set_line_width(1)
    cr.set_source_rgb(*hi)
    cr.move_to(x + 0.5, y + h - 0.5)
    cr.line_to(x + 0.5, y + 0.5)
    cr.line_to(x + w - 0.5, y + 0.5)
    cr.stroke()
    cr.set_source_rgb(*lo)
    cr.move_to(x + w - 0.5, y + 0.5)
    cr.line_to(x + w - 0.5, y + h - 0.5)
    cr.line_to(x + 0.5, y + h - 0.5)
    cr.stroke()


def _panel(cr, x, y, w, h):
    cr.set_source_rgb(0.02, 0.02, 0.03)
    cr.rectangle(x, y, w, h)
    cr.fill()
    _bevel(cr, x, y, w, h, raised=False)


def _button(cr, x, y, w, h, pressed=False, lit=False):
    g = cairo.LinearGradient(0, y, 0, y + h)
    a, b = ((0.36, 0.36, 0.42), (0.20, 0.20, 0.24)) if not pressed else ((0.16, 0.16, 0.19), (0.27, 0.27, 0.31))
    g.add_color_stop_rgb(0, *a)
    g.add_color_stop_rgb(1, *b)
    cr.set_source(g)
    cr.rectangle(x, y, w, h)
    cr.fill()
    _bevel(cr, x, y, w, h, raised=not pressed)
    if lit:
        cr.set_source_rgba(*ACCENT, 0.9)
        cr.rectangle(x + 3, y + h - 4, w - 6, 2)
        cr.fill()


def _glyph(cr, kind, cx, cy, col=(0.88, 0.88, 0.92)):
    cr.set_source_rgb(*col)
    if kind == "play":
        cr.move_to(cx - 3, cy - 4)
        cr.line_to(cx + 4, cy)
        cr.line_to(cx - 3, cy + 4)
        cr.close_path()
        cr.fill()
    elif kind == "pause":
        cr.rectangle(cx - 4, cy - 4, 3, 8)
        cr.rectangle(cx + 1, cy - 4, 3, 8)
        cr.fill()
    elif kind == "stop":
        cr.rectangle(cx - 4, cy - 4, 8, 8)
        cr.fill()
    elif kind == "prev":
        cr.rectangle(cx - 5, cy - 4, 2, 8)
        cr.fill()
        for o in (0, 4):
            cr.move_to(cx + 1 + o, cy - 4)
            cr.line_to(cx - 3 + o, cy)
            cr.line_to(cx + 1 + o, cy + 4)
            cr.close_path()
            cr.fill()
    elif kind == "next":
        cr.rectangle(cx + 3, cy - 4, 2, 8)
        cr.fill()
        for o in (0, 4):
            cr.move_to(cx - 1 - o, cy - 4)
            cr.line_to(cx + 3 - o, cy)
            cr.line_to(cx - 1 - o, cy + 4)
            cr.close_path()
            cr.fill()
    elif kind == "eject":
        cr.move_to(cx - 5, cy + 1)
        cr.line_to(cx, cy - 4)
        cr.line_to(cx + 5, cy + 1)
        cr.close_path()
        cr.fill()
        cr.rectangle(cx - 5, cy + 3, 10, 2)
        cr.fill()


def _text(cr, s, x, y, size=7, col=(0.88, 0.88, 0.92), bold=False):
    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(size)
    cr.set_source_rgb(*col)
    cr.move_to(x, y)
    cr.show_text(s)


def _seg_digit(cr, d, x, y, col):
    """A 7-segment digit 9x13 (the LED time)."""
    seg = {0: "abcdef", 1: "bc", 2: "abged", 3: "abgcd", 4: "fgbc", 5: "afgcd", 6: "afgedc", 7: "abc", 8: "abcdefg", 9: "abcdfg"}
    lit = seg.get(d, "")
    rects = {"a": (2, 1, 5, 1.6), "g": (2, 5.7, 5, 1.6), "d": (2, 10.4, 5, 1.6),
             "f": (1, 2, 1.6, 4), "b": (6.4, 2, 1.6, 4), "e": (1, 7, 1.6, 4), "c": (6.4, 7, 1.6, 4)}
    for k, (rx, ry, rw, rh) in rects.items():
        on = k in lit
        cr.set_source_rgba(*(col if on else LCD_DIM), 1.0 if on else 0.55)
        cr.rectangle(x + rx, y + ry, rw, rh)
        cr.fill()


def folio():
    sk = Skin("Folio")
    S = sk.sheets
    # ---- main.bmp: the body, the display and the panels
    s, cr = _new(275, 116)
    _body(cr, 0, 0, 275, 116)
    _bevel(cr, 0, 0, 275, 116)
    _panel(cr, 9, 22, 101, 42)            # time and visualizer
    _panel(cr, 108, 23, 158, 13)           # song title
    _panel(cr, 108, 40, 24, 12)            # kbps
    _panel(cr, 153, 40, 16, 12)            # kHz
    _text(cr, "kbps", 134, 49, 6, (0.6, 0.6, 0.66))
    _text(cr, "kHz", 171, 49, 6, (0.6, 0.6, 0.66))
    _panel(cr, 14, 70, 252, 14)            # under the position bar
    cr.set_source_rgba(*ACCENT, 0.55)
    cr.rectangle(253, 91, 13, 13)
    cr.fill()
    _text(cr, "♪", 255, 102, 11, (1, 1, 1))
    S["main"] = s
    # ---- titlebar.bmp
    s, cr = _new(344, 87)
    for y, focused in ((0, True), (15, False)):
        _body(cr, 27, y, 275, 14, (0.30, 0.30, 0.36) if focused else (0.22, 0.22, 0.26), (0.18, 0.18, 0.22))
        cr.set_source_rgba(*ACCENT, 0.85 if focused else 0.35)
        for i in range(4):
            cr.rectangle(27 + 92, y + 3 + i * 2, 160, 1)
        cr.fill()
        cr.set_source_rgb(*BODY2)
        cr.rectangle(27 + 112, y + 2, 51, 10)
        cr.fill()
        _text(cr, "CHORDAMP", 27 + 114, y + 10, 7.5, (1, 1, 1) if focused else (0.7, 0.7, 0.75), True)
    for y, focused in ((29, True), (42, False)):      # shade bars
        _body(cr, 27, y, 275, 14, (0.30, 0.30, 0.36) if focused else (0.22, 0.22, 0.26), (0.18, 0.18, 0.22))
    for (x, y, glyph, pressed) in ((0, 0, "o", False), (0, 9, "o", True), (9, 0, "_", False), (9, 9, "_", True),
                                   (0, 18, "s", False), (9, 18, "s", True), (18, 0, "x", False), (18, 9, "x", True)):
        _button(cr, x, y, 9, 9, pressed)
        cr.set_source_rgb(0.9, 0.9, 0.95)
        cr.set_line_width(1)
        if glyph == "x":
            cr.move_to(x + 2.5, y + 2.5)
            cr.line_to(x + 6.5, y + 6.5)
            cr.move_to(x + 6.5, y + 2.5)
            cr.line_to(x + 2.5, y + 6.5)
            cr.stroke()
        elif glyph == "_":
            cr.rectangle(x + 2, y + 6, 5, 1)
            cr.fill()
        elif glyph == "s":
            cr.rectangle(x + 2, y + 2, 5, 1)
            cr.rectangle(x + 2, y + 4, 5, 1)
            cr.fill()
        else:
            cr.rectangle(x + 2, y + 2, 5, 5)
            cr.stroke()
    S["titlebar"] = s
    # ---- cbuttons.bmp
    s, cr = _new(136, 36)
    for i, (x, w, g) in enumerate(((0, 23, "prev"), (23, 23, "play"), (46, 23, "pause"), (69, 23, "stop"), (92, 22, "next"))):
        for y, pressed in ((0, False), (18, True)):
            _button(cr, x, y, w, 18, pressed)
            _glyph(cr, g, x + w / 2, y + 9)
    for y, pressed in ((0, False), (16, True)):
        _button(cr, 114, y, 22, 16, pressed)
        _glyph(cr, "eject", 125, y + 8)
    S["cbuttons"] = s
    # ---- numbers.bmp: LED digits, a blank and a minus
    s, cr = _new(108, 13)
    cr.set_source_rgb(0, 0, 0)
    cr.paint()
    for d in range(10):
        _seg_digit(cr, d, d * 9, 0, LCD)
    _seg_digit(cr, -1, 90, 0, LCD)
    _seg_digit(cr, -1, 99, 0, LCD)
    cr.set_source_rgb(*LCD)
    cr.rectangle(101, 6, 5, 1.6)
    cr.fill()
    S["numbers"] = s
    # ---- playpaus.bmp
    s, cr = _new(42, 9)
    cr.set_source_rgb(0, 0, 0)
    cr.paint()
    _glyph(cr, "play", 4.5, 4.5, (0.25, 1, 0.45))
    cr.save()
    cr.translate(9, 0)
    cr.scale(0.8, 0.8)
    _glyph(cr, "pause", 5.6, 5.6, LCD)
    cr.restore()
    cr.save()
    cr.translate(18, 0)
    cr.scale(0.8, 0.8)
    _glyph(cr, "stop", 5.6, 5.6, LCD)
    cr.restore()
    cr.set_source_rgb(*ACCENT)
    cr.rectangle(39, 2, 3, 5)
    cr.fill()
    S["playpaus"] = s
    # ---- monoster.bmp
    s, cr = _new(58, 24)
    cr.set_source_rgb(0, 0, 0)
    cr.paint()
    for (x, w, label) in ((0, 29, "STEREO"), (29, 27, "MONO")):
        for y, on in ((0, True), (12, False)):
            _text(cr, label, x + 2, y + 9, 6.5, LCD if on else LCD_DIM, True)
    S["monoster"] = s
    # ---- posbar.bmp
    s, cr = _new(307, 10)
    cr.set_source_rgb(0.04, 0.04, 0.05)
    cr.rectangle(0, 0, 248, 10)
    cr.fill()
    cr.set_source_rgba(*ACCENT, 0.35)
    cr.rectangle(0, 4, 248, 2)
    cr.fill()
    for x, pressed in ((248, False), (278, True)):
        _button(cr, x, 0, 29, 10, pressed, lit=True)
    S["posbar"] = s
    # ---- volume.bmp and balance.bmp: 28 backgrounds, then the thumbs
    for sheet, width, centre in (("volume", 68, False), ("balance", 38, True)):
        s, cr = _new(68, 433)
        x0 = 0 if sheet == "volume" else 9
        for i in range(28):
            y = i * 15
            cr.set_source_rgb(0.03, 0.03, 0.04)
            cr.rectangle(x0, y, width, 13)
            cr.fill()
            f = i / 27.0
            if centre:
                f = abs(i - 13.5) / 13.5
            col = (0.25 + 0.75 * f * ACCENT[0], 0.2 + 0.1 * (1 - f), 0.25 + 0.6 * f * ACCENT[2])
            cr.set_source_rgb(*col)
            cr.rectangle(x0 + 2, y + 5, (width - 4) * (i / 27.0 if not centre else 1), 3)
            cr.fill()
            _bevel(cr, x0, y, width, 13, raised=False)
        for x, pressed in ((15, False), (0, True)):
            _button(cr, x, 422, 14, 11, pressed, lit=True)
        S[sheet] = s
    # ---- shufrep.bmp
    s, cr = _new(92, 85)
    for (x, w, label) in ((28, 47, "SHUFFLE"), (0, 28, "REP")):
        for i, (pressed, on) in enumerate(((False, False), (True, False), (False, True), (True, True))):
            _button(cr, x, i * 15, w, 15, pressed, lit=on)
            _text(cr, label, x + 4, i * 15 + 10, 6, (1, 1, 1) if on else (0.75, 0.75, 0.8), True)
    for (x, label) in ((0, "EQ"), (23, "PL")):
        for (dx, dy, pressed, on) in ((0, 61, False, False), (0, 73, False, True), (46, 61, True, False), (46, 73, True, True)):
            _button(cr, x + dx, dy, 23, 12, pressed, lit=on)
            _text(cr, label, x + dx + 6, dy + 8.5, 6, (1, 1, 1) if on else (0.75, 0.75, 0.8), True)
    S["shufrep"] = s
    # ---- eqmain.bmp
    s, cr = _new(275, 315)
    _body(cr, 0, 0, 275, 116)
    _bevel(cr, 0, 0, 275, 116)
    _panel(cr, 86, 17, 113, 19)
    for i, hz in enumerate(("PRE", "32", "64", "125", "250", "500", "1K", "2K", "4K", "8K", "16K")):
        x = 21 if i == 0 else 78 + (i - 1) * 18
        _text(cr, hz, x - 1, 112, 5.5, (0.65, 0.65, 0.7))
    for y, focused in ((134, True), (149, False)):
        _body(cr, 0, y, 275, 14, (0.30, 0.30, 0.36) if focused else (0.22, 0.22, 0.26), (0.18, 0.18, 0.22))
        _text(cr, "CHORDAMP EQUALIZER", 90, y + 10, 7, (1, 1, 1) if focused else (0.7, 0.7, 0.75), True)
    for (x, w, label, on, pressed) in ((10, 26, "ON", False, False), (69, 26, "ON", True, False), (128, 26, "ON", False, True),
                                       (187, 26, "ON", True, True), (36, 32, "AUTO", False, False), (95, 32, "AUTO", True, False),
                                       (154, 32, "AUTO", False, True), (213, 32, "AUTO", True, True)):
        _button(cr, x, 119, w, 12, pressed, lit=on)
        _text(cr, label, x + 4, 128, 6, (1, 1, 1) if on else (0.75, 0.75, 0.8), True)
    for i in range(28):
        x, y = 13 + (i % 14) * 15, 164 + (i // 14) * 65
        cr.set_source_rgb(0.03, 0.03, 0.04)
        cr.rectangle(x, y, 14, 63)
        cr.fill()
        f = i / 27.0
        cr.set_source_rgb(0.3 + 0.6 * f, 0.15, 0.3 + 0.4 * f)
        cr.rectangle(x + 5, y + 2, 4, 59)
        cr.fill()
        _bevel(cr, x, y, 14, 63, raised=False)
    for y, pressed in ((164, False), (176, True)):
        _button(cr, 0, y, 11, 11, pressed, lit=True)
    for y, pressed in ((164, False), (176, True)):
        _button(cr, 224, y, 44, 12, pressed)
        _text(cr, "PRESETS", 227, y + 9, 6, (0.9, 0.9, 0.95), True)
    cr.set_source_rgb(0.02, 0.02, 0.03)
    cr.rectangle(0, 294, 113, 19)
    cr.fill()
    cr.set_source_rgba(1, 1, 1, 0.2)
    cr.rectangle(0, 303, 113, 1)
    cr.fill()
    cr.set_source_rgb(0.6, 0.6, 0.65)
    cr.rectangle(0, 314, 113, 1)
    cr.fill()
    for i in range(19):
        f = i / 18.0
        cr.set_source_rgb(1.0, 0.3 + 0.5 * f, 0.6 - 0.4 * f)
        cr.rectangle(115, 294 + i, 1, 1)
        cr.fill()
    S["eqmain"] = s
    # ---- pledit.bmp: the playlist editor's frame
    s, cr = _new(280, 186)
    for y, focused in ((0, True), (21, False)):
        top = (0.30, 0.30, 0.36) if focused else (0.22, 0.22, 0.26)
        _body(cr, 0, y, 25, 20, top)
        _body(cr, 26, y, 100, 20, top)
        _body(cr, 127, y, 25, 20, top)
        _body(cr, 153, y, 25, 20, top)
        cr.set_source_rgba(*ACCENT, 0.8 if focused else 0.3)
        for i in range(4):
            cr.rectangle(127, y + 6 + i * 2, 25, 1)
            cr.rectangle(0, y + 6 + i * 2, 25, 1)
        cr.fill()
        _text(cr, "PLAYLIST", 46, y + 13, 7.5, (1, 1, 1) if focused else (0.7, 0.7, 0.75), True)
        _button(cr, 153 + 14, y + 3, 9, 9)
        cr.set_source_rgb(0.9, 0.9, 0.95)
        cr.set_line_width(1)
        cr.move_to(153 + 16.5, y + 5.5)
        cr.line_to(153 + 20.5, y + 9.5)
        cr.move_to(153 + 20.5, y + 5.5)
        cr.line_to(153 + 16.5, y + 9.5)
        cr.stroke()
    _body(cr, 0, 42, 12, 29)
    _body(cr, 31, 42, 20, 29)
    cr.set_source_rgb(0.05, 0.05, 0.06)
    cr.rectangle(36, 42, 8, 29)
    cr.fill()
    _button(cr, 52, 53, 8, 18)
    _button(cr, 61, 53, 8, 18, True)
    _body(cr, 0, 72, 125, 38)
    _body(cr, 126, 72, 150, 38)
    _body(cr, 179, 0, 25, 38)
    for i, label in enumerate(("ADD", "REM", "SEL", "MISC")):
        _button(cr, 11 + i * 29, 72 + 10, 25, 18)
        _text(cr, label, 13 + i * 29, 72 + 22, 6, (0.88, 0.88, 0.92), True)
    _button(cr, 126 + 104, 72 + 10, 22, 18)
    _text(cr, "LIST", 126 + 105, 72 + 22, 6, (0.88, 0.88, 0.92), True)
    _panel(cr, 126 + 7, 72 + 10, 90, 10)
    S["pledit"] = s
    sk.vis = [(0, 0, 0), (0.12, 0.12, 0.14)] + [(1.0, 0.15 + 0.045 * i, 0.75 - 0.04 * i) for i in range(16)] + \
        [(0.9, 0.9, 0.95)] * 5 + [(1, 1, 1)]
    sk.pl = {"normal": (0.95, 0.42, 0.82), "current": (1, 1, 1), "normalbg": (0.03, 0.03, 0.04),
             "selectedbg": (0.42, 0.06, 0.32), "font": "Sans"}
    sk.lcd = LCD
    return sk


def skins_dir():
    d = os.path.join(GLib.get_user_data_dir(), "folio-chord", "skins")
    os.makedirs(d, exist_ok=True)
    return d


def installed():
    d = skins_dir()
    return sorted(f for f in os.listdir(d) if f.lower().endswith((".wsz", ".zip")))


def by_name(name):
    if not name:
        return folio()
    p = os.path.join(skins_dir(), name)
    if os.path.exists(p):
        try:
            return load_wsz(p)
        except (zipfile.BadZipFile, OSError):
            pass
    return folio()


def export_folio(path):
    """Chordamp's own skin written out as a .wsz (bitmaps in a zip), e.g. to start a skin of your own."""
    sk = folio()
    with zipfile.ZipFile(path, "w") as z:
        for name, s in sk.sheets.items():
            pb = Gdk.pixbuf_get_from_surface(s, 0, 0, s.get_width(), s.get_height())
            ok, data = pb.save_to_bufferv("bmp", [], [])
            z.writestr(name + ".bmp", bytes(data))
        z.writestr("viscolor.txt", "\n".join("%d,%d,%d," % tuple(int(c * 255) for c in v) for v in sk.vis))
        z.writestr("pledit.txt", "[Text]\nNormal=#%02X%02X%02X\nCurrent=#FFFFFF\nNormalBG=#080809\nSelectedBG=#6B1052\nFont=Sans\n"
                   % tuple(int(c * 255) for c in sk.pl["normal"]))
    return path


