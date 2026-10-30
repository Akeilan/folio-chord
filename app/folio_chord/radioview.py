"""Internet radio in the window (C3-05): favourites, recently played, the most popular stations,
and stations by genre, country and language from radio-browser.info; search by name."""
from gi.repository import GLib, Gtk, Pango

from . import net, radio


class RadioView(Gtk.Paned):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.lib = win.lib
        self.dir = win.app.radio
        self.stations = []
        self._seq = 0
        self._loaded_lists = False
        #                          label, kind, value, header
        self.cat_store = Gtk.TreeStore(str, str, str, bool)
        cv = Gtk.TreeView(model=self.cat_store)
        cv.set_headers_visible(False)
        cv.get_style_context().add_class("chord-browse")
        r = Gtk.CellRendererText()
        r.set_property("ellipsize", Pango.EllipsizeMode.END)
        col = Gtk.TreeViewColumn("", r, text=0)
        col.set_cell_data_func(r, self._cat_cell)
        cv.append_column(col)
        cv.get_selection().set_select_function(lambda s, m, p, c: not m[p][3])
        cv.get_selection().connect("changed", lambda s: self._category())
        self.cat_view = cv
        sw = Gtk.ScrolledWindow()
        sw.set_size_request(210, -1)
        sw.add(cv)
        self.pack1(sw, False, False)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        bar = Gtk.Box(spacing=6)
        bar.get_style_context().add_class("chord-sectionbar")
        self.heading = Gtk.Label(label="Radio", xalign=0)
        self.heading.get_style_context().add_class("chord-heading")
        bar.pack_start(self.heading, True, True, 0)
        self.fav_btn = Gtk.Button(label="Add to Favourites")
        self.fav_btn.get_style_context().add_class("chord-button")
        self.fav_btn.connect("clicked", lambda *_: self.toggle_favourite())
        bar.pack_end(self.fav_btn, False, False, 0)
        right.pack_start(bar, False, False, 0)
        #                         fav, name, genre, country, bitrate, index
        self.store = Gtk.ListStore(str, str, str, str, str, int)
        v = Gtk.TreeView(model=self.store)
        for title, i, w in (("", 0, 26), ("Station", 1, 300), ("Genre", 2, 220), ("Country", 3, 150), ("Bit Rate", 4, 80)):
            rr = Gtk.CellRendererText()
            rr.set_property("ellipsize", Pango.EllipsizeMode.END)
            c = Gtk.TreeViewColumn(title, rr, text=i)
            c.set_fixed_width(w)
            c.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            c.set_resizable(True)
            v.append_column(c)
        v.append_column(Gtk.TreeViewColumn(""))
        v.connect("row-activated", lambda vv, p, c: self.play_selected())
        v.connect("button-press-event", self._press)
        v.get_selection().connect("changed", lambda s: self._sync_fav())
        self.view = v
        sw2 = Gtk.ScrolledWindow()
        sw2.add(v)
        right.pack_start(sw2, True, True, 0)
        self.hint = Gtk.Label(xalign=0)
        self.hint.get_style_context().add_class("chord-dim")
        self.hint.set_margin_start(8)
        self.hint.set_margin_bottom(4)
        self.hint.set_text("Stations from radio-browser.info, the community radio directory.")
        right.pack_start(self.hint, False, False, 0)
        self.pack2(right, True, False)
        self.set_position(210)
        self._fill_categories()

    def _cat_cell(self, col, cell, model, it, d=None):
        from . import theme
        c = theme.colours(self.win.dark)
        if model[it][3]:
            cell.set_property("markup", "<small><b>%s</b></small>" % GLib.markup_escape_text(model[it][0]))
            cell.set_property("foreground", c["src_head"])
        else:
            cell.set_property("text", model[it][0])
            sel = self.cat_view.get_selection().iter_is_selected(it)
            cell.set_property("foreground", c["sel_fg"] if sel else c["list_fg"])

    def _fill_categories(self):
        s = self.cat_store
        s.clear()
        s.append(None, ["MY STATIONS", "", "", True])
        s.append(None, ["Favourites", "favourites", "", False])
        s.append(None, ["Recently Played", "recent", "", False])
        s.append(None, ["DIRECTORY", "", "", True])
        s.append(None, ["Most Popular", "top", "", False])
        self.genres = s.append(None, ["By Genre", "", "", True])
        self.countries = s.append(None, ["By Country", "", "", True])
        self.languages = s.append(None, ["By Language", "", "", True])

    def refresh(self):
        if not self._loaded_lists:
            self._loaded_lists = True

            def work():
                return self.dir.tags(60), self.dir.countries(120), self.dir.languages(60)

            def done(res):
                tags, countries, langs = res
                for name, n, _cc in tags:
                    self.cat_store.append(self.genres, [name.capitalize(), "tag", name, False])
                for name, n, cc in countries:
                    self.cat_store.append(self.countries, [name, "country", cc or name, False])
                for name, n, _cc in langs:
                    self.cat_store.append(self.languages, [name.capitalize(), "language", name, False])
                self.cat_view.expand_all()

            def fail(e):
                self._loaded_lists = False
                self.hint.set_text("The radio directory couldn't be reached: %s" % e)
            net.in_thread(work, done, fail)
        model, it = self.cat_view.get_selection().get_selected()
        if it is None:
            self.cat_view.get_selection().select_path(Gtk.TreePath.new_from_indices([1 if radio.favourites(self.lib) else 4]))
        else:
            self._category()

    def _category(self):
        model, it = self.cat_view.get_selection().get_selected()
        if it is None:
            return
        kind, val, label = model[it][1], model[it][2], model[it][0]
        self.heading.set_text(label)
        if kind == "favourites":
            self.set_stations(radio.favourites(self.lib))
        elif kind == "recent":
            self.set_stations(radio.recent(self.lib))
        elif kind == "top":
            self._load(lambda: self.dir.top(100))
        elif kind == "tag":
            self._load(lambda: self.dir.search(tag=val, limit=200))
        elif kind == "country":
            self._load(lambda: self.dir.search(countrycode=val, limit=200) if len(val) == 2 else self.dir.search(country=val, limit=200))
        elif kind == "language":
            self._load(lambda: self.dir.search(language=val, limit=200))

    def search(self, q):
        if not q:
            self._category()
            return
        self.heading.set_text("Stations matching “%s”" % q)
        self._load(lambda: self.dir.search(name=q, limit=200))

    def _load(self, fn):
        self._seq += 1
        seq = self._seq
        self.store.clear()
        self.hint.set_text("Looking…")

        def done(st):
            if seq == self._seq:
                self.set_stations(st)

        def fail(e):
            if seq == self._seq:
                self.hint.set_text("The radio directory couldn't be reached: %s" % e)
        net.in_thread(fn, done, fail)

    def set_stations(self, stations):
        keep = {x["uuid"] for x in self.selected()}
        self.stations = list(stations)
        self.store.clear()
        favs = {f["uuid"] for f in radio.favourites(self.lib)}
        for i, s in enumerate(self.stations):
            self.store.append(["♥" if s["uuid"] in favs else "", s["name"], ", ".join(s.get("tags", [])[:4]),
                               s.get("country", ""), "%d kbps" % s["bitrate"] if s.get("bitrate") else "", i])
        for row in self.store:
            if self.stations[row[5]]["uuid"] in keep:
                self.view.get_selection().select_path(row.path)
        self.hint.set_text("%d stations from radio-browser.info." % len(self.stations))
        self.win.update_status()
        self._sync_fav()

    def status_text(self):
        return "%d stations" % len(self.stations)

    def selected(self):
        model, paths = self.view.get_selection().get_selected_rows()
        return [self.stations[model[p][5]] for p in paths]

    def play_selected(self):
        s = self.selected()
        if s:
            self.win.app.playback.play_station(s[0])
            return s[0]
        return None

    def toggle_favourite(self):
        s = self.selected()
        if not s:
            return None
        on = not radio.is_favourite(self.lib, s[0])
        radio.set_favourite(self.lib, s[0], on)
        self.set_stations(self.stations)
        return on

    def remove_selected(self):
        s = self.selected()
        model, it = self.cat_view.get_selection().get_selected()
        if s and it is not None and model[it][1] == "favourites":
            for x in s:
                radio.set_favourite(self.lib, x, False)
            self.set_stations(radio.favourites(self.lib))
        return s

    def _sync_fav(self):
        s = self.selected()
        self.fav_btn.set_sensitive(bool(s))
        self.fav_btn.set_label("Remove from Favourites" if s and radio.is_favourite(self.lib, s[0]) else "Add to Favourites")

    def _press(self, v, ev):
        if ev.button != 3:
            return False
        hit = v.get_path_at_pos(int(ev.x), int(ev.y))
        if hit:
            v.get_selection().select_path(hit[0])
        s = self.selected()
        if not s:
            return True
        self.win.popup([("Play", "radio:play"), ("Remove from Favourites" if radio.is_favourite(self.lib, s[0]) else "Add to Favourites",
                                                 "radio:favourite"), ("Copy Stream Address", "radio:copy"),
                        ("Open Station Web Page", "radio:web")], ev)
        return True

    def act(self, what):
        s = self.selected()
        if what == "play":
            return self.play_selected()
        if what == "favourite":
            return self.toggle_favourite()
        if what == "copy" and s:
            from gi.repository import Gdk
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(s[0]["url"], -1)
            return s[0]["url"]
        if what == "web" and s and s[0].get("homepage"):
            import os
            if not os.environ.get("FOLIO_TEST_SCRIPT"):
                Gtk.show_uri_on_window(self.win, s[0]["homepage"], 0)
            return s[0]["homepage"]
        return None
