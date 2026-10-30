"""The small windows (C3-02, C3-08): the Equalizer, the Mini Player, the Visualizer, and the Up
Next list."""
import math
import random

from gi.repository import Gdk, GLib, Gtk, Pango

from . import art, player, theme, views


class Equalizer(Gtk.Window):
    def __init__(self, win):
        super().__init__(title="Equalizer", transient_for=win)
        self.win = win
        self.get_style_context().add_class("chord-dialog")
        self.set_resizable(False)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        s = win.settings
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)
        self.add(box)
        top = Gtk.Box(spacing=8)
        self.on = Gtk.CheckButton(label="On")
        self.on.set_active(s["eq_on"])
        self.on.connect("toggled", lambda *_: self.apply())
        self.preset = Gtk.ComboBoxText()
        self.preset.append("Manual", "Manual")
        for p in sorted(player.PRESETS):
            self.preset.append(p, p)
        self.preset.set_active_id(s["eq_preset"] if s["eq_preset"] in player.PRESETS else "Manual")
        self.preset.connect("changed", lambda *_: self.pick())
        top.pack_start(self.on, False, False, 0)
        top.pack_end(self.preset, False, False, 0)
        box.pack_start(top, False, False, 0)
        sliders = Gtk.Box(spacing=6)
        self.scales = []
        self._quiet = False

        def column(label, val):
            c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            sc = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, -12, 12, 0.5)
            sc.set_inverted(True)
            sc.set_draw_value(False)
            sc.add_mark(0, Gtk.PositionType.RIGHT, None)
            sc.set_size_request(-1, 160)
            sc.set_value(val)
            sc.get_style_context().add_class("chord-eq-scale")
            sc.connect("value-changed", lambda *_: self.moved())
            c.pack_start(sc, True, True, 0)
            l = Gtk.Label(label=label)
            l.get_style_context().add_class("chord-dim")
            c.pack_start(l, False, False, 0)
            return c, sc
        c, self.preamp = column("Preamp", s["eq_preamp"])
        sliders.pack_start(c, False, False, 0)
        sliders.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)
        for i, hz in enumerate(player.BANDS):
            c, sc = column(("%dK" % (hz // 1000)) if hz >= 1000 else str(hz), s["eq_bands"][i])
            self.scales.append(sc)
            sliders.pack_start(c, False, False, 0)
        scale_lab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for t in ("+12 dB", "0 dB", "-12 dB"):
            l = Gtk.Label(label=t)
            l.get_style_context().add_class("chord-dim")
            scale_lab.pack_start(l, True, True, 0)
        sliders.pack_end(scale_lab, False, False, 0)
        box.pack_start(sliders, True, True, 0)

    def pick(self):
        name = self.preset.get_active_id()
        if name in player.PRESETS:
            pa, bands = player.PRESETS[name]
            self._quiet = True
            self.preamp.set_value(pa)
            for sc, v in zip(self.scales, bands):
                sc.set_value(v)
            self._quiet = False
            if not self.on.get_active():
                self.on.set_active(True)
        self.apply()

    def moved(self):
        if self._quiet:
            return
        if self.preset.get_active_id() != "Manual":
            self._quiet = True
            self.preset.set_active_id("Manual")
            self._quiet = False
        self.apply()

    def apply(self):
        s = self.win.settings
        bands = [sc.get_value() for sc in self.scales]
        s["eq_on"] = self.on.get_active()
        s["eq_preset"] = self.preset.get_active_id()
        s["eq_preamp"] = self.preamp.get_value()
        s["eq_bands"] = bands
        s.save()
        self.win.app.playback.engine.set_eq(s["eq_on"], s["eq_preamp"], bands)


class MiniPlayer(Gtk.Window):
    def __init__(self, win):
        super().__init__(title="Folio Chord")
        self.win = win
        self.get_style_context().add_class("chord-own")
        self.get_style_context().add_class("chord-mini")
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_icon_name("folio-chord")
        box = Gtk.Box(spacing=8)
        box.set_border_width(6)
        self.add(box)
        self.img = Gtk.Image()
        box.pack_start(self.img, False, False, 0)
        mid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.title = Gtk.Label(xalign=0)
        self.title.set_ellipsize(Pango.EllipsizeMode.END)
        self.title.set_max_width_chars(34)
        self.sub = Gtk.Label(xalign=0)
        self.sub.set_ellipsize(Pango.EllipsizeMode.END)
        self.sub.set_max_width_chars(34)
        self.sub.get_style_context().add_class("chord-dim")
        mid.pack_start(self.title, False, False, 0)
        mid.pack_start(self.sub, False, False, 0)
        row = Gtk.Box(spacing=4)
        from .window import round_button
        row.pack_start(round_button("prev", "Previous", lambda: win.run("previous")), False, False, 0)
        self.play = round_button("play", "Play", lambda: win.run("play-pause"))
        row.pack_start(self.play, False, False, 0)
        row.pack_start(round_button("next", "Next", lambda: win.run("next")), False, False, 0)
        self.vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.02)
        self.vol.set_draw_value(False)
        self.vol.set_size_request(90, -1)
        self.vol.set_value(win.app.playback.engine.volume)
        self.vol.connect("value-changed", lambda s: win.app.playback.set_volume(s.get_value()))
        row.pack_start(self.vol, False, False, 0)
        back = round_button("fullscreen", "Back to the full window", lambda: win.run("front"))
        row.pack_end(back, False, False, 0)
        mid.pack_start(row, False, False, 0)
        box.pack_start(mid, True, True, 0)
        self.connect("delete-event", lambda *a: (win.run("front"), True)[1])
        win.app.playback.listen(lambda ev, v: self.update() if ev in ("state", "track", "tags") else None)
        self.update()

    def update(self):
        pb = self.win.app.playback
        n = pb.now
        if not n:
            self.title.set_text("Folio Chord")
            self.sub.set_text("Nothing playing")
            self.img.set_from_pixbuf(art.placeholder(56, self.win.dark))
        else:
            self.title.set_text(n.get("title") or "")
            self.sub.set_text(pb.stream_title or " — ".join(x for x in (n.get("artist"), n.get("album")) if x))
            pbuf = art.for_song(n["path"], 56) if n.get("path") else None
            self.img.set_from_pixbuf(pbuf or art.placeholder(56, self.win.dark))
        playing = pb.engine.state == "playing"
        from .window import icon
        self.play.set_image(icon("pause" if playing else "play"))


class Visualizer(Gtk.Window):
    """Light that moves with the music: the spectrum as glowing bars over a slow drift of colour."""

    def __init__(self, win):
        super().__init__(title="Visualizer")
        self.win = win
        self.get_style_context().add_class("chord-vis")
        self.set_default_size(720, 420)
        self.da = Gtk.DrawingArea()
        self.da.connect("draw", self._draw)
        self.add(self.da)
        self.levels = [0.0] * 32
        self.peaks = [0.0] * 32
        self.t = 0.0
        self.frames = 0
        self.connect("key-press-event", self._key)
        self.connect("map", lambda *_: win.app.playback.engine.set_spectrum(True))
        self.connect("unmap", lambda *_: win.app.playback.engine.set_spectrum(False))
        self.connect("delete-event", lambda *a: (self.hide(), True)[1])
        self.da.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.da.connect("button-press-event", lambda w, e: e.type == Gdk.EventType._2BUTTON_PRESS and self.toggle_full())
        self.full = False
        GLib.timeout_add(33, self._tick)

    def toggle_full(self):
        self.full = not self.full
        (self.fullscreen if self.full else self.unfullscreen)()

    def _key(self, w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            if self.full:
                self.toggle_full()
            else:
                self.hide()
            return True
        if ev.keyval == Gdk.KEY_space:
            self.win.run("play-pause")
            return True
        return False

    def feed(self, mags):
        n = len(self.levels)
        for i in range(min(n, len(mags))):
            v = max(0.0, min(1.0, (mags[i] + 70) / 70.0))
            self.levels[i] = max(v, self.levels[i] * 0.85)
            self.peaks[i] = max(self.peaks[i] * 0.97, self.levels[i])

    def _tick(self):
        if not self.get_visible():
            return True
        self.t += 0.033
        if self.win.app.playback.engine.state != "playing":
            self.levels = [v * 0.9 for v in self.levels]
        self.da.queue_draw()
        return True

    def _draw(self, w, cr):
        self.frames += 1
        a = w.get_allocation()
        W, H = a.width, a.height
        cr.set_source_rgb(0, 0, 0)
        cr.paint()
        energy = sum(self.levels) / len(self.levels)
        # drifting colour clouds
        for k in range(5):
            x = W * (0.5 + 0.38 * math.sin(self.t * (0.21 + 0.07 * k) + k * 1.7))
            y = H * (0.5 + 0.34 * math.cos(self.t * (0.17 + 0.05 * k) + k))
            r = (0.25 + 0.5 * energy) * max(W, H) * (0.35 + 0.08 * k)
            hue = (self.t * 0.03 + k * 0.2) % 1.0
            rr, gg, bb = _hsv(hue, 0.8, 0.9)
            import cairo
            g = cairo.RadialGradient(x, y, 0, x, y, r)
            g.add_color_stop_rgba(0, rr, gg, bb, 0.32 + 0.4 * energy)
            g.add_color_stop_rgba(1, rr, gg, bb, 0)
            cr.set_source(g)
            cr.paint()
        n = len(self.levels)
        bw = W / float(n)
        for i, v in enumerate(self.levels):
            h = v * H * 0.75
            rr, gg, bb = _hsv((i / float(n) + self.t * 0.05) % 1.0, 0.65, 1.0)
            cr.set_source_rgba(rr, gg, bb, 0.75)
            cr.rectangle(i * bw + 2, H - h, bw - 4, h)
            cr.fill()
            cr.set_source_rgba(1, 1, 1, 0.8)
            cr.rectangle(i * bw + 2, H - self.peaks[i] * H * 0.75 - 3, bw - 4, 2)
            cr.fill()
        n_ = self.win.app.playback.now
        if n_:
            cr.set_source_rgba(1, 1, 1, 0.85)
            cr.select_font_face("Sans")
            cr.set_font_size(16)
            cr.move_to(18, 30)
            cr.show_text(self.win.app.playback.stream_title or n_.get("title") or "")
            cr.set_font_size(12)
            cr.move_to(18, 50)
            cr.show_text(" — ".join(x for x in (n_.get("artist"), n_.get("album")) if x))
        return True


def _hsv(h, s, v):
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    return [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]


def up_next(win, relative):
    """The songs coming up: Up Next first, then the rest of the list."""
    pb = win.app.playback
    pop = Gtk.Popover.new(relative)
    pop.get_style_context().add_class("chord-pop")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.set_border_width(8)
    head = Gtk.Box(spacing=8)
    t = Gtk.Label(xalign=0)
    t.set_markup("<b>Up Next</b>")
    head.pack_start(t, True, True, 0)
    clear = Gtk.Button(label="Clear")
    clear.connect("clicked", lambda *_: (pb.queue.clear_up_next(), pop.popdown()))
    head.pack_end(clear, False, False, 0)
    box.pack_start(head, False, False, 0)
    lb = Gtk.ListBox()
    lb.set_selection_mode(Gtk.SelectionMode.NONE)
    items = pb.queue.upcoming(30)
    for k in items:
        it = pb._item_for(k)
        if not it:
            continue
        row = Gtk.Box(spacing=8)
        l = Gtk.Label(xalign=0)
        l.set_ellipsize(Pango.EllipsizeMode.END)
        l.set_max_width_chars(40)
        l.set_markup("%s\n<small>%s</small>" % (GLib.markup_escape_text(it["title"] or ""), GLib.markup_escape_text(it.get("artist") or "")))
        row.pack_start(l, True, True, 0)
        row.pack_end(Gtk.Label(label=views.fmt_time(it.get("duration") or 0)), False, False, 0)
        lb.add(row)
    if not items:
        lb.add(Gtk.Label(label="Nothing is coming up. Choose Play Next or Add to Up Next on songs."))
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sw.set_size_request(360, min(420, 50 + 44 * max(1, len(items))))
    sw.add(lb)
    box.pack_start(sw, True, True, 0)
    pop.add(box)
    box.show_all()
    pop.popup()
    win.up_next_popover = pop
    return [x for x in items]
