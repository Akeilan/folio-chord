"""Podcasts in the window (C3-06): your shows on the left, their episodes on the right, and the
Podcast Directory (search, and the charts by country and category) to find new ones."""
import os
import time

from gi.repository import GdkPixbuf, GLib, Gtk, Pango

from . import art, net, podcasts as P, views


class PodcastsView(Gtk.Box):
    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = win
        self.pods = win.pods
        self.settings = win.settings
        self.downloading = {}
        self.query = ""
        bar = Gtk.Box(spacing=6)
        bar.get_style_context().add_class("chord-sectionbar")
        self.heading = Gtk.Label(label="Podcasts", xalign=0)
        self.heading.get_style_context().add_class("chord-heading")
        bar.pack_start(self.heading, True, True, 0)
        self.btn = {}
        for key, label in (("directory", "Podcast Directory"), ("refresh", "Refresh"), ("settings", "Settings…"),
                           ("unsubscribe", "Unsubscribe")):
            b = Gtk.Button(label=label) if key != "directory" else Gtk.ToggleButton(label=label)
            b.get_style_context().add_class("chord-button")
            if key == "directory":
                b.connect("toggled", lambda w: self.show_directory(w.get_active()))
            else:
                b.connect("clicked", lambda _b, k=key: getattr(self, "on_" + k)())
            self.btn[key] = b
        for key in ("unsubscribe", "settings", "refresh", "directory"):
            bar.pack_end(self.btn[key], False, False, 0)
        self.pack_start(bar, False, False, 0)
        self.stack = Gtk.Stack()
        self.pack_start(self.stack, True, True, 0)
        # ---- your shows
        paned = Gtk.Paned()
        self.show_store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, int, str)     # art, markup, id, badge
        sv = Gtk.TreeView(model=self.show_store)
        sv.set_headers_visible(False)
        c = Gtk.TreeViewColumn()
        pr = Gtk.CellRendererPixbuf()
        c.pack_start(pr, False)
        c.add_attribute(pr, "pixbuf", 0)
        tr = Gtk.CellRendererText()
        tr.set_property("ellipsize", Pango.EllipsizeMode.END)
        c.pack_start(tr, True)
        c.add_attribute(tr, "markup", 1)
        br = Gtk.CellRendererText()
        c.pack_end(br, False)
        c.set_cell_data_func(br, self._badge)
        sv.append_column(c)
        sv.get_selection().connect("changed", lambda s: self.fill_episodes())
        sv.connect("button-press-event", self._show_press)
        self.show_view = sv
        sw = Gtk.ScrolledWindow()
        sw.set_size_request(260, -1)
        sw.add(sv)
        paned.pack1(sw, False, False)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        #                            id, new dot, title, time, date, status, played(bool), description
        self.ep_store = Gtk.ListStore(int, str, str, str, str, str, bool, str, float)
        ev = Gtk.TreeView(model=self.ep_store)
        ev.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        for title, i, w in (("", 1, 22), ("Name", 2, 320), ("Time", 3, 60), ("Release Date", 4, 110), ("", 5, 110)):
            r = Gtk.CellRendererText()
            r.set_property("ellipsize", Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title, r, text=i)
            col.set_fixed_width(w)
            col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            col.set_cell_data_func(r, self._ep_cell, i)
            if i == 4:
                col.set_sort_column_id(8)
            ev.append_column(col)
        ev.append_column(Gtk.TreeViewColumn(""))
        ev.connect("row-activated", lambda v, p, c: self.play_selected())
        ev.connect("button-press-event", self._ep_press)
        ev.get_selection().connect("changed", lambda s: self._notes())
        self.ep_view = ev
        sw2 = Gtk.ScrolledWindow()
        sw2.add(ev)
        right.pack_start(sw2, True, True, 0)
        self.notes = Gtk.TextView()
        self.notes.set_editable(False)
        self.notes.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.notes.set_left_margin(8)
        self.notes.set_right_margin(8)
        self.notes.get_style_context().add_class("chord-notes")
        sw3 = Gtk.ScrolledWindow()
        sw3.set_size_request(-1, 110)
        sw3.add(self.notes)
        right.pack_start(sw3, False, False, 0)
        paned.pack2(right, True, False)
        self.stack.add_named(paned, "mine")
        self.empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.empty.set_valign(Gtk.Align.CENTER)
        l1 = Gtk.Label(label="No podcasts yet")
        l1.get_style_context().add_class("chord-heading")
        l2 = Gtk.Label(label="Find shows in the Podcast Directory, or subscribe to one by its address.")
        l2.get_style_context().add_class("chord-dim")
        b = Gtk.Button(label="Podcast Directory")
        b.get_style_context().add_class("chord-default")
        b.set_halign(Gtk.Align.CENTER)
        b.connect("clicked", lambda *_: self.btn["directory"].set_active(True))
        for w in (l1, l2, b):
            self.empty.pack_start(w, False, False, 0)
        self.stack.add_named(self.empty, "empty")
        # ---- the directory
        d = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        row = Gtk.Box(spacing=8)
        row.set_border_width(8)
        self.dir_label = Gtk.Label(xalign=0)
        self.dir_label.get_style_context().add_class("chord-heading")
        row.pack_start(self.dir_label, True, True, 0)
        self.country = Gtk.ComboBoxText()
        for name, cc in P.COUNTRIES:
            self.country.append(cc, name)
        from .app import default_country
        cc = self.settings.get("podcast_country") or default_country()
        if not self.country.set_active_id(cc):
            self.country.set_active_id("us")
        self.country.connect("changed", lambda c: self._charts())
        self.genre = Gtk.ComboBoxText()
        for name, gid in P.GENRES:
            self.genre.append(str(gid), name)
        self.genre.set_active(0)
        self.genre.connect("changed", lambda c: self._charts())
        row.pack_end(self.genre, False, False, 0)
        row.pack_end(self.country, False, False, 0)
        d.pack_start(row, False, False, 0)
        self.dir_store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, object, str)    # art, markup, show dict, subscribed
        dv = Gtk.TreeView(model=self.dir_store)
        dv.set_headers_visible(False)
        c = Gtk.TreeViewColumn()
        pr = Gtk.CellRendererPixbuf()
        c.pack_start(pr, False)
        c.add_attribute(pr, "pixbuf", 0)
        tr = Gtk.CellRendererText()
        tr.set_property("ellipsize", Pango.EllipsizeMode.END)
        tr.set_property("wrap-width", 520)
        c.pack_start(tr, True)
        c.add_attribute(tr, "markup", 1)
        sr = Gtk.CellRendererText()
        c.pack_end(sr, False)
        c.add_attribute(sr, "text", 3)
        dv.append_column(c)
        dv.connect("row-activated", lambda v, p, c: self.subscribe_row(p))
        self.dir_view = dv
        sw4 = Gtk.ScrolledWindow()
        sw4.add(dv)
        d.pack_start(sw4, True, True, 0)
        hint = Gtk.Label(xalign=0)
        hint.set_margin_start(8)
        hint.set_margin_bottom(4)
        hint.get_style_context().add_class("chord-dim")
        self.dir_hint = hint
        d.pack_start(hint, False, False, 0)
        self.stack.add_named(d, "directory")
        self._dir_seq = 0
        self._charted = None

    # ---------------------------------------------------------------- cells
    def _badge(self, col, cell, model, it, d=None):
        from . import theme
        t = model[it][3]
        c = theme.colours(self.win.dark)
        cell.set_property("visible", bool(t))
        if t:
            cell.set_property("markup", "<small><b> %s </b></small>" % t)
            cell.set_property("foreground", c["badge_fg"])
            cell.set_property("background", c["badge"])

    def _ep_cell(self, col, cell, model, it, i):
        from . import theme
        c = theme.colours(self.win.dark)
        sel = self.ep_view.get_selection().iter_is_selected(it)
        cell.set_property("foreground", c["sel_fg"] if sel else (c["dim"] if model[it][6] else c["list_fg"]))
        cell.set_property("weight", Pango.Weight.BOLD if i == 2 and not model[it][6] else Pango.Weight.NORMAL)

    # ---------------------------------------------------------------- your shows
    def refresh(self):
        sel = self.current_show()
        self._keep_eps = self.selected_episodes()
        self.show_store.clear()
        shows = self.pods.shows()
        ph = art.placeholder(40, self.win.dark)
        for p in shows:
            it = self.show_store.append([ph, "<b>%s</b>\n<small>%s</small>" % (GLib.markup_escape_text(p["title"] or ""),
                                                                                 GLib.markup_escape_text(p["author"] or "")),
                                         p["id"], str(p["unplayed"]) if p["unplayed"] else ""])
            path = self.show_store.get_path(it)
            art.for_url(p["artwork"], 40, lambda pb, path=path, pid=p["id"]: self._set_art(self.show_store, path, pb, pid))
        if not self.btn["directory"].get_active():
            self.stack.set_visible_child_name("mine" if shows else "empty")
        if shows:
            idx = next((i for i, r in enumerate(self.show_store) if r[2] == sel), 0)
            self.show_view.get_selection().select_path(Gtk.TreePath.new_from_indices([idx]))
        else:
            self.ep_store.clear()
        self.heading.set_text("Podcasts")
        self.win.update_status()

    def _set_art(self, store, path, pb, key):
        try:
            row = store[path]
        except (ValueError, IndexError):
            return
        if pb is not None and (row[2] == key if not isinstance(key, dict) else True):
            row[0] = pb

    def current_show(self):
        model, it = self.show_view.get_selection().get_selected()
        return model[it][2] if it else None

    def fill_episodes(self):
        pid = self.current_show()
        sel = self.selected_episodes() or getattr(self, "_keep_eps", [])
        self.ep_store.clear()
        if pid is None:
            return
        self._keep_eps = []
        q = self.query
        for e in self.pods.episodes(pid):
            if q and q not in (e["title"] or "").lower() and q not in P.plain(e["description"]).lower():
                continue
            self.ep_store.append([e["id"], "●" if not e["played"] and e["new"] else ("◐" if e["position"] and not e["played"] else ""),
                                  e["title"] or "", views.fmt_time(e["duration"]) if e["duration"] else "",
                                  time.strftime("%d %b %Y", time.localtime(e["published"])) if e["published"] else "",
                                  self._status(e), bool(e["played"]), e["description"] or "", e["published"] or 0])
        for row in self.ep_store:
            if row[0] in sel:
                self.ep_view.get_selection().select_path(row.path)
        self.win.update_status()

    def _status(self, e):
        if e["id"] in self.downloading:
            return "Downloading %d%%" % self.downloading[e["id"]]
        if e["file"] and os.path.exists(e["file"]):
            return "Downloaded"
        return "Stream"

    def selected_episodes(self):
        model, paths = self.ep_view.get_selection().get_selected_rows()
        return [model[p][0] for p in paths]

    def _notes(self):
        model, paths = self.ep_view.get_selection().get_selected_rows()
        self.notes.get_buffer().set_text(P.plain(model[paths[0]][7]) if paths else "")

    def search(self, q):
        self.query = q
        if self.btn["directory"].get_active():
            if q:
                self._search_dir(q)
            else:
                self._charts()
        else:
            self.fill_episodes()

    def status_text(self):
        if self.btn["directory"].get_active():
            return "%d shows" % len(self.dir_store)
        n = len(self.ep_store)
        unplayed = sum(1 for r in self.ep_store if not r[6])
        return "%d episodes, %d unplayed" % (n, unplayed)

    # ---------------------------------------------------------------- playing
    def play_selected(self):
        model, paths = self.ep_view.get_selection().get_selected_rows()
        if not paths:
            return None
        ids = [r[0] for r in self.ep_store]
        i = paths[0].get_indices()[0]
        self.win.app.playback.play_episodes(ids, i)
        GLib.timeout_add(500, lambda: (self.fill_episodes(), False)[1])
        return ids[i]

    def _ep_press(self, v, ev):
        if ev.button != 3:
            return False
        hit = v.get_path_at_pos(int(ev.x), int(ev.y))
        if hit and not v.get_selection().path_is_selected(hit[0]):
            v.get_selection().unselect_all()
            v.get_selection().select_path(hit[0])
        self.episode_menu(ev)
        return True

    def episode_menu(self, ev=None):
        items = [("Play", "pod:play"), ("Download Episode", "pod:download"), ("Remove Download", "pod:remove-download"),
                 None, ("Mark as Played", "pod:played"), ("Mark as Unplayed", "pod:unplayed"), None,
                 ("Episode Notes", "pod:info"), ("Open Episode Web Page", "pod:web")]
        return self.win.popup(items, ev)

    def _show_press(self, v, ev):
        if ev.button != 3:
            return False
        hit = v.get_path_at_pos(int(ev.x), int(ev.y))
        if hit:
            v.get_selection().select_path(hit[0])
        return self.win.popup([("Refresh", "pod:refresh"), ("Mark All as Played", "pod:all-played"),
                               ("Settings…", "pod:settings"), None, ("Unsubscribe", "pod:unsubscribe")], ev) is not None

    def act(self, what):
        eids = self.selected_episodes()
        if what == "play":
            return self.play_selected()
        if what == "download":
            for e in eids:
                self.download(e)
        elif what == "remove-download":
            for e in eids:
                self.pods.delete_download(e)
        elif what == "played":
            self.pods.mark_played(eids)
        elif what == "unplayed":
            self.pods.mark_played(eids, False)
        elif what == "all-played":
            pid = self.current_show()
            self.pods.mark_played([e["id"] for e in self.pods.episodes(pid)])
        elif what == "info":
            return self.info_selected()
        elif what == "web":
            e = self.pods.episode(eids[0]) if eids else None
            if e and e["link"] and not os.environ.get("FOLIO_TEST_SCRIPT"):
                Gtk.show_uri_on_window(self.win, e["link"], 0)
            return e["link"] if e else None
        elif what == "refresh":
            return self.on_refresh()
        elif what == "settings":
            return self.on_settings()
        elif what == "unsubscribe":
            return self.on_unsubscribe()
        self.refresh()
        return eids

    def info_selected(self):
        from . import dialogs
        eids = self.selected_episodes()
        if not eids:
            return None
        e = self.pods.episode(eids[0])
        p = self.pods.show(e["podcast"])
        return dialogs.message(self.win, P.plain(e["description"]) or "No notes.", "%s — %s" % (p["title"], e["title"]))

    def delete_selected(self):
        eids = self.selected_episodes()
        for e in eids:
            self.pods.delete_download(e)
        self.fill_episodes()
        return eids

    # ---------------------------------------------------------------- toolbar
    def on_refresh(self):
        pid = self.current_show()
        if pid is None:
            return self.refresh_all()
        self._refresh_ids([pid])

    def refresh_all(self):
        self._refresh_ids([p["id"] for p in self.pods.shows()])

    def _refresh_ids(self, ids):
        if not ids:
            return
        self.win.lcd.set_busy("Checking for new episodes…")

        def work():
            new = []
            for pid in ids:
                try:
                    new += self.pods.refresh(pid)
                except Exception:       # noqa: BLE001 — one show's feed failing doesn't stop the rest
                    pass
            return new

        def done(new):
            self.win.lcd.set_busy(None)
            self.after_refresh(new)
        net.in_thread(work, done, lambda e: self.win.lcd.set_busy(None))

    def after_refresh(self, new):
        mode = self.settings["podcast_new"]
        if mode != "nothing":
            for eid in self.pods.to_download():
                e = self.pods.episode(eid)
                if mode == "all" or e["id"] == (self.pods.episodes(e["podcast"])[0]["id"]):
                    self.download(eid)
        self._keep()
        self.win.fill_sources()
        if self.win.source[0] == "podcasts":
            self.refresh()

    def _keep(self):
        keep = self.settings["podcast_keep"]
        if keep == "all":
            return
        for p in self.pods.shows():
            eps = [e for e in self.pods.episodes(p["id"]) if e["file"]]
            for i, e in enumerate(eps):
                if keep == "unplayed" and e["played"] or keep == "recent" and i >= 1:
                    self.pods.delete_download(e["id"])

    def refresh_due(self):
        every = {"hour": 3600, "day": 86400, "week": 7 * 86400}.get(self.settings["podcast_refresh"])
        if not every:
            return
        due = [p["id"] for p in self.pods.shows() if time.time() - (p["refreshed"] or 0) >= every]
        if due:
            self._refresh_ids(due)

    def download(self, eid):
        if eid in self.downloading:
            return
        self.downloading[eid] = 0

        def prog(done, total):
            if total:
                pct = int(done * 100 / total)
                if pct != self.downloading.get(eid):
                    self.downloading[eid] = pct
                    GLib.idle_add(self._dl_progress, eid)

        def work():
            return self.pods.download(eid, prog)

        def done(path):
            self.downloading.pop(eid, None)
            self.fill_episodes()

        def fail(e):
            self.downloading.pop(eid, None)
            self.fill_episodes()
        net.in_thread(work, done, fail)
        self.fill_episodes()

    def _dl_progress(self, eid):
        for row in self.ep_store:
            if row[0] == eid:
                row[5] = "Downloading %d%%" % self.downloading.get(eid, 0)
        return False

    def on_settings(self):
        from . import dialogs
        pid = self.current_show()
        if pid is None:
            return None
        return dialogs.podcast_settings(self.win, pid)

    def on_unsubscribe(self):
        from . import dialogs
        pid = self.current_show()
        if pid is None:
            return None
        p = self.pods.show(pid)
        if dialogs.confirm(self.win, "Unsubscribe from “%s”?" % p["title"], "Its downloaded episodes are deleted.", "Unsubscribe"):
            self.pods.unsubscribe(pid)
            self.win.fill_sources()
            self.refresh()
            return pid
        return None

    def subscribe(self, url, quiet=False):
        self.win.lcd.set_busy("Subscribing…")

        def done(pid):
            self.win.lcd.set_busy(None)
            self.after_refresh([])
            self.btn["directory"].set_active(False)
            for row in self.show_store:
                if row[2] == pid:
                    self.show_view.get_selection().select_path(row.path)
            for eid in self.pods.to_download():
                if self.settings["podcast_new"] != "nothing" and self.pods.episode(eid)["podcast"] == pid:
                    self.download(eid)
            self._mark_subscribed()

        def fail(e):
            self.win.lcd.set_busy(None)
            if not quiet:
                self.win.info("That podcast couldn't be subscribed to: %s" % e)
        net.in_thread(lambda: self.pods.subscribe(url), done, fail)

    # ---------------------------------------------------------------- the directory
    def show_directory(self, on):
        if on:
            self.stack.set_visible_child_name("directory")
            d = P.directory(self.settings)
            self.dir_hint.set_text("From %s. Double-click a show to subscribe." % d.name)
            if self.query:
                self._search_dir(self.query)
            elif self._charted is None:
                self._charts()
        else:
            self.refresh()
        self.win.update_status()

    def _country(self):
        return self.country.get_active_id() or "us"

    def _charts(self):
        cc, gid = self._country(), int(self.genre.get_active_id() or 26)
        self.settings["podcast_country"] = cc
        self._charted = (cc, gid)
        self.dir_label.set_text("Top Podcasts — %s" % self.genre.get_active_text())
        d = P.directory(self.settings)
        self._dir_load(lambda: d.charts(cc, gid))

    def _search_dir(self, q):
        self.dir_label.set_text("Results for “%s”" % q)
        d = P.directory(self.settings)
        cc = self._country()
        self._dir_load(lambda: d.search(q, cc))

    def _dir_load(self, fn):
        self._dir_seq += 1
        seq = self._dir_seq
        self.dir_store.clear()
        self.dir_hint.set_text("Looking…")

        def done(shows):
            if seq != self._dir_seq:
                return
            self.fill_dir(shows)

        def fail(e):
            if seq != self._dir_seq:
                return
            self.dir_hint.set_text("The directory couldn't be reached: %s" % e)
        net.in_thread(fn, done, fail)

    def fill_dir(self, shows):
        self.dir_store.clear()
        subs = {p["feed"] for p in self.pods.shows()}
        ph = art.placeholder(56, self.win.dark)
        for s in shows:
            it = self.dir_store.append([ph, "<b>%s</b>\n%s\n<small>%s</small>" % (
                GLib.markup_escape_text(s["title"]), GLib.markup_escape_text(s["author"]),
                GLib.markup_escape_text(s["genre"] or "")), s, "Subscribed" if s["feed"] in subs else "Subscribe"])
            path = self.dir_store.get_path(it)
            art.for_url(s["artwork"], 56, lambda pb, path=path: self._set_dir_art(path, pb))
        d = P.directory(self.settings)
        self.dir_hint.set_text("%d shows from %s. Double-click a show to subscribe." % (len(shows), d.name))
        self.win.update_status()

    def _set_dir_art(self, path, pb):
        try:
            if pb is not None:
                self.dir_store[path][0] = pb
        except (ValueError, IndexError):
            pass

    def _mark_subscribed(self):
        subs = {p["feed"] for p in self.pods.shows()}
        for row in self.dir_store:
            row[3] = "Subscribed" if row[2]["feed"] in subs else "Subscribe"

    def subscribe_row(self, path):
        s = self.dir_store[path][2]
        if s["feed"] in {p["feed"] for p in self.pods.shows()}:
            return None
        self.subscribe(s["feed"])
        return s["feed"]
