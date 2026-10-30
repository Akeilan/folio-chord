"""Folio Chord's dialogs: messages, Get Info (C3-04), the Smart Playlist rules (C3-03), View
Options, Options, podcast settings, Import CD and Burn (C3-07), Create Version, Keyboard Shortcuts
and About."""
import json
import os
import threading
import time

from gi.repository import GdkPixbuf, GLib, Gtk, Pango

from . import APP_NAME, art, cd, library, player, tags, views

RESPONSE = {}      # tests: {dialog title: response or callable(dialog) -> response}


class Dialog(Gtk.Dialog):
    def __init__(self, parent, title, buttons=(("Cancel", Gtk.ResponseType.CANCEL), ("OK", Gtk.ResponseType.OK))):
        super().__init__(title=title, transient_for=parent, modal=True)
        self.get_style_context().add_class("chord-dialog")
        for label, resp in buttons:
            b = self.add_button(label, resp)
            if resp == Gtk.ResponseType.OK or label in ("Delete", "Unsubscribe", "Import", "Burn", "Subscribe", "Move to Trash"):
                b.get_style_context().add_class("chord-default")
        if buttons:
            self.set_default_response(buttons[-1][1])
        self.body = self.get_content_area()
        self.body.set_spacing(8)
        self.body.set_border_width(12)

    def ask(self):
        self.show_all()
        r = RESPONSE.get(self.get_title())
        if r is not None:
            res = r(self) if callable(r) else r
            self.destroy_later()
            return res
        res = self.run()
        return res

    def destroy_later(self):
        GLib.idle_add(lambda: (self.destroy(), False)[1])


def message(win, text, title=None):
    d = Dialog(win, title or APP_NAME, (("OK", Gtk.ResponseType.OK),))
    l = Gtk.Label(label=text, xalign=0)
    l.set_line_wrap(True)
    l.set_max_width_chars(70)
    l.set_selectable(True)
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sw.set_propagate_natural_height(True)
    sw.set_max_content_height(420)
    sw.add(l)
    d.body.pack_start(sw, True, True, 0)
    if hasattr(win, "missing_log"):
        win.last_message = text
    d.ask()
    d.destroy()
    return text


def confirm(win, text, detail="", ok="OK"):
    d = Dialog(win, APP_NAME, (("Cancel", Gtk.ResponseType.CANCEL), (ok, Gtk.ResponseType.OK)))
    t = Gtk.Label(xalign=0)
    t.set_markup("<b>%s</b>" % GLib.markup_escape_text(text))
    t.set_line_wrap(True)
    d.body.pack_start(t, False, False, 0)
    if detail:
        x = Gtk.Label(label=detail, xalign=0)
        x.set_line_wrap(True)
        d.body.pack_start(x, False, False, 0)
    d.set_title("Confirm")
    r = d.ask()
    d.destroy()
    return r == Gtk.ResponseType.OK


def choose(win, text, detail, options):
    """options: [(label, value)]; returns the value of the button pressed."""
    d = Dialog(win, "Choose", tuple((label, i + 1) for i, (label, _v) in enumerate(options)))
    t = Gtk.Label(xalign=0)
    t.set_markup("<b>%s</b>" % GLib.markup_escape_text(text))
    d.body.pack_start(t, False, False, 0)
    if detail:
        d.body.pack_start(Gtk.Label(label=detail, xalign=0), False, False, 0)
    r = d.ask()
    d.destroy()
    if isinstance(r, int) and 1 <= r <= len(options):
        return options[r - 1][1]
    return options[0][1]


def ask_text(win, title, prompt, value=""):
    d = Dialog(win, title)
    d.body.pack_start(Gtk.Label(label=prompt, xalign=0), False, False, 0)
    e = Gtk.Entry(text=value)
    e.set_activates_default(True)
    e.set_width_chars(50)
    d.body.pack_start(e, False, False, 0)
    d.entry = e
    r = d.ask()
    v = e.get_text()
    d.destroy()
    return v if r == Gtk.ResponseType.OK else None


def _chooser(win, title, action, name=None):
    c = Gtk.FileChooserNative.new(title, win, action, None, None)
    if name:
        c.set_current_name(name)
        c.set_do_overwrite_confirmation(True)
    return c


def choose_files(win, title, audio=False, patterns=None, multiple=True):
    c = _chooser(win, title, Gtk.FileChooserAction.OPEN)
    c.set_select_multiple(multiple)
    if audio:
        f = Gtk.FileFilter()
        f.set_name("Music")
        for e in tags.EXTENSIONS:
            f.add_pattern("*" + e)
            f.add_pattern("*" + e.upper())
        c.add_filter(f)
    for name, pats in patterns or []:
        f = Gtk.FileFilter()
        f.set_name(name)
        for p in pats:
            f.add_pattern(p)
        c.add_filter(f)
    r = c.run()
    files = c.get_filenames() if r == Gtk.ResponseType.ACCEPT else []
    c.destroy()
    return files


def choose_folder(win, title):
    c = _chooser(win, title, Gtk.FileChooserAction.SELECT_FOLDER)
    r = c.run()
    f = c.get_filename() if r == Gtk.ResponseType.ACCEPT else None
    c.destroy()
    return f


def save_file(win, title, name):
    c = _chooser(win, title, Gtk.FileChooserAction.SAVE, name)
    r = c.run()
    f = c.get_filename() if r == Gtk.ResponseType.ACCEPT else None
    c.destroy()
    return f


def grid():
    g = Gtk.Grid(column_spacing=8, row_spacing=6)
    return g


def lab(text, xalign=1.0, dim=False):
    l = Gtk.Label(label=text, xalign=xalign)
    if dim:
        l.get_style_context().add_class("chord-dim")
    return l


# ================================================================ Get Info
INFO_FIELDS = [("title", "Name"), ("artist", "Artist"), ("album_artist", "Album Artist"), ("album", "Album"),
               ("grouping", "Grouping"), ("composer", "Composer"), ("comments", "Comments"), ("genre", "Genre")]


class InfoDialog(Dialog):
    """Get Info: one song (Summary, Info, Options, Artwork; Previous and Next), or several (the
    fields they share; only what you change is written)."""

    def __init__(self, win, ids):
        super().__init__(win, "Get Info", (("Cancel", Gtk.ResponseType.CANCEL), ("OK", Gtk.ResponseType.OK)))
        self.win = win
        self.lib = win.lib
        self.ids = list(ids)
        self.multi = len(ids) > 1
        self.pos = 0
        self.set_default_size(560, 470)
        if not self.multi:
            nav = Gtk.Box(spacing=4)
            self.prev_b = Gtk.Button(label="Previous")
            self.next_b = Gtk.Button(label="Next")
            self.prev_b.connect("clicked", lambda *_: self.step(-1))
            self.next_b.connect("clicked", lambda *_: self.step(1))
            nav.pack_start(self.prev_b, False, False, 0)
            nav.pack_start(self.next_b, False, False, 0)
            self.get_action_area().pack_start(nav, False, False, 0)
            self.get_action_area().reorder_child(nav, 0)
        self.nb = Gtk.Notebook()
        self.body.pack_start(self.nb, True, True, 0)
        self.entries = {}
        self.touched = set()
        if not self.multi:
            self._summary_page()
        self._info_page()
        self._options_page()
        self._art_page()
        self.load()

    def _page(self, title):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        b.get_style_context().add_class("chord-page")
        b.set_border_width(10)
        self.nb.append_page(b, Gtk.Label(label=title))
        return b

    def _summary_page(self):
        b = self._page("Summary")
        top = Gtk.Box(spacing=12)
        self.sum_art = Gtk.Image()
        top.pack_start(self.sum_art, False, False, 0)
        self.sum_head = Gtk.Label(xalign=0)
        self.sum_head.set_line_wrap(True)
        top.pack_start(self.sum_head, True, True, 0)
        b.pack_start(top, False, False, 0)
        self.sum_grid = grid()
        b.pack_start(self.sum_grid, False, False, 0)

    def _entry(self, key, width=30):
        e = Gtk.Entry()
        e.set_width_chars(width)
        e.connect("changed", lambda w: None if getattr(self, "_loading", False) else self.touched.add(key))
        self.entries[key] = e
        return e

    def _info_page(self):
        b = self._page("Info")
        g = grid()
        r = 0
        for key, label in INFO_FIELDS:
            g.attach(lab(label), 0, r, 1, 1)
            g.attach(self._entry(key, 36), 1, r, 3, 1)
            r += 1
        g.attach(lab("Year"), 0, r, 1, 1)
        g.attach(self._entry("year", 6), 1, r, 1, 1)
        g.attach(lab("BPM"), 2, r, 1, 1)
        g.attach(self._entry("bpm", 6), 3, r, 1, 1)
        r += 1
        for key, label in (("track", "Track Number"), ("disc", "Disc Number")):
            g.attach(lab(label), 0, r, 1, 1)
            box = Gtk.Box(spacing=4)
            box.pack_start(self._entry(key + "_no", 4), False, False, 0)
            box.pack_start(lab("of", 0.5), False, False, 0)
            box.pack_start(self._entry(key + "_count", 4), False, False, 0)
            g.attach(box, 1, r, 2, 1)
            r += 1
        self.comp = Gtk.CheckButton(label="Part of a compilation")
        self.comp.connect("toggled", lambda w: None if getattr(self, "_loading", False) else self.touched.add("compilation"))
        g.attach(self.comp, 1, r, 3, 1)
        b.pack_start(g, False, False, 0)

    def _options_page(self):
        b = self._page("Options")
        g = grid()
        g.attach(lab("Volume Adjustment"), 0, 0, 1, 1)
        self.vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -100, 100, 5)
        self.vol.set_size_request(260, -1)
        self.vol.add_mark(0, Gtk.PositionType.BOTTOM, "None")
        self.vol.add_mark(-100, Gtk.PositionType.BOTTOM, "-100%")
        self.vol.add_mark(100, Gtk.PositionType.BOTTOM, "+100%")
        self.vol.connect("value-changed", lambda w: None if getattr(self, "_loading", False) else self.touched.add("volume_adjust"))
        g.attach(self.vol, 1, 0, 3, 1)
        g.attach(lab("Equalizer Preset"), 0, 1, 1, 1)
        self.eq = Gtk.ComboBoxText()
        self.eq.append("", "None")
        for p in sorted(player.PRESETS):
            self.eq.append(p, p)
        self.eq.connect("changed", lambda w: None if getattr(self, "_loading", False) else self.touched.add("eq"))
        g.attach(self.eq, 1, 1, 2, 1)
        g.attach(lab("Rating"), 0, 2, 1, 1)
        self.rating = Gtk.ComboBoxText()
        for n in range(6):
            self.rating.append(str(n * 20), "★" * n if n else "None")
        self.rating.connect("changed", lambda w: None if getattr(self, "_loading", False) else self.touched.add("rating"))
        g.attach(self.rating, 1, 2, 2, 1)
        if not self.multi:
            self.start_c = Gtk.CheckButton(label="Start Time")
            self.start_e = Gtk.Entry(width_chars=8)
            self.stop_c = Gtk.CheckButton(label="Stop Time")
            self.stop_e = Gtk.Entry(width_chars=8)
            g.attach(self.start_c, 0, 3, 1, 1)
            g.attach(self.start_e, 1, 3, 1, 1)
            g.attach(self.stop_c, 0, 4, 1, 1)
            g.attach(self.stop_e, 1, 4, 1, 1)
        self.remember = Gtk.CheckButton(label="Remember playback position")
        self.skip_shuffle = Gtk.CheckButton(label="Skip when shuffling")
        self.remember.connect("toggled", lambda w: None if getattr(self, "_loading", False) else self.touched.add("remember_position"))
        self.skip_shuffle.connect("toggled", lambda w: None if getattr(self, "_loading", False) else self.touched.add("skip_shuffle"))
        g.attach(self.remember, 0, 5, 3, 1)
        g.attach(self.skip_shuffle, 0, 6, 3, 1)
        b.pack_start(g, False, False, 0)

    def _art_page(self):
        b = self._page("Artwork")
        self.art_img = Gtk.Image()
        self.art_img.get_style_context().add_class("chord-art")
        self.art_img.set_size_request(260, 260)
        b.pack_start(self.art_img, False, False, 0)
        row = Gtk.Box(spacing=6)
        add = Gtk.Button(label="Add…")
        rm = Gtk.Button(label="Delete")
        add.connect("clicked", lambda *_: self.add_art())
        rm.connect("clicked", lambda *_: self.set_art(None))
        row.pack_start(add, False, False, 0)
        row.pack_start(rm, False, False, 0)
        b.pack_start(row, False, False, 0)
        self.new_art = "keep"

    def rows(self):
        return [self.lib.track(i) for i in self.ids]

    def load(self):
        self._loading = True
        self.touched = set()
        self.new_art = "keep"
        rows = [self.lib.track(self.ids[self.pos])] if not self.multi else self.rows()

        def common(key):
            vals = {r[key] for r in rows}
            return vals.pop() if len(vals) == 1 else None
        for key, _l in INFO_FIELDS:
            v = common(key)
            self.entries[key].set_text(v or "")
            self.entries[key].set_placeholder_text("Mixed" if v is None and self.multi else "")
        for key in ("year", "bpm", "track_no", "track_count", "disc_no", "disc_count"):
            v = common(key)
            self.entries[key].set_text(str(v) if v else "")
            self.entries[key].set_placeholder_text("Mixed" if v is None and self.multi else "")
        self.comp.set_active(bool(common("compilation")))
        self.vol.set_value(common("volume_adjust") or 0)
        self.eq.set_active_id(common("eq") or "")
        self.rating.set_active_id(str(common("rating") or 0))
        self.remember.set_active(bool(common("remember_position")))
        self.skip_shuffle.set_active(bool(common("skip_shuffle")))
        r = rows[0]
        if not self.multi:
            self.set_title("Get Info")
            self.start_c.set_active(bool(r["start_time"]))
            self.start_e.set_text(views.fmt_time(r["start_time"] or 0))
            self.stop_c.set_active(bool(r["stop_time"]))
            self.stop_e.set_text(views.fmt_time(r["stop_time"] or r["duration"]))
            pb = art.for_song(r["path"], 96) or art.placeholder(96, self.win.dark)
            self.sum_art.set_from_pixbuf(pb)
            self.sum_head.set_markup("<b>%s</b>\n%s\n%s\n<small>%s</small>" % tuple(GLib.markup_escape_text(x or "") for x in (
                r["title"], r["artist"], r["album"], views.fmt_time(r["duration"]))))
            for c in self.sum_grid.get_children():
                self.sum_grid.remove(c)
            facts = [("Kind", r["kind"]), ("Size", "%.1f MB" % ((r["size"] or 0) / 1e6)),
                     ("Bit Rate", "%d kbps" % r["bitrate"] if r["bitrate"] else ""),
                     ("Sample Rate", "%.1f kHz" % (r["sample_rate"] / 1000.0) if r["sample_rate"] else ""),
                     ("Date Modified", views.fmt_date(r["date_modified"])), ("Date Added", views.fmt_date(r["date_added"])),
                     ("Plays", str(r["play_count"] or 0)), ("Last Played", views.fmt_date(r["last_played"])),
                     ("Skips", str(r["skip_count"] or 0)), ("Where", r["path"])]
            for i, (k, v) in enumerate(facts):
                self.sum_grid.attach(lab(k + ":", 1.0, True), 0, i, 1, 1)
                vl = Gtk.Label(label=v or "", xalign=0)
                vl.set_selectable(True)
                vl.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
                vl.set_max_width_chars(60)
                self.sum_grid.attach(vl, 1, i, 1, 1)
            self.sum_grid.show_all()
            self.prev_b.set_sensitive(self.pos > 0)
            self.next_b.set_sensitive(self.pos < len(self.ids) - 1)
        else:
            self.set_title("Multiple Item Information")
        pb = art.for_song(r["path"], 256) if (not self.multi or len({x["album"] for x in rows}) == 1) else None
        self.art_img.set_from_pixbuf(pb or art.placeholder(256, self.win.dark))
        self._loading = False

    def step(self, d):
        self.save()
        self.pos = max(0, min(len(self.ids) - 1, self.pos + d))
        self.load()

    def add_art(self):
        f = choose_files(self, "Choose Artwork", patterns=[("Pictures", ["*.jpg", "*.jpeg", "*.png"])], multiple=False)
        if f:
            with open(f[0], "rb") as fh:
                self.set_art(fh.read())

    def set_art(self, data):
        self.new_art = data
        if data is None:
            self.art_img.set_from_pixbuf(art.placeholder(256, self.win.dark))
        else:
            loader = GdkPixbuf.PixbufLoader()
            loader.write(data)
            loader.close()
            pb = loader.get_pixbuf()
            self.art_img.set_from_pixbuf(pb.scale_simple(256, int(256 * pb.get_height() / max(1, pb.get_width())),
                                                         GdkPixbuf.InterpType.BILINEAR))

    def changes(self):
        ch = {}
        for key, _l in INFO_FIELDS:
            if key in self.touched:
                ch[key] = self.entries[key].get_text().strip()
        for key in ("year", "bpm", "track_no", "track_count", "disc_no", "disc_count"):
            if key in self.touched:
                t = self.entries[key].get_text().strip()
                ch[key] = int(t) if t.isdigit() else 0
        if "compilation" in self.touched:
            ch["compilation"] = self.comp.get_active()
        return ch

    def save(self):
        ids = self.ids if self.multi else [self.ids[self.pos]]
        ch = self.changes()
        db = {}
        if "volume_adjust" in self.touched:
            db["volume_adjust"] = int(self.vol.get_value())
        if "eq" in self.touched:
            db["eq"] = self.eq.get_active_id() or ""
        if "rating" in self.touched:
            db["rating"] = int(self.rating.get_active_id() or 0)
        if "remember_position" in self.touched:
            db["remember_position"] = 1 if self.remember.get_active() else 0
        if "skip_shuffle" in self.touched:
            db["skip_shuffle"] = 1 if self.skip_shuffle.get_active() else 0
        if not self.multi:
            def secs(e):
                parts = [p for p in e.get_text().split(":") if p.strip()]
                try:
                    v = 0.0
                    for p in parts:
                        v = v * 60 + float(p)
                    return v
                except ValueError:
                    return 0.0
            r = self.lib.track(ids[0])
            st = secs(self.start_e) if self.start_c.get_active() else 0
            sp = secs(self.stop_e) if self.stop_c.get_active() else 0
            if sp and abs(sp - (r["duration"] or 0)) < 1:
                sp = 0
            if st != (r["start_time"] or 0) or sp != (r["stop_time"] or 0):
                db["start_time"], db["stop_time"] = st, sp
        errors = []
        for tid in ids:
            r = self.lib.track(tid)
            try:
                if ch:
                    tags.write(r["path"], ch)
                if self.new_art != "keep":
                    tags.set_artwork(r["path"], self.new_art)
                if ch or self.new_art != "keep":
                    self.lib.add_file(r["path"])
            except Exception as e:      # noqa: BLE001
                errors.append("%s: %s" % (os.path.basename(r["path"]), e))
        if db:
            self.lib.update(ids, **db)
        if self.new_art != "keep":
            art._cache.clear()
        if ch or self.new_art != "keep":
            self.lib.changed()
        self.touched = set()
        self.new_art = "keep"
        return errors


def get_info(win, ids):
    d = InfoDialog(win, ids)
    win.info_dialog = d
    r = d.ask()
    errors = d.save() if r == Gtk.ResponseType.OK else []
    d.destroy()
    if errors:
        message(win, "Some files couldn't be changed:\n" + "\n".join(errors))
    return r == Gtk.ResponseType.OK


# ================================================================ Smart Playlist
class SmartDialog(Dialog):
    def __init__(self, win, spec):
        super().__init__(win, "Smart Playlist")
        self.win = win
        spec = spec or {"match": "all", "rules": [["artist", "contains", ""]]}
        top = Gtk.Box(spacing=6)
        top.pack_start(lab("Name", 0), False, False, 0)
        self.name = Gtk.Entry(text=spec.get("name", "untitled playlist"))
        top.pack_start(self.name, True, True, 0)
        self.body.pack_start(top, False, False, 0)
        m = Gtk.Box(spacing=6)
        self.use_match = Gtk.CheckButton(label="Match")
        self.use_match.set_active(True)
        self.match = Gtk.ComboBoxText()
        self.match.append("all", "all")
        self.match.append("any", "any")
        self.match.set_active_id(spec.get("match", "all"))
        m.pack_start(self.use_match, False, False, 0)
        m.pack_start(self.match, False, False, 0)
        m.pack_start(lab("of the following rules:", 0), False, False, 0)
        self.body.pack_start(m, False, False, 0)
        self.rules_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.body.pack_start(self.rules_box, False, False, 0)
        self.rule_rows = []
        for r in spec.get("rules") or [["artist", "contains", ""]]:
            self.add_rule(r)
        lim = Gtk.Box(spacing=6)
        self.use_limit = Gtk.CheckButton(label="Limit to")
        self.limit_n = Gtk.SpinButton.new_with_range(1, 100000, 1)
        self.limit_unit = Gtk.ComboBoxText()
        for u in ("items", "minutes", "hours", "MB", "GB"):
            self.limit_unit.append(u, u)
        self.sel_by = Gtk.ComboBoxText()
        for k in library.SELECTED_BY:
            self.sel_by.append(k, k)
        l = spec.get("limit")
        self.use_limit.set_active(bool(l))
        self.limit_n.set_value(l[0] if l else 25)
        self.limit_unit.set_active_id(l[1] if l else "items")
        self.sel_by.set_active_id(spec.get("selected_by") or "random")
        for w in (self.use_limit, self.limit_n, self.limit_unit, lab("selected by", 0), self.sel_by):
            lim.pack_start(w, False, False, 0)
        self.body.pack_start(lim, False, False, 0)
        self.checked = Gtk.CheckButton(label="Match only checked items")
        self.checked.set_active(bool(spec.get("checked_only")))
        self.body.pack_start(self.checked, False, False, 0)
        self.live = Gtk.CheckButton(label="Live updating")
        self.live.set_active(True)
        self.live.set_sensitive(False)
        self.body.pack_start(self.live, False, False, 0)

    def add_rule(self, r=None, after=None):
        r = list(r or ["artist", "contains", ""])
        row = Gtk.Box(spacing=4)
        field = Gtk.ComboBoxText()
        for label, col, _k in library.FIELDS:
            field.append(col, label)
        op = Gtk.ComboBoxText()
        v1 = Gtk.Entry(width_chars=16)
        v2 = Gtk.Entry(width_chars=8)
        unit = Gtk.ComboBoxText()
        for u in ("days", "weeks", "months"):
            unit.append(u, u)
        rating = Gtk.ComboBoxText()
        for n in range(6):
            rating.append(str(n * 20), "★" * n if n else "none")
        add = Gtk.Button(label="+")
        rm = Gtk.Button(label="−")
        rec = {"row": row, "field": field, "op": op, "v1": v1, "v2": v2, "unit": unit, "rating": rating}

        def kind():
            return library.FIELD.get(field.get_active_id(), ("", "text"))[1]

        def refill_ops(keep=None):
            op.remove_all()
            for o in library.OPS[kind()]:
                op.append(o, o)
            if not op.set_active_id(keep or ""):
                op.set_active(0)
            show()

        def show(*_):
            k, o = kind(), op.get_active_id() or ""
            v1.set_visible(k in ("text", "number", "date"))
            rating.set_visible(k == "rating")
            v2.set_visible(o == "is in the range" and k in ("number",))
            unit.set_visible(k == "date" and o in ("is in the last", "is not in the last"))
        field.connect("changed", lambda *_: refill_ops())
        op.connect("changed", show)
        add.connect("clicked", lambda *_: self.add_rule(None, rec))
        rm.connect("clicked", lambda *_: self.remove_rule(rec))
        for w in (field, op, v1, rating, v2, unit):
            row.pack_start(w, False, False, 0)
        row.pack_end(rm, False, False, 0)
        row.pack_end(add, False, False, 0)
        field.set_active_id(r[0])
        refill_ops(r[1])
        k = kind()
        if k == "rating":
            rating.set_active_id(str(int(r[2] or 0)) if len(r) > 2 else "0")
            if rating.get_active_id() is None:
                rating.set_active(0)
        elif len(r) > 2:
            v1.set_text("" if r[2] is None else (time.strftime("%Y-%m-%d", time.localtime(r[2]))
                                                  if k == "date" and r[1] in ("is after", "is before") else str(r[2])))
        if len(r) > 3:
            if k == "date":
                unit.set_active_id(r[3])
            else:
                v2.set_text(str(r[3]))
        if unit.get_active_id() is None:
            unit.set_active_id("days")
        if after is not None and after in self.rule_rows:
            i = self.rule_rows.index(after) + 1
            self.rule_rows.insert(i, rec)
        else:
            self.rule_rows.append(rec)
        self.rules_box.pack_start(row, False, False, 0)
        self.rules_box.reorder_child(row, self.rule_rows.index(rec))
        row.show_all()
        show()
        return rec

    def remove_rule(self, rec):
        if len(self.rule_rows) <= 1:
            return
        self.rule_rows.remove(rec)
        self.rules_box.remove(rec["row"])

    def spec(self):
        rules = []
        for rec in self.rule_rows:
            col, o = rec["field"].get_active_id(), rec["op"].get_active_id()
            k = library.FIELD[col][1]
            if k == "text":
                rules.append([col, o, rec["v1"].get_text()])
            elif k == "number":
                def num(e):
                    try:
                        return float(e.get_text() or 0)
                    except ValueError:
                        return 0
                rules.append([col, o, num(rec["v1"])] + ([num(rec["v2"])] if o == "is in the range" else []))
            elif k == "rating":
                rules.append([col, o, int(rec["rating"].get_active_id() or 0)])
            elif k == "date":
                if o in ("is in the last", "is not in the last"):
                    try:
                        n = float(rec["v1"].get_text() or 0)
                    except ValueError:
                        n = 0
                    rules.append([col, o, n, rec["unit"].get_active_id() or "days"])
                else:
                    try:
                        t = time.mktime(time.strptime(rec["v1"].get_text().strip(), "%Y-%m-%d"))
                    except ValueError:
                        t = 0
                    rules.append([col, o, t])
            else:
                rules.append([col, o])
        out = {"name": self.name.get_text().strip() or "untitled playlist", "match": self.match.get_active_id(),
               "rules": rules if self.use_match.get_active() else [],
               "checked_only": self.checked.get_active()}
        if self.use_limit.get_active():
            out["limit"] = [self.limit_n.get_value_as_int(), self.limit_unit.get_active_id()]
            out["selected_by"] = self.sel_by.get_active_id()
        return out


def smart_playlist(win, spec):
    d = SmartDialog(win, spec)
    win.smart_dialog = d
    r = d.ask()
    out = d.spec() if r == Gtk.ResponseType.OK else None
    d.destroy()
    return out


# ================================================================ View Options
def view_options(win, columns):
    d = Dialog(win, "View Options")
    d.body.pack_start(lab("Show columns:", 0), False, False, 0)
    g = grid()
    checks = {}
    for i, (key, title, _i, _w, _s) in enumerate(views.COLS):
        c = Gtk.CheckButton(label=title or "Checkbox")
        c.set_active(key in columns)
        if key == "title":
            c.set_sensitive(False)
            c.set_active(True)
        checks[key] = c
        g.attach(c, i % 3, i // 3, 1, 1)
    d.body.pack_start(g, False, False, 0)
    d.checks = checks
    r = d.ask()
    out = [c[0] for c in views.COLS if checks[c[0]].get_active()] if r == Gtk.ResponseType.OK else None
    d.destroy()
    return out


# ================================================================ Options
class OptionsDialog(Dialog):
    def __init__(self, win):
        super().__init__(win, "Options")
        self.win = win
        s = self.s = win.settings
        self.set_default_size(560, 420)
        nb = Gtk.Notebook()
        self.body.pack_start(nb, True, True, 0)

        def page(title):
            b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            b.get_style_context().add_class("chord-page")
            b.set_border_width(10)
            nb.append_page(b, Gtk.Label(label=title))
            return b
        # ---- General
        g = page("General")
        g.pack_start(lab("Music folders (Folio Chord watches these):", 0), False, False, 0)
        self.folders = Gtk.ListStore(str)
        for f in s["music_folders"] or []:
            self.folders.append([f])
        fv = Gtk.TreeView(model=self.folders)
        fv.set_headers_visible(False)
        fv.append_column(Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=0))
        self.folder_view = fv
        sw = Gtk.ScrolledWindow()
        sw.set_size_request(-1, 90)
        sw.add(fv)
        g.pack_start(sw, False, False, 0)
        row = Gtk.Box(spacing=6)
        a = Gtk.Button(label="Add…")
        a.connect("clicked", lambda *_: self.add_folder())
        rm = Gtk.Button(label="Remove")
        rm.connect("clicked", lambda *_: self.remove_folder())
        row.pack_start(a, False, False, 0)
        row.pack_start(rm, False, False, 0)
        g.pack_start(row, False, False, 0)
        gr = grid()
        gr.attach(lab("When you insert a CD:"), 0, 0, 1, 1)
        self.cd_after = Gtk.ComboBoxText()
        for k, t in (("nothing", "Show the CD"), ("ask", "Ask to import the CD"), ("import", "Import the CD"),
                     ("import-eject", "Import the CD and eject")):
            self.cd_after.append(k, t)
        self.cd_after.set_active_id(s["cd_after_import"])
        gr.attach(self.cd_after, 1, 0, 2, 1)
        gr.attach(lab("Import using:"), 0, 1, 1, 1)
        self.fmt = Gtk.ComboBoxText()
        for f in cd.FORMATS:
            self.fmt.append(f, f + " Encoder" if f in ("AAC", "MP3") else f)
        self.fmt.set_active_id(s["import_format"])
        gr.attach(self.fmt, 1, 1, 1, 1)
        self.kbps = Gtk.ComboBoxText()
        for k in (128, 160, 192, 256, 320):
            self.kbps.append(str(k), "%d kbps" % k)
        self.kbps.set_active_id(str(s["import_kbps"]))
        gr.attach(self.kbps, 2, 1, 1, 1)
        g.pack_start(gr, False, False, 0)
        self.lookup = Gtk.CheckButton(label="Look up CD track names on the internet (MusicBrainz)")
        self.lookup.set_active(s["cd_lookup"])
        g.pack_start(self.lookup, False, False, 0)
        # ---- Playback
        p = page("Playback")
        cf = Gtk.Box(spacing=6)
        self.xfade = Gtk.CheckButton(label="Crossfade songs")
        self.xfade.set_active(s["crossfade"])
        self.xfade_s = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 12, 1)
        self.xfade_s.set_value(s["crossfade_secs"])
        self.xfade_s.set_size_request(220, -1)
        self.xfade_s.set_digits(0)
        cf.pack_start(self.xfade, False, False, 0)
        cf.pack_start(self.xfade_s, False, False, 0)
        cf.pack_start(lab("seconds", 0), False, False, 0)
        p.pack_start(cf, False, False, 0)
        self.sc = Gtk.CheckButton(label="Sound Check (plays songs at the same volume, from their ReplayGain)")
        self.sc.set_active(s["sound_check"])
        p.pack_start(self.sc, False, False, 0)
        # ---- Podcasts
        q = page("Podcasts")
        gq = grid()
        gq.attach(lab("Check for new episodes:"), 0, 0, 1, 1)
        self.refresh = Gtk.ComboBoxText()
        for k, t in (("hour", "Every hour"), ("day", "Every day"), ("week", "Every week"), ("manual", "Manually")):
            self.refresh.append(k, t)
        self.refresh.set_active_id(s["podcast_refresh"])
        gq.attach(self.refresh, 1, 0, 1, 1)
        gq.attach(lab("When new episodes are available:"), 0, 1, 1, 1)
        self.new = Gtk.ComboBoxText()
        for k, t in (("recent", "Download the most recent one"), ("all", "Download all"), ("nothing", "Do nothing")):
            self.new.append(k, t)
        self.new.set_active_id(s["podcast_new"])
        gq.attach(self.new, 1, 1, 1, 1)
        gq.attach(lab("Keep:"), 0, 2, 1, 1)
        self.keep = Gtk.ComboBoxText()
        for k, t in (("all", "All episodes"), ("unplayed", "All unplayed episodes"), ("recent", "Most recent episode")):
            self.keep.append(k, t)
        self.keep.set_active_id(s["podcast_keep"])
        gq.attach(self.keep, 1, 2, 1, 1)
        q.pack_start(gq, False, False, 0)
        q.pack_start(lab("Podcast directory:", 0), False, False, 0)
        self.dir_apple = Gtk.RadioButton.new_with_label(None, "Apple's podcast directory (no sign-in; the shows MusicPod finds)")
        self.dir_pi = Gtk.RadioButton.new_with_label_from_widget(self.dir_apple, "Podcast Index (needs a free API key from podcastindex.org)")
        (self.dir_pi if s["podcast_directory"] == "podcastindex" else self.dir_apple).set_active(True)
        q.pack_start(self.dir_apple, False, False, 0)
        q.pack_start(self.dir_pi, False, False, 0)
        gk = grid()
        self.pi_key = Gtk.Entry(text=s["podcastindex_key"], width_chars=30)
        self.pi_secret = Gtk.Entry(text=s["podcastindex_secret"], width_chars=30)
        self.pi_secret.set_visibility(False)
        gk.attach(lab("API key"), 0, 0, 1, 1)
        gk.attach(self.pi_key, 1, 0, 1, 1)
        gk.attach(lab("API secret"), 0, 1, 1, 1)
        gk.attach(self.pi_secret, 1, 1, 1, 1)
        q.pack_start(gk, False, False, 0)
        # ---- Advanced
        a = page("Advanced")
        a.pack_start(lab("Media folder (imported CDs and podcast downloads go here):", 0), False, False, 0)
        mr = Gtk.Box(spacing=6)
        self.media = Gtk.Entry(text=win.app.media_folder())
        self.media.set_hexpand(True)
        ch = Gtk.Button(label="Change…")
        ch.connect("clicked", lambda *_: self._media())
        mr.pack_start(self.media, True, True, 0)
        mr.pack_start(ch, False, False, 0)
        a.pack_start(mr, False, False, 0)
        self.copy = Gtk.CheckButton(label="Copy files to the media folder when adding them to the library")
        self.copy.set_active(s["copy_to_media"])
        a.pack_start(self.copy, False, False, 0)
        self.nb = nb

    def add_folder(self):
        f = choose_folder(self, "Add Music Folder")
        if f:
            self.folders.append([f])

    def remove_folder(self):
        model, it = self.folder_view.get_selection().get_selected()
        if it:
            model.remove(it)

    def _media(self):
        f = choose_folder(self, "Media Folder")
        if f:
            self.media.set_text(f)

    def apply(self):
        s, win = self.s, self.win
        old = set(s["music_folders"] or [])
        new = [r[0] for r in self.folders]
        s["music_folders"] = new
        for f in old - set(new):
            win.lib.remove_folder(f)
        for f in new:
            win.lib.add_folder(f)
        s["cd_after_import"] = self.cd_after.get_active_id()
        s["import_format"] = self.fmt.get_active_id()
        s["import_kbps"] = int(self.kbps.get_active_id() or 256)
        s["cd_lookup"] = self.lookup.get_active()
        s["crossfade"] = self.xfade.get_active()
        s["crossfade_secs"] = int(self.xfade_s.get_value())
        s["sound_check"] = self.sc.get_active()
        s["podcast_refresh"] = self.refresh.get_active_id()
        s["podcast_new"] = self.new.get_active_id()
        s["podcast_keep"] = self.keep.get_active_id()
        s["podcast_directory"] = "podcastindex" if self.dir_pi.get_active() else "apple"
        s["podcastindex_key"] = self.pi_key.get_text().strip()
        s["podcastindex_secret"] = self.pi_secret.get_text().strip()
        s["media_folder"] = self.media.get_text().strip() or None
        s["copy_to_media"] = self.copy.get_active()
        s.save()
        pb = win.app.playback
        pb.engine.crossfade = float(s["crossfade_secs"]) if s["crossfade"] else 0.0
        pb.engine.set_sound_check(s["sound_check"])
        if old != set(new):
            win.rescan()


def options(win):
    d = OptionsDialog(win)
    win.options_dialog = d
    r = d.ask()
    if r == Gtk.ResponseType.OK:
        d.apply()
    d.destroy()
    return r == Gtk.ResponseType.OK


def podcast_settings(win, pid):
    p = win.pods.show(pid)
    d = Dialog(win, "Podcast Settings")
    d.body.pack_start(lab(p["title"], 0), False, False, 0)
    auto = Gtk.CheckButton(label="Download new episodes automatically")
    auto.set_active(bool(p["auto_download"]))
    d.body.pack_start(auto, False, False, 0)
    d.body.pack_start(lab("Feed: " + p["feed"], 0, True), False, False, 0)
    d.auto = auto
    r = d.ask()
    if r == Gtk.ResponseType.OK:
        win.pods.set_auto_download(pid, auto.get_active())
    d.destroy()
    return r == Gtk.ResponseType.OK


# ================================================================ CDs and conversions
class Progress(Dialog):
    def __init__(self, win, title):
        super().__init__(win, title, (("Stop", Gtk.ResponseType.CANCEL),))
        self.label = Gtk.Label(xalign=0)
        self.label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.label.set_width_chars(50)
        self.bar = Gtk.ProgressBar()
        self.body.pack_start(self.label, False, False, 0)
        self.body.pack_start(self.bar, False, False, 0)
        self.stopped = False
        self.connect("response", lambda *_: setattr(self, "stopped", True))

    def set(self, text, frac):
        self.label.set_text(text)
        self.bar.set_fraction(max(0.0, min(1.0, frac)))


def _work(win, title, job):
    """Run job(report, stopped) on a thread with a progress window; returns its result."""
    d = Progress(win, title)
    d.show_all()
    out = {}

    def report(text, frac):
        GLib.idle_add(lambda: (d.set(text, frac), win.lcd.set_busy(text, frac), False)[2])

    def run():
        try:
            out["result"] = job(report, lambda: d.stopped)
        except Exception as e:      # noqa: BLE001
            out["error"] = e
        GLib.idle_add(lambda: (d.destroy(), False)[1])
    t = threading.Thread(target=run, daemon=True)
    t.start()
    while t.is_alive():
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.01)
    win.lcd.set_busy(None)
    if "error" in out:
        message(win, "%s didn't finish: %s" % (title, out["error"]))
        return None
    return out.get("result")


def import_cd(win):
    info = win.cd_info
    which = [r[1] for r in win.cd_store if r[0]] if len(win.cd_store) else list(range(1, len(info["lengths"]) + 1))
    s = win.settings
    fmt, kbps = s["import_format"], s["import_kbps"]
    folder = win.app.media_folder()

    def job(report, stopped):
        made = []
        for i, n in enumerate(which):
            if stopped():
                break
            t = info["tracks"][n - 1] if n <= len(info["tracks"]) else {}
            name = t.get("title") or "Track %d" % n
            dest = cd.dest_path(folder, info, n, fmt)
            report("Importing “%s”" % name, i / len(which))
            p = cd.rip(win.cd_device, n, dest, fmt, kbps,
                       progress=lambda f, i=i: report("Importing “%s”" % name, (i + f) / len(which)), stop=stopped)
            if p:
                cd.tag_ripped(p, info, n)
                made.append(p)
        return made
    made = _work(win, "Importing CD", job) or []
    if made:
        if folder not in (s["music_folders"] or []):
            s.set("music_folders", (s["music_folders"] or []) + [folder])
            win.lib.add_folder(folder)
        for p in made:
            win.lib.add_file(p)
        win.lib.changed()
    if s["cd_after_import"] == "import-eject":
        win.run("eject")
    return made


def burn(win, name, rows):
    total = sum(r["duration"] or 0 for r in rows)
    d = Dialog(win, "Burn Settings", (("Cancel", Gtk.ResponseType.CANCEL), ("Burn", Gtk.ResponseType.OK)))
    d.body.pack_start(lab("“%s”: %d songs, %s" % (name, len(rows), views.fmt_time(total)), 0), False, False, 0)
    drives = cd.drives()
    dev = Gtk.ComboBoxText()
    for x in drives:
        dev.append(x, x)
    dev.set_active(0)
    g = grid()
    g.attach(lab("CD Burner"), 0, 0, 1, 1)
    g.attach(dev, 1, 0, 1, 1)
    audio = Gtk.RadioButton.new_with_label(None, "Audio CD")
    data = Gtk.RadioButton.new_with_label_from_widget(audio, "Data CD (the files themselves)")
    (data if win.settings["burn_kind"] == "data" else audio).set_active(True)
    g.attach(lab("Disc Format"), 0, 1, 1, 1)
    g.attach(audio, 1, 1, 1, 1)
    g.attach(data, 1, 2, 1, 1)
    gap = Gtk.ComboBoxText()
    for k in (0, 1, 2, 3, 4, 5):
        gap.append(str(k), "none" if k == 0 else "%d second%s" % (k, "" if k == 1 else "s"))
    gap.set_active_id(str(win.settings["burn_gap"]))
    g.attach(lab("Gap Between Songs"), 0, 3, 1, 1)
    g.attach(gap, 1, 3, 1, 1)
    d.body.pack_start(g, False, False, 0)
    warn = Gtk.Label(xalign=0)
    if not cd.burner():
        warn.set_text("Burning needs wodim: sudo apt install wodim")
    elif not drives:
        warn.set_text("No CD burner was found.")
    elif not cd.fits(total):
        warn.set_text("These songs are longer than an 80-minute CD.")
    d.body.pack_start(warn, False, False, 0)
    d.dev, d.audio, d.data, d.gap = dev, audio, data, gap
    r = d.ask()
    kind = "audio" if audio.get_active() else "data"
    gp = int(gap.get_active_id() or 0)
    device = dev.get_active_id()
    d.destroy()
    if r != Gtk.ResponseType.OK:
        return None
    if not device or not cd.burner():
        message(win, warn.get_text() or "No CD burner was found.")
        return None
    if kind == "audio" and not cd.fits(total):
        message(win, "These songs don't fit on an audio CD (80 minutes). Make a shorter playlist, or burn a data CD.")
        return None
    win.settings.set("burn_kind", kind)
    win.settings.set("burn_gap", gp)
    log = []
    code = _work(win, "Burning", lambda report, stopped: cd.burn([r["path"] for r in rows], device.replace("fake:", ""), kind, gp,
                                                                  progress=report, log=log))
    win.burn_log = log
    if code == 0:
        message(win, "“%s” was burned." % name)
    elif code is not None:
        message(win, "The disc couldn't be burned:\n" + ("".join(log)[-600:] or "the burner gave no reason."))
    return code


def convert(win, rows, fmt):
    kbps = win.settings["import_kbps"]
    ext = cd.FORMATS[fmt][0]

    def job(report, stopped):
        made = []
        for i, r in enumerate(rows):
            if stopped():
                break
            base = os.path.splitext(r["path"])[0]
            dest = base + ext
            if os.path.abspath(dest) == os.path.abspath(r["path"]):
                dest = base + " 1" + ext
            report("Converting “%s”" % r["title"], i / len(rows))
            import gi
            gi.require_version("Gst", "1.0")
            from gi.repository import Gst
            pipe = Gst.parse_launch("uridecodebin name=d ! audioconvert ! audioresample ! %s ! filesink name=out"
                                    % cd.FORMATS[fmt][1].format(kbps=kbps))
            pipe.get_by_name("d").set_property("uri", Gst.filename_to_uri(r["path"]))
            pipe.get_by_name("out").set_property("location", dest)
            pipe.set_state(Gst.State.PLAYING)
            m = pipe.get_bus().timed_pop_filtered(3600 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
            pipe.set_state(Gst.State.NULL)
            if m is None or m.type == Gst.MessageType.ERROR:
                raise RuntimeError("“%s” couldn't be converted" % r["title"])
            t = tags.read(r["path"])
            tags.write(dest, {k: t[k] for k in tags.FIELDS})
            a = tags.artwork(r["path"])
            if a:
                tags.set_artwork(dest, a[0], a[1])
            made.append(dest)
        return made
    made = _work(win, "Create %s Version" % fmt, job) or []
    for p in made:
        win.lib.add_file(p)
    win.lib.changed()
    return made


# ================================================================ Help
SHORTCUTS = [("Play or pause", "Space"), ("Next song", "Ctrl+Right"), ("Previous song", "Ctrl+Left"),
             ("Stop", "Ctrl+."), ("Volume up / down", "Ctrl+Up / Ctrl+Down"), ("Mute", "Ctrl+Alt+Down"),
             ("Shuffle on or off", "Ctrl+S"), ("Go to the current song", "Ctrl+L"), ("Get Info", "Ctrl+I"),
             ("New playlist", "Ctrl+N"), ("New playlist from selection", "Ctrl+Shift+N"),
             ("New Smart Playlist", "Ctrl+Alt+N"), ("Add file to library", "Ctrl+O"), ("Search", "Ctrl+F"),
             ("Column browser", "Ctrl+B"), ("Artwork", "Ctrl+G"), ("Visualizer", "Ctrl+T"),
             ("Mini Player", "Ctrl+Shift+M"), ("Equalizer", "Ctrl+Alt+E"), ("Open stream", "Ctrl+U"),
             ("View as list / album list / grid", "Ctrl+Alt+3 / 4 / 5"), ("Options", "Ctrl+,"), ("Eject disc", "Ctrl+E"),
             ("Delete", "Delete"), ("Rename a playlist", "F2 or double-click")]


def shortcuts(win):
    d = Dialog(win, "Keyboard Shortcuts", (("Close", Gtk.ResponseType.CLOSE),))
    g = grid()
    for i, (what, keys) in enumerate(SHORTCUTS):
        g.attach(lab(what, 0), 0, i, 1, 1)
        k = Gtk.Label(xalign=0)
        k.set_markup("<b>%s</b>" % GLib.markup_escape_text(keys))
        g.attach(k, 1, i, 1, 1)
    sw = Gtk.ScrolledWindow()
    sw.set_size_request(420, 420)
    sw.add(g)
    d.body.pack_start(sw, True, True, 0)
    d.ask()
    d.destroy()
    return len(SHORTCUTS)


def about(win, version):
    d = Dialog(win, "About Folio Chord", (("Close", Gtk.ResponseType.CLOSE),))
    img = Gtk.Image.new_from_icon_name("folio-chord", Gtk.IconSize.DIALOG)
    img.set_pixel_size(96)
    d.body.pack_start(img, False, False, 0)
    t = Gtk.Label()
    t.set_markup("<big><b>%s</b></big>\nVersion %s" % (APP_NAME, version))
    t.set_justify(Gtk.Justification.CENTER)
    d.body.pack_start(t, False, False, 0)
    x = Gtk.Label(label="Music, internet radio and podcasts.\nStations from radio-browser.info; podcasts from Apple's "
                        "public podcast directory or Podcast Index;\nCD track names from MusicBrainz. Nothing else leaves "
                        "this computer.")
    x.set_justify(Gtk.Justification.CENTER)
    x.get_style_context().add_class("chord-dim")
    d.body.pack_start(x, False, False, 0)
    d.ask()
    d.destroy()
    return version


__all__ = ["message", "confirm", "choose", "ask_text", "get_info", "smart_playlist", "view_options", "options",
           "import_cd", "burn", "convert", "shortcuts", "about", "json"]
