"""The Folio Chord window (C3-08): menu bar, the top bar with the transport buttons, volume, the
status display and search; the source list on the left (Library, Devices, Playlists) with the
artwork underneath; songs, podcasts or radio on the right; and the bottom bar with new playlist,
shuffle, repeat and the song count."""
import os

from gi.repository import Gdk, GLib, Gtk, Pango

from . import APP_NAME, VERSION, appearance, art, cd, theme, views

NOT_HERE = "“%s” isn't available in Folio Chord."


def icon(name, size=Gtk.IconSize.BUTTON):
    return Gtk.Image.new_from_icon_name("chord-%s-symbolic" % name, size)


def round_button(name, tip, cb, big=False):
    b = Gtk.Button()
    b.set_image(icon(name, Gtk.IconSize.LARGE_TOOLBAR if big else Gtk.IconSize.BUTTON))
    b.get_style_context().add_class("chord-round")
    if big:
        b.get_style_context().add_class("big")
    b.set_tooltip_text(tip)
    b.set_relief(Gtk.ReliefStyle.NONE)
    b.set_valign(Gtk.Align.CENTER)
    b.connect("clicked", lambda *_: cb())
    return b


def seg_button(name, tip, cb, toggle=False, label=None):
    b = Gtk.ToggleButton() if toggle else Gtk.Button()
    if name:
        b.set_image(icon(name))
    if label:
        b.set_label(label)
        b.set_always_show_image(True)
    b.get_style_context().add_class("chord-seg")
    b.set_tooltip_text(tip)
    b.set_valign(Gtk.Align.CENTER)
    b.set_focus_on_click(False)
    if toggle:
        b.connect("toggled", lambda w: None if getattr(w, "_quiet", False) else cb(w.get_active()))
    else:
        b.connect("clicked", lambda *_: cb())
    return b


class Lcd(Gtk.Box):
    """The status display: what's playing, where, how long; or what Folio Chord is busy with."""

    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.win = win
        self.get_style_context().add_class("chord-lcd")
        self.set_size_request(430, -1)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.pack_start(self.stack, True, True, 0)
        logo = Gtk.Label(label=APP_NAME)
        logo.get_style_context().add_class("chord-lcd-logo")
        self.stack.add_named(logo, "idle")
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.title = Gtk.Label(xalign=0.5)
        self.title.get_style_context().add_class("chord-lcd-title")
        self.title.set_ellipsize(Pango.EllipsizeMode.END)
        self.sub = Gtk.Label(xalign=0.5)
        self.sub.get_style_context().add_class("chord-lcd-sub")
        self.sub.set_ellipsize(Pango.EllipsizeMode.END)
        row = Gtk.Box(spacing=6)
        self.elapsed = Gtk.Label(label="0:00")
        self.elapsed.get_style_context().add_class("chord-lcd-time")
        self.elapsed.set_width_chars(6)
        self.elapsed.set_xalign(1)
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.5)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.scale.connect("change-value", self._seek)
        self.remaining = Gtk.Button(label="-0:00")
        self.remaining.get_style_context().add_class("chord-flat")
        self.remaining.get_child().get_style_context().add_class("chord-lcd-time")
        self.remaining.set_tooltip_text("Show the total time or the time left")
        self.remaining.connect("clicked", self._flip)
        self.show_total = False
        row.pack_start(self.elapsed, False, False, 0)
        row.pack_start(self.scale, True, True, 0)
        row.pack_start(self.remaining, False, False, 0)
        b.pack_start(self.title, False, False, 0)
        b.pack_start(self.sub, False, False, 0)
        b.pack_start(row, False, False, 0)
        self.stack.add_named(b, "playing")
        bb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.busy_label = Gtk.Label(xalign=0.5)
        self.busy_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.busy_bar = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.01)
        self.busy_bar.set_draw_value(False)
        self.busy_bar.set_sensitive(False)
        bb.pack_start(self.busy_label, True, True, 0)
        bb.pack_start(self.busy_bar, False, False, 0)
        bb.set_valign(Gtk.Align.CENTER)
        self.stack.add_named(bb, "busy")
        self._seeking = False
        self._alt = 0
        self.busy = None
        GLib.timeout_add(500, self._tick)
        GLib.timeout_add_seconds(4, self._alternate)

    def _flip(self, *_):
        self.show_total = not self.show_total
        self._tick()

    def _seek(self, scale, scroll, value):
        pb = self.win.app.playback
        if pb.now and not pb.now.get("stream"):
            pb.engine.seek(value)
        return False

    def set_busy(self, text, fraction=None):
        """Show what's going on (importing, burning) instead of the song; None to stop."""
        self.busy = text
        if text is None:
            self.update()
            return
        self.busy_label.set_text(text)
        self.busy_bar.set_visible(fraction is not None)
        if fraction is not None:
            self.busy_bar.set_value(fraction)
        self.stack.set_visible_child_name("busy")

    def _alternate(self):
        self._alt += 1
        self.update()
        return True

    def update(self):
        if self.busy:
            return
        pb = self.win.app.playback
        n = pb.now
        if not n or pb.engine.state == "stopped" and n.get("kind") == "station":
            self.stack.set_visible_child_name("idle" if not n else "playing")
            if not n:
                return
        self.stack.set_visible_child_name("playing")
        if n["kind"] == "station":
            self.title.set_text(n["title"])
            self.sub.set_text(pb.stream_title or n.get("album") or "Internet radio")
        else:
            self.title.set_text(n.get("title") or "")
            parts = [x for x in (n.get("artist"), n.get("album")) if x]
            self.sub.set_text(parts[self._alt % len(parts)] if parts else "")
        self._tick()

    def _tick(self):
        pb = self.win.app.playback
        n = pb.now
        if not n or self.busy:
            return True
        pos = pb.engine.position() if pb.engine.state != "stopped" else 0
        if n.get("stream") and not n.get("duration"):
            self.scale.set_visible(False)
            self.remaining.set_visible(False)
            self.elapsed.set_text(views.fmt_time(pos))
            return True
        self.scale.set_visible(True)
        self.remaining.set_visible(True)
        dur = pb.engine.duration() or n.get("duration") or 0
        self.scale.set_range(0, max(1, dur))
        self.scale.set_value(pos)
        self.elapsed.set_text(views.fmt_time(pos))
        self.remaining.set_label(views.fmt_time(dur) if self.show_total else "-" + views.fmt_time(max(0, dur - pos)))
        return True


class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME)
        self.app = app
        self.lib = app.lib
        self.pods = app.pods
        self.settings = app.settings
        self.get_style_context().add_class("chord-own")
        self.set_default_size(1180, 740)
        self.set_icon_name("folio-chord")
        self.dark = appearance.is_dark()
        appearance.on_change(self._dark_changed)
        self.accel = Gtk.AccelGroup()
        self.add_accel_group(self.accel)
        self.commands = []          # every menu command, for the command walk
        self.missing_log = []
        self.source = ("music", None)
        self.all_rows = []
        self.rows = []
        self.cd_info = None
        self.cd_device = None
        self.mini = self.vis = self.eq_win = None
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(box)
        self.menubar = self._menubar()
        box.pack_start(self.menubar, False, False, 0)
        box.pack_start(self._topbar(), False, False, 0)
        self.paned = Gtk.Paned()
        box.pack_start(self.paned, True, True, 0)
        self.paned.pack1(self._sourcepane(), False, False)
        self.paned.set_position(200)
        self.content = Gtk.Stack()
        self.content.set_transition_type(Gtk.StackTransitionType.NONE)
        self.paned.pack2(self.content, True, False)
        self._songs_page()
        from .podview import PodcastsView
        from .radioview import RadioView
        self.podview = PodcastsView(self)
        self.content.add_named(self.podview, "podcasts")
        self.radioview = RadioView(self)
        self.content.add_named(self.radioview, "radio")
        self._cd_page()
        box.pack_start(self._bottombar(), False, False, 0)
        self.connect("key-press-event", self._key)
        self.connect("delete-event", self._closing)
        app.playback.listen(self._playback)
        self.lib.listeners.append(self._lib_changed)
        self._lib_pending = False
        self.scanning = False
        self.fill_sources()

    def after_show(self):
        self.select_source("music")
        self._sync_modes()
        self.set_view(self.settings["view"])
        self.browser_box.set_visible(self.settings["browser"])
        self.art_box.set_visible(self.settings["artwork"])
        self.art_img.set_from_pixbuf(art.placeholder(180, self.dark))
        if not os.environ.get("FOLIO_CHORD_NO_SCAN"):
            GLib.timeout_add(400, lambda: (self.rescan(), False)[1])
        GLib.timeout_add_seconds(3, self._check_cd)
        GLib.timeout_add_seconds(60, self._podcast_timer)
        if not os.environ.get("FOLIO_CHORD_NO_AUTOSYNC"):
            GLib.timeout_add_seconds(8, lambda: (self.podview.refresh_due(), False)[1])

    def _dark_changed(self, dark):
        self.dark = dark
        self.queue_draw()

    def _closing(self, *a):
        self.settings.save()
        return False

    # ================================================================ menus
    def _menubar(self):
        mb = Gtk.MenuBar()
        mb.get_style_context().add_class("chord-menubar")
        M = [
            ("_File", [
                ("New Playlist", "new-playlist", "<Control>n"),
                ("New Playlist from Selection", "new-playlist-selection", "<Shift><Control>n"),
                ("New Smart Playlist…", "new-smart", "<Alt><Control>n"),
                ("New Playlist Folder", "new-folder", None),
                ("Edit Smart Playlist…", "edit-smart", None),
                None,
                ("Add File to Library…", "add-file", "<Control>o"),
                ("Add Folder to Library…", "add-folder", "<Shift><Control>o"),
                ("Check Music Folders Again", "rescan", None),
                None,
                ("sub", "Library", [("Import Playlist…", "import-playlist", None),
                                    ("Export Playlist…", "export-playlist", None)]),
                ("sub", "Devices", [("Sync", "na:Sync", None), ("Back Up", "na:Back Up", None)]),
                None,
                ("Subscribe to Podcast…", "subscribe", None),
                ("Import Podcasts (OPML)…", "import-opml", None),
                ("Export Podcasts (OPML)…", "export-opml", None),
                None,
                ("Show in Files", "show-in-files", "<Shift><Control>r"),
                ("Burn Playlist to Disc…", "burn", None),
                None,
                ("Close Window", "close", "<Control>w"),
                ("Quit", "quit", "<Control>q")]),
            ("_Edit", [
                ("Copy", "copy", "<Control>c"),
                ("Delete", "delete", None),
                ("Select All", "select-all", "<Control>a"),
                ("Select None", "select-none", "<Shift><Control>a"),
                None,
                ("Get Info", "get-info", "<Control>i"),
                ("sub", "Rating", [("★★★★★", "rate:100", None), ("★★★★", "rate:80", None), ("★★★", "rate:60", None),
                                   ("★★", "rate:40", None), ("★", "rate:20", None), ("None", "rate:0", None)]),
                ("Check Selection", "check-selection", None),
                ("Uncheck Selection", "uncheck-selection", None),
                None,
                ("View Options…", "view-options", "<Control>j"),
                ("Options…", "options", "<Control>comma")]),
            ("_View", [
                ("as List", "view:list", "<Alt><Control>3"),
                ("as Album List", "view:albums", "<Alt><Control>4"),
                ("as Grid", "view:grid", "<Alt><Control>5"),
                None,
                ("Show/Hide Column Browser", "toggle-browser", "<Control>b"),
                ("Show/Hide Artwork", "toggle-artwork", "<Control>g"),
                ("Show Up Next", "up-next", None),
                None,
                ("Show Visualizer", "visualizer", "<Control>t"),
                ("Switch to Mini Player", "mini-player", "<Shift><Control>m"),
                ("Full Screen", "fullscreen", "<Control><Shift>f")]),
            ("_Controls", [
                ("Play/Pause", "play-pause", None),
                ("Stop", "stop", "<Control>period"),
                ("Next", "next", "<Control>Right"),
                ("Previous", "previous", "<Control>Left"),
                ("Go to Current Song", "go-current", "<Control>l"),
                None,
                ("Increase Volume", "volume-up", "<Control>Up"),
                ("Decrease Volume", "volume-down", "<Control>Down"),
                ("Mute", "mute", "<Alt><Control>Down"),
                None,
                ("sub", "Shuffle", [("Shuffle On/Off", "shuffle", "<Control>s"), ("By Songs", "shuffle-by:songs", None),
                                    ("By Albums", "shuffle-by:albums", None)]),
                ("sub", "Repeat", [("Off", "repeat:off", None), ("All", "repeat:all", None), ("One", "repeat:one", None)]),
                None,
                ("Play Next (selection)", "play-next", None),
                ("Add to Up Next", "add-up-next", None),
                ("Clear Up Next", "clear-up-next", None),
                None,
                ("Eject Disc", "eject", "<Control>e")]),
            ("_Store", [
                ("Search the Store", "na:Search the Store", None),
                ("Sign In…", "na:Sign In", None),
                ("Authorize This Computer…", "na:Authorize This Computer", None),
                ("Check for Available Downloads…", "na:Check for Available Downloads", None),
                ("Turn On Match", "na:Match", None)]),
            ("_Advanced", [
                ("Open Stream…", "open-stream", "<Control>u"),
                ("Subscribe to Podcast…", "subscribe", None),
                ("Refresh All Podcasts", "refresh-podcasts", None),
                None,
                ("Import CD", "import-cd", None),
                ("Get Track Names", "get-track-names", None),
                None,
                ("sub", "Create Version", [("Create AAC Version", "convert:AAC", None), ("Create MP3 Version", "convert:MP3", None),
                                           ("Create FLAC Version", "convert:FLAC", None),
                                           ("Create Apple Lossless Version", "convert:Apple Lossless", None)]),
                ("Get Album Artwork", "get-artwork", None)]),
            ("_Window", [
                ("Minimize", "minimize", "<Control>m"),
                ("Zoom", "zoom", None),
                None,
                ("Equalizer", "equalizer", "<Alt><Control>e"),
                (APP_NAME, "front", "<Alt><Control>1")]),
            ("_Help", [
                ("Keyboard Shortcuts", "shortcuts", "F1"),
                ("About Folio Chord", "about", None)]),
        ]
        self.menu_spec = M
        for label, items in M:
            top = Gtk.MenuItem.new_with_mnemonic(label)
            top.set_submenu(self._menu(items))
            mb.append(top)
        return mb

    def _menu(self, items):
        m = Gtk.Menu()
        m.get_style_context().add_class("chord-menu")
        m.set_accel_group(self.accel)
        for it in items:
            if it is None:
                m.append(Gtk.SeparatorMenuItem())
                continue
            if it[0] == "sub":
                mi = Gtk.MenuItem(label=it[1])
                mi.set_submenu(self._menu(it[2]))
                m.append(mi)
                continue
            label, cmd, accel = it
            mi = Gtk.MenuItem(label=label)
            mi.connect("activate", lambda _w, c=cmd: self.run(c))
            if accel:
                key, mods = Gtk.accelerator_parse(accel)
                mi.add_accelerator("activate", self.accel, key, mods, Gtk.AccelFlags.VISIBLE)
            self.commands.append((label, cmd))
            m.append(mi)
        return m

    # ================================================================ top bar
    def _topbar(self):
        bar = Gtk.Box(spacing=8)
        bar.get_style_context().add_class("chord-topbar")
        t = Gtk.Box(spacing=4)
        self.b_prev = round_button("prev", "Previous", lambda: self.run("previous"))
        self.b_play = round_button("play", "Play", lambda: self.run("play-pause"), big=True)
        self.b_next = round_button("next", "Next", lambda: self.run("next"))
        for b in (self.b_prev, self.b_play, self.b_next):
            t.pack_start(b, False, False, 0)
        bar.pack_start(t, False, False, 0)
        v = Gtk.Box(spacing=2)
        v.pack_start(icon("volume-low"), False, False, 0)
        self.volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.02)
        self.volume.set_draw_value(False)
        self.volume.set_size_request(100, -1)
        self.volume.set_value(self.settings["volume"])
        self.volume.connect("value-changed", lambda s: None if getattr(self, "_vol_quiet", False) else self.app.playback.set_volume(s.get_value()))
        self.volume.set_tooltip_text("Volume")
        v.pack_start(self.volume, False, False, 0)
        v.pack_start(icon("volume-high"), False, False, 0)
        v.set_valign(Gtk.Align.CENTER)
        bar.pack_start(v, False, False, 6)
        self.lcd = Lcd(self)
        bar.set_center_widget(self.lcd)
        right = Gtk.Box(spacing=6)
        self.viewbtns = {}
        vb = Gtk.Box(spacing=0)
        vb.get_style_context().add_class("linked")
        for key, name, tip in (("list", "view-list", "View as list"), ("albums", "view-albums", "View as album list"),
                               ("grid", "view-grid", "View as grid")):
            b = seg_button(name, tip, lambda on, k=key: on and self.run("view:" + k), toggle=True)
            self.viewbtns[key] = b
            vb.pack_start(b, False, False, 0)
        vb.set_valign(Gtk.Align.CENTER)
        right.pack_start(vb, False, False, 0)
        self.search = Gtk.SearchEntry()
        self.search.get_style_context().add_class("chord-search")
        self.search.set_placeholder_text("Search Music")
        self.search.set_width_chars(18)
        self.search.set_valign(Gtk.Align.CENTER)
        self.search.connect("search-changed", lambda e: self.apply_search())
        right.pack_start(self.search, False, False, 0)
        bar.pack_end(right, False, False, 0)
        return bar

    # ================================================================ source list
    def _sourcepane(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        #                          icon, name, kind, id, badge, header, editable
        self.src_store = Gtk.TreeStore(str, str, str, int, str, bool, bool)
        v = Gtk.TreeView(model=self.src_store)
        v.get_style_context().add_class("chord-source")
        v.set_headers_visible(False)
        v.set_enable_search(False)
        v.set_show_expanders(True)
        v.set_level_indentation(0)
        col = Gtk.TreeViewColumn()
        ir = Gtk.CellRendererPixbuf()
        col.pack_start(ir, False)
        col.set_cell_data_func(ir, self._src_icon)
        tr = Gtk.CellRendererText()
        tr.set_property("ellipsize", Pango.EllipsizeMode.END)
        tr.connect("edited", self._src_renamed)
        col.pack_start(tr, True)
        col.set_cell_data_func(tr, self._src_text)
        br = Gtk.CellRendererText()
        col.pack_end(br, False)
        col.set_cell_data_func(br, self._src_badge)
        col.set_expand(True)
        self.src_text = tr
        v.append_column(col)
        v.get_selection().set_select_function(lambda sel, model, path, cur: not model[path][5])
        v.get_selection().connect("changed", self._src_changed)
        v.connect("button-press-event", self._src_press)
        v.connect("key-press-event", self._src_key)
        t = [Gtk.TargetEntry.new("application/x-chord-tracks", Gtk.TargetFlags.SAME_APP, 1)]
        v.enable_model_drag_dest(t, Gdk.DragAction.COPY)
        v.connect("drag-data-received", self._src_drop)
        v.connect("drag-motion", self._src_drag_motion)
        self.src_view = v
        sw = Gtk.ScrolledWindow()
        sw.get_style_context().add_class("chord-source")
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.add(v)
        box.pack_start(sw, True, True, 0)
        self.art_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.art_box.get_style_context().add_class("chord-art-pane")
        self.art_title = Gtk.Label(label="Now Playing", xalign=0.5)
        self.art_title.set_margin_top(3)
        self.art_img = Gtk.Image()
        self.art_img.set_margin_bottom(6)
        self.art_box.pack_start(self.art_title, False, False, 0)
        self.art_box.pack_start(self.art_img, False, False, 0)
        box.pack_start(self.art_box, False, False, 0)
        return box

    def _src_icon(self, col, cell, model, it, d=None):
        name = model[it][0]
        cell.set_property("icon-name", ("chord-%s-symbolic" % name) if name else None)
        cell.set_property("visible", bool(name))

    def _src_text(self, col, cell, model, it, d=None):
        c = theme.colours(self.dark)
        sel = self.src_view.get_selection().iter_is_selected(it)
        if model[it][5]:
            cell.set_property("markup", "<small><b>%s</b></small>" % GLib.markup_escape_text(model[it][1]))
            cell.set_property("foreground", c["src_head"])
            cell.set_property("editable", False)
        else:
            cell.set_property("text", model[it][1])
            cell.set_property("foreground", c["sel_fg"] if sel else c["src_fg"])
            cell.set_property("editable", model[it][6] and getattr(self, "_editing", False))

    def _src_badge(self, col, cell, model, it, d=None):
        t = model[it][4]
        c = theme.colours(self.dark)
        cell.set_property("visible", bool(t))
        if t:
            cell.set_property("markup", "<small><b> %s </b></small>" % GLib.markup_escape_text(t))
            cell.set_property("foreground", c["badge_fg"])
            cell.set_property("background", c["badge"])

    def fill_sources(self):
        sel_key = self.source
        s = self.src_store
        self._src_quiet = True      # emptying the list moves the selection about: not a choice
        s.clear()
        lib = s.append(None, ["", "LIBRARY", "header", 0, "", True, False])
        s.append(None, ["music", "Music", "music", 0, "", False, False])
        unplayed = sum(p["unplayed"] for p in self.pods.shows())
        s.append(None, ["podcast", "Podcasts", "podcasts", 0, str(unplayed) if unplayed else "", False, False])
        s.append(None, ["radio", "Radio", "radio", 0, "", False, False])
        if self.cd_info is not None:
            s.append(None, ["", "DEVICES", "header", 0, "", True, False])
            s.append(None, ["cd", self.cd_info.get("album") or "Audio CD", "cd", 0, "", False, False])
        s.append(None, ["", "PLAYLISTS", "header", 0, "", True, False])
        pls = self.lib.playlists()
        nodes = {}

        def add(p, parent):
            kind = p["kind"]
            it = s.append(parent, [{"smart": "smart", "folder": "folder"}.get(kind, "playlist"), p["name"], kind, p["id"], "", False, True])
            nodes[p["id"]] = it
            for c in pls:
                if c["parent"] == p["id"]:
                    add(c, it)
        for p in pls:
            if p["parent"] is None or p["parent"] not in {x["id"] for x in pls}:
                add(p, None)
        self.src_view.expand_all()
        del lib
        self._src_quiet = False
        self._select_src_row(*sel_key, quiet=True)

    def _select_src_row(self, kind, pid=None, quiet=False):
        found = []

        def walk(model, path, it):
            r = model[it]
            if r[2] == kind and (pid is None or r[3] == pid) and not r[5]:
                found.append(path.copy())
                return True
            return False
        self.src_store.foreach(walk)
        if found:
            self._src_quiet = quiet
            self.src_view.get_selection().select_path(found[0])
            self._src_quiet = False
            return True
        return False

    def select_source(self, kind, pid=None):
        if not self._select_src_row(kind, pid):
            self._select_src_row("music")

    def _src_changed(self, sel):
        model, it = sel.get_selected()
        if it is None or getattr(self, "_src_quiet", False):
            return
        r = model[it]
        self.source = (r[2], r[3] if r[2] not in ("music", "podcasts", "radio", "cd") else None)
        self.show_source()

    def show_source(self):
        kind, pid = self.source
        self.search.set_text("")
        if kind == "podcasts":
            self.content.set_visible_child_name("podcasts")
            self.search.set_placeholder_text("Search Podcasts")
            self.podview.refresh()
        elif kind == "radio":
            self.content.set_visible_child_name("radio")
            self.search.set_placeholder_text("Search Stations")
            self.radioview.refresh()
        elif kind == "cd":
            self.content.set_visible_child_name("cd")
            self.search.set_placeholder_text("Search")
            self.fill_cd()
        else:
            self.content.set_visible_child_name("songs")
            self.search.set_placeholder_text("Search Music" if kind == "music" else "Search Playlist")
            self.load_songs()
        self.update_status()

    def current_playlist(self):
        kind, pid = self.source
        return self.lib.playlist(pid) if kind in ("playlist", "smart", "folder") else None

    def _src_press(self, v, ev):
        hit = v.get_path_at_pos(int(ev.x), int(ev.y))
        if ev.button == 3:
            if hit and not self.src_store[hit[0]][5]:
                v.get_selection().select_path(hit[0])
            self._src_menu(ev)
            return True
        if ev.type == Gdk.EventType._2BUTTON_PRESS and hit and self.src_store[hit[0]][6]:
            self.rename_playlist(hit[0])
            return True
        return False

    def _src_key(self, v, ev):
        if ev.keyval in (Gdk.KEY_Delete, Gdk.KEY_KP_Delete) and self.current_playlist():
            self.run("delete-playlist")
            return True
        if ev.keyval == Gdk.KEY_F2 and self.current_playlist():
            self.rename_playlist()
            return True
        return False

    def rename_playlist(self, path=None):
        if path is None:
            model, it = self.src_view.get_selection().get_selected()
            if it is None:
                return
            path = model.get_path(it)
        self._editing = True
        self.src_view.set_cursor_on_cell(path, self.src_view.get_column(0), self.src_text, True)

    def _src_renamed(self, cell, path, text):
        self._editing = False
        r = self.src_store[path]
        if text.strip() and r[6]:
            self.lib.rename_playlist(r[3], text.strip())
            r[1] = text.strip()

    def _src_menu(self, ev):
        items = [("New Playlist", "new-playlist"), ("New Smart Playlist…", "new-smart"), ("New Playlist Folder", "new-folder")]
        p = self.current_playlist()
        if p:
            items += [None, ("Play", "play-source"), ("Rename", "rename-playlist")]
            if p["kind"] == "smart":
                items.append(("Edit Smart Playlist…", "edit-smart"))
            items += [("Burn Playlist to Disc…", "burn"), ("Export Playlist…", "export-playlist"), None,
                      ("Delete Playlist", "delete-playlist")]
        elif self.source[0] == "cd":
            items += [None, ("Import CD", "import-cd"), ("Get Track Names", "get-track-names"), ("Eject", "eject")]
        self.popup(items, ev)

    def popup(self, items, ev=None):
        m = Gtk.Menu()
        m.get_style_context().add_class("chord-menu")
        for it in items:
            if it is None:
                m.append(Gtk.SeparatorMenuItem())
                continue
            if isinstance(it[1], list):
                mi = Gtk.MenuItem(label=it[0])
                sub = Gtk.Menu()
                sub.get_style_context().add_class("chord-menu")
                for a in it[1]:
                    x = Gtk.MenuItem(label=a[0])
                    x.connect("activate", lambda _w, c=a[1]: self.run(c))
                    sub.append(x)
                mi.set_submenu(sub)
                m.append(mi)
                continue
            mi = Gtk.MenuItem(label=it[0])
            mi.connect("activate", lambda _w, c=it[1]: self.run(c))
            m.append(mi)
        m.show_all()
        m.attach_to_widget(self, None)
        if os.environ.get("FOLIO_TEST_SCRIPT"):
            self.last_popup = [it for it in items if it]
            return m
        m.popup_at_pointer(ev)
        return m

    def _src_drag_motion(self, v, ctx, x, y, t):
        dest = v.get_dest_row_at_pos(x, y)
        if dest and self.src_store[dest[0]][2] == "playlist":
            v.set_drag_dest_row(dest[0], Gtk.TreeViewDropPosition.INTO_OR_BEFORE)
            Gdk.drag_status(ctx, Gdk.DragAction.COPY, t)
            return True
        if dest and self.src_store[dest[0]][2] == "header" and self.src_store[dest[0]][1] == "PLAYLISTS":
            Gdk.drag_status(ctx, Gdk.DragAction.COPY, t)
            return True
        Gdk.drag_status(ctx, 0, t)
        return True

    def _src_drop(self, v, ctx, x, y, data, info, t):
        ids = [int(i) for i in (data.get_data() or b"").decode().split(",") if i]
        dest = v.get_dest_row_at_pos(x, y)
        self.drop_on_source(self.src_store[dest[0]] if dest else None, ids)
        ctx.finish(True, False, t)

    def drop_on_source(self, row, ids):
        """Songs dropped on the source list: onto a playlist adds them; elsewhere makes a new one."""
        if not ids:
            return
        if row is not None and row[2] == "playlist":
            self.lib.add_to_playlist(row[3], ids)
            return row[3]
        first = self.lib.track(ids[0])
        name = (first["album"] if all((self.lib.track(i) or {"album": None})["album"] == first["album"] for i in ids) else None) \
            or (first["artist"] if all((self.lib.track(i) or {"artist": None})["artist"] == first["artist"] for i in ids) else None) \
            or "untitled playlist"
        pid = self.lib.new_playlist(name, tracks=ids)
        self.fill_sources()
        return pid

    # ================================================================ songs page
    def _songs_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.banner = Gtk.Box(spacing=8)
        self.banner.get_style_context().add_class("chord-banner")
        self.banner_label = Gtk.Label(xalign=0)
        self.banner.pack_start(self.banner_label, True, True, 0)
        self.banner_btn = Gtk.Button(label="Add Folder…")
        self.banner_btn.get_style_context().add_class("chord-button")
        self.banner_btn.connect("clicked", lambda *_: self.run("add-folder"))
        self.banner.pack_end(self.banner_btn, False, False, 0)
        self.banner.set_no_show_all(True)
        box.pack_start(self.banner, False, False, 0)
        self.browser = views.ColumnBrowser(self)
        self.browser.connect("changed", lambda *_: self.apply_search())
        self.browser_box = Gtk.Box()
        self.browser_box.pack_start(self.browser, True, True, 0)
        box.pack_start(self.browser_box, False, False, 0)
        self.songview = Gtk.Stack()
        self.songs = views.SongList(self, self.settings["columns"])
        self.songs.connect("play", lambda w, i: self.play_from_list(i))
        self.songs.connect("context", lambda w, ev: self.song_menu(ev))
        self.songs.connect("selection", lambda *_: self._selection_changed())
        self.albumlist = views.AlbumList(self)
        self.albumlist.connect("play", lambda w, rows, i: self.app.playback.play_songs([r["id"] for r in rows], i))
        self.albumlist.connect("context", lambda w, ev: self.song_menu(ev))
        self.grid = views.AlbumGrid(self)
        self.grid.connect("play", lambda w, rows: self.app.playback.play_songs([r["id"] for r in rows], 0))
        self.grid.connect("context", lambda w, ev: self.song_menu(ev))
        self.songview.add_named(self.songs, "list")
        self.songview.add_named(self.albumlist, "albums")
        self.songview.add_named(self.grid, "grid")
        box.pack_start(self.songview, True, True, 0)
        self.content.add_named(box, "songs")

    def load_songs(self):
        kind, pid = self.source
        if kind == "music":
            self.all_rows = self.lib.tracks()
        else:
            self.all_rows = self.lib.playlist_tracks(pid)
        self.browser.set_rows(self.all_rows)
        self.apply_search()
        n = len(self.lib.q("select id from tracks where not missing limit 1"))
        if kind == "music" and not n:
            self.banner_label.set_text("Your library is empty. Add the folder your music is in, or check it again." if not self.scanning
                                       else "Looking through your music folders…")
            self.banner.set_no_show_all(False)
            self.banner.show_all()
        else:
            self.banner.hide()

    def apply_search(self):
        kind = self.source[0]
        q = self.search.get_text().strip().lower()
        if kind == "podcasts":
            self.podview.search(q)
            return
        if kind == "radio":
            self.radioview.search(q)
            return
        if kind == "cd":
            return
        rows = self.browser.filter(self.all_rows) if self.browser_box.get_visible() else self.all_rows
        if q:
            words = q.split()
            rows = [r for r in rows if all(any(w in (r[c] or "").lower() for c in ("title", "artist", "album", "album_artist",
                                                                                    "genre", "composer")) for w in words)]
        self.rows = rows
        p = self.current_playlist()
        self.songs.set_rows(rows, p["id"] if p and p["kind"] == "playlist" and not q else None)
        if self.songview.get_visible_child_name() == "albums":
            self.albumlist.set_rows(rows)
        elif self.songview.get_visible_child_name() == "grid":
            self.grid.set_rows(rows)
        self.update_status()

    def set_view(self, key):
        self.songview.set_visible_child_name(key)
        for k, b in self.viewbtns.items():
            b._quiet = True
            b.set_active(k == key)
            b._quiet = False
        self.settings["view"] = key
        if key == "albums":
            self.albumlist.set_rows(self.rows)
        elif key == "grid":
            self.grid.set_rows(self.rows)

    def selected_rows(self):
        kind = self.source[0]
        if kind in ("podcasts", "radio", "cd"):
            return []
        v = self.songview.get_visible_child_name()
        if v == "albums":
            return self.albumlist.selected_rows()
        if v == "grid":
            return self.grid.selected_rows()
        ids = self.songs.selected_ids()
        by = {r["id"]: r for r in self.rows}
        return [by[i] for i in ids if i in by]

    def selected_ids(self):
        return [r["id"] for r in self.selected_rows()]

    def play_from_list(self, index):
        ids = self.songs.ids_in_order()
        if ids:
            self.app.playback.play_songs(ids, index)

    def song_menu(self, ev):
        if not self.selected_ids():
            return
        pls = [p for p in self.lib.playlists() if p["kind"] == "playlist"]
        items = [("Play", "play-selection"), ("Play Next", "play-next"), ("Add to Up Next", "add-up-next"), None,
                 ("Get Info", "get-info"),
                 ("Rating", [("★★★★★", "rate:100"), ("★★★★", "rate:80"), ("★★★", "rate:60"), ("★★", "rate:40"),
                             ("★", "rate:20"), ("None", "rate:0")]),
                 ("Add to Playlist", [("New Playlist from Selection", "new-playlist-selection")] +
                  [(p["name"], "add-to:%d" % p["id"]) for p in pls]),
                 None, ("Check Selection", "check-selection"), ("Uncheck Selection", "uncheck-selection"),
                 ("Show in Files", "show-in-files"), ("Copy", "copy"), None]
        items.append(("Remove from Playlist", "delete") if (self.current_playlist() or {"kind": ""})["kind"] == "playlist"
                     else ("Delete from Library", "delete"))
        self.popup(items, ev)

    def _selection_changed(self):
        rows = self.selected_rows()
        if self.app.playback.now is None and rows:
            self._show_art(rows[0], "Selected Item")

    # ================================================================ CD page
    def _cd_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        bar = Gtk.Box(spacing=8)
        bar.get_style_context().add_class("chord-sectionbar")
        self.cd_title = Gtk.Label(xalign=0)
        self.cd_title.get_style_context().add_class("chord-heading")
        bar.pack_start(self.cd_title, True, True, 0)
        for label, cmd in (("Get Track Names", "get-track-names"), ("Eject", "eject"), ("Import CD", "import-cd")):
            b = Gtk.Button(label=label)
            b.get_style_context().add_class("chord-button" if cmd != "import-cd" else "chord-default")
            b.connect("clicked", lambda _b, c=cmd: self.run(c))
            bar.pack_end(b, False, False, 0)
        box.pack_start(bar, False, False, 0)
        #                         import?, n, title, time, artist
        self.cd_store = Gtk.ListStore(bool, int, str, str, str)
        v = Gtk.TreeView(model=self.cd_store)
        r = Gtk.CellRendererToggle()
        r.set_activatable(True)
        r.connect("toggled", lambda c, p: self.cd_store[p].__setitem__(0, not self.cd_store[p][0]))
        v.append_column(Gtk.TreeViewColumn("", r, active=0))
        for title, i, w in (("#", 1, 36), ("Name", 2, 300), ("Time", 3, 60), ("Artist", 4, 200)):
            c = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
            c.set_fixed_width(w)
            c.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            v.append_column(c)
        v.append_column(Gtk.TreeViewColumn(""))
        v.connect("row-activated", lambda v, p, c: self.play_cd_track(p.get_indices()[0] + 1))
        self.cd_view = v
        sw = Gtk.ScrolledWindow()
        sw.add(v)
        box.pack_start(sw, True, True, 0)
        self.content.add_named(box, "cd")

    def fill_cd(self):
        info = self.cd_info or {"tracks": []}
        self.cd_title.set_text("%s%s" % (info.get("album") or "Audio CD", (" — " + info["artist"]) if info.get("artist") else ""))
        self.cd_store.clear()
        for i, secs in enumerate(info.get("lengths", [])):
            t = info["tracks"][i] if i < len(info.get("tracks") or []) else {}
            self.cd_store.append([True, i + 1, t.get("title") or "Track %d" % (i + 1), views.fmt_time(secs),
                                  t.get("artist") or info.get("artist") or ""])

    def _check_cd(self):
        if getattr(self, "_cd_busy", False):
            return True
        drives = cd.drives()
        dev = drives[0] if drives else None
        if dev is None:
            if self.cd_info is not None:
                self.cd_info = None
                self.fill_sources()
            return True
        if self.cd_info is not None and self.cd_device == dev:
            return True
        self._cd_busy = True
        from . import net

        def read():
            return cd.read_disc(dev)

        def got(d):
            self._cd_busy = False
            if d is None:
                if self.cd_info is not None:
                    self.cd_info = None
                    self.fill_sources()
                return
            self.cd_device = dev
            n = len(d["tracks"])
            text = d.get("cdtext") or {}
            self.cd_info = {"album": text.get("album") or "Audio CD", "artist": text.get("artist") or "", "year": 0,
                            "genre": "", "tracks": [{} for _ in range(n)], "lengths": d["tracks"], "discid": d.get("discid", ""),
                            "disc_no": 1, "disc_count": 1}
            self.fill_sources()
            if self.settings["cd_lookup"] and d.get("discid"):
                self.run("get-track-names")
        net.in_thread(read, got, lambda e: setattr(self, "_cd_busy", False))
        return True

    def play_cd_track(self, n):
        if self.cd_device and self.cd_device.startswith("fake:"):
            import glob
            f = sorted(glob.glob(os.path.join(self.cd_device[5:], "*.wav")))[n - 1]
            uri = "file://" + f
        else:
            uri = "cdda://%d#%s" % (n, self.cd_device)
        info = self.cd_info or {}
        t = info["tracks"][n - 1] if n <= len(info.get("tracks") or []) else {}
        self.app.playback.queue.start([], 0)
        self.app.playback._start({"kind": "cd", "id": n, "uri": uri, "title": t.get("title") or "Track %d" % n,
                                  "artist": t.get("artist") or info.get("artist", ""), "album": info.get("album", ""),
                                  "duration": info["lengths"][n - 1] if info.get("lengths") else 0, "rg": None})

    # ================================================================ bottom bar
    def _bottombar(self):
        bar = Gtk.Box(spacing=6)
        bar.get_style_context().add_class("chord-bottombar")
        add = seg_button("add", "New playlist (hold for more)", lambda: self.run("new-playlist"))
        add.connect("button-press-event", lambda w, ev: ev.button == 3 and (self.popup(
            [("New Playlist", "new-playlist"), ("New Smart Playlist…", "new-smart"), ("New Playlist Folder", "new-folder")], ev), True)[1])
        bar.pack_start(add, False, False, 0)
        self.b_shuffle = seg_button("shuffle", "Shuffle", lambda on: self.run("shuffle-set:%d" % on), toggle=True)
        self.b_repeat = seg_button("repeat", "Repeat: off", lambda: self.run("repeat-cycle"))
        self.b_art = seg_button("info", "Show or hide artwork", lambda on: self.run("artwork-set:%d" % on), toggle=True)
        for b in (self.b_shuffle, self.b_repeat, self.b_art):
            bar.pack_start(b, False, False, 0)
        self.status = Gtk.Label()
        bar.set_center_widget(self.status)
        right = Gtk.Box(spacing=4)
        right.pack_start(seg_button("up-next", "Up Next", lambda: self.run("up-next")), False, False, 0)
        right.pack_start(seg_button("equalizer", "Equalizer", lambda: self.run("equalizer")), False, False, 0)
        right.pack_start(seg_button("visualizer", "Visualizer", lambda: self.run("visualizer")), False, False, 0)
        right.pack_start(seg_button("mini", "Mini Player", lambda: self.run("mini-player")), False, False, 0)
        self.b_upnext = right.get_children()[0]
        bar.pack_end(right, False, False, 0)
        return bar

    def update_status(self):
        kind = self.source[0]
        if kind == "podcasts":
            self.status.set_text(self.podview.status_text())
        elif kind == "radio":
            self.status.set_text(self.radioview.status_text())
        elif kind == "cd":
            n = len((self.cd_info or {}).get("lengths") or [])
            self.status.set_text("%d songs, %s" % (n, views.fmt_time(sum((self.cd_info or {}).get("lengths") or []))))
        else:
            self.status.set_text(self.lib.stats(self.rows))

    def _sync_modes(self):
        q = self.app.playback.queue
        self.b_shuffle._quiet = True
        self.b_shuffle.set_active(q.shuffle)
        self.b_shuffle._quiet = False
        self.b_repeat.set_image(icon("repeat-one" if q.repeat == "one" else "repeat"))
        sc = self.b_repeat.get_style_context()
        (sc.add_class if q.repeat != "off" else sc.remove_class)("on")
        self.b_repeat.set_tooltip_text("Repeat: %s" % {"off": "off", "all": "all", "one": "one"}[q.repeat])
        self.b_shuffle.set_tooltip_text("Shuffle: %s (by %s)" % ("on" if q.shuffle else "off", q.shuffle_by))
        self.b_art._quiet = True
        self.b_art.set_active(self.settings["artwork"])
        self.b_art._quiet = False

    # ================================================================ events
    def _playback(self, ev, val):
        pb = self.app.playback
        if ev == "state":
            playing = pb.engine.state == "playing"
            self.b_play.set_image(icon("pause" if playing and not (pb.now or {}).get("kind") == "station" else
                                       "stop" if playing else "play", Gtk.IconSize.LARGE_TOOLBAR))
            self.b_play.set_tooltip_text("Pause" if playing else "Play")
            self.lcd.update()
        elif ev == "track":
            self.lcd.update()
            if val and val.get("kind") == "song":
                self.songs.mark_playing(val["id"])
                r = self.lib.track(val["id"])
                if r:
                    self._show_art(r, "Now Playing")
            elif val and val.get("artwork"):
                art.for_url(val["artwork"], 180, lambda pb_: self.art_img.set_from_pixbuf(pb_ or art.placeholder(180, self.dark)))
                self.art_title.set_text("Now Playing")
            else:
                self.art_img.set_from_pixbuf(art.placeholder(180, self.dark))
            if self.mini:
                self.mini.update()
        elif ev == "tags":
            self.lcd.update()
            if self.mini:
                self.mini.update()
        elif ev == "volume":
            self._vol_quiet = True
            self.volume.set_value(val)
            self._vol_quiet = False
        elif ev == "modes":
            self._sync_modes()
        elif ev == "error":
            self.lcd.set_busy(val)
            GLib.timeout_add_seconds(4, lambda: (self.lcd.set_busy(None), False)[1])
        elif ev == "play-selection":
            self.run("play-selection")
        elif ev == "spectrum" and self.vis:
            self.vis.feed(val)

    def _show_art(self, row, title):
        self.art_title.set_text(title)
        self.art_img.set_from_pixbuf(art.for_song(row["path"], 180) or art.placeholder(180, self.dark))

    def _lib_changed(self, what):
        if self._lib_pending:
            return
        self._lib_pending = True

        def later():
            self._lib_pending = False
            if what in ("playlists",):
                self.fill_sources()
            if what in ("podcasts",):
                self.fill_sources()
            if self.source[0] in ("music", "playlist", "smart", "folder") and what in ("tracks", "playlist-items", "playlists", "plays"):
                sel = self.songs.selected_ids()
                self.load_songs()
                self.songs.select_ids(sel, scroll=False)
            return False
        GLib.idle_add(later)

    def _key(self, w, ev):
        focus = self.get_focus()
        typing = isinstance(focus, (Gtk.Entry, Gtk.TextView)) or getattr(self, "_editing", False)
        if ev.keyval == Gdk.KEY_space and not typing:
            self.run("play-pause")
            return True
        if ev.keyval in (Gdk.KEY_AudioPlay, Gdk.KEY_AudioPause):
            self.run("play-pause")
            return True
        if ev.keyval == Gdk.KEY_AudioNext:
            self.run("next")
            return True
        if ev.keyval == Gdk.KEY_AudioPrev:
            self.run("previous")
            return True
        if ev.keyval == Gdk.KEY_f and ev.state & Gdk.ModifierType.CONTROL_MASK:
            self.search.grab_focus()
            return True
        if ev.keyval == Gdk.KEY_Escape and self.is_fullscreen():
            self.unfullscreen()
            return True
        return False

    def is_fullscreen(self):
        gw = self.get_window()
        return bool(gw and gw.get_state() & Gdk.WindowState.FULLSCREEN)

    # ================================================================ scanning and adding
    def rescan(self):
        if self.scanning:
            return
        self.scanning = True
        self.lcd.set_busy("Checking your music folders…")
        from . import net

        def work():
            return self.lib.scan(progress=lambda n: GLib.idle_add(lambda: (self.lcd.set_busy("Checking your music folders… %d songs" % n), False)[1]))

        def done(res):
            self.scanning = False
            self.lcd.set_busy(None)
            self.load_songs() if self.source[0] == "music" else None

        def fail(e):
            self.scanning = False
            self.lcd.set_busy(None)
        net.in_thread(work, done, fail)

    def add_paths(self, paths, play=False):
        ids = []
        for p in paths:
            if os.path.isdir(p):
                self.lib.add_folder(p)
                folders = self.settings["music_folders"] or []
                if p not in folders:
                    self.settings.set("music_folders", folders + [p])
                for d, _dirs, files in os.walk(p):
                    for f in sorted(files):
                        tid = self.lib.add_file(os.path.join(d, f))
                        if tid:
                            ids.append(tid)
            else:
                tid = self.lib.add_file(p)
                if tid:
                    ids.append(tid)
        self.lib.changed()
        if play and ids:
            self.app.playback.play_songs(ids, 0)
        return ids

    def _podcast_timer(self):
        self.podview.refresh_due()
        return True

    # ================================================================ commands
    def run(self, cmd, *args):
        name, _, arg = cmd.partition(":")
        fn = getattr(self, "act_" + name.replace("-", "_"), None)
        if fn is None:
            self.missing_log.append(cmd)
            self.info(NOT_HERE % (arg or cmd))
            return None
        try:
            return fn(arg) if arg else fn(*args)
        except Exception as e:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            self.info("Something went wrong: %s" % e)
            return None

    def act_na(self, what):
        self.missing_log.append("na:" + what)
        self.info(NOT_HERE % what)

    def info(self, text, title=None):
        from . import dialogs
        return dialogs.message(self, text, title)

    # ---- File
    def act_new_playlist(self, tracks=()):
        pid = self.lib.new_playlist("untitled playlist", tracks=list(tracks))
        self.fill_sources()
        self.select_source("playlist", pid)
        self.rename_playlist()
        return pid

    def act_new_playlist_selection(self):
        ids = self.selected_ids()
        if not ids:
            self.info("Select some songs first.")
            return None
        pid = self.drop_on_source(None, ids)
        self.select_source("playlist", pid)
        return pid

    def act_new_smart(self):
        from . import dialogs
        spec = dialogs.smart_playlist(self, None)
        if spec is None:
            return None
        pid = self.lib.new_playlist(spec.pop("name", "untitled playlist"), kind="smart", rules=spec)
        self.fill_sources()
        self.select_source("smart", pid)
        return pid

    def act_edit_smart(self):
        import json
        from . import dialogs
        p = self.current_playlist()
        if not p or p["kind"] != "smart":
            self.info("Select a Smart Playlist first.")
            return None
        spec = dialogs.smart_playlist(self, dict(json.loads(p["rules"] or "{}"), name=p["name"]))
        if spec is None:
            return None
        name = spec.pop("name", p["name"])
        self.lib.set_rules(p["id"], spec)
        if name != p["name"]:
            self.lib.rename_playlist(p["id"], name)
        self.load_songs()
        return p["id"]

    def act_new_folder(self):
        pid = self.lib.new_playlist("untitled folder", kind="folder")
        self.fill_sources()
        self.select_source("folder", pid)
        self.rename_playlist()
        return pid

    def act_rename_playlist(self):
        self.rename_playlist()

    def act_delete_playlist(self):
        from . import dialogs
        p = self.current_playlist()
        if not p:
            return
        if dialogs.confirm(self, "Delete the playlist “%s”?" % p["name"],
                           "The songs stay in your library." if p["kind"] != "folder" else "The playlists in it stay.", "Delete"):
            self.lib.delete_playlist(p["id"])
            self.source = ("music", None)
            self.fill_sources()
            self.select_source("music")

    def act_play_source(self):
        self.load_songs()
        if self.rows:
            self.app.playback.play_songs([r["id"] for r in self.rows], 0)

    def act_add_file(self):
        from . import dialogs
        files = dialogs.choose_files(self, "Add to Library", audio=True)
        if files:
            return self.add_paths(files)

    def act_add_folder(self):
        from . import dialogs
        d = dialogs.choose_folder(self, "Add Folder to Library")
        if d:
            ids = self.add_paths([d])
            self.load_songs()
            return ids

    def act_rescan(self):
        self.rescan()

    def act_import_playlist(self):
        from . import dialogs
        f = dialogs.choose_files(self, "Import Playlist", patterns=[("Playlists", ["*.m3u", "*.m3u8"])], multiple=False)
        if f:
            pid = self.lib.import_m3u(f[0])
            self.fill_sources()
            self.select_source("playlist", pid)
            return pid

    def act_export_playlist(self):
        from . import dialogs
        p = self.current_playlist()
        rows = self.lib.playlist_tracks(p["id"]) if p else self.rows
        name = (p["name"] if p else "Library") + ".m3u"
        f = dialogs.save_file(self, "Export Playlist", name)
        if f:
            self.lib.export_m3u(rows, f)
            return f

    def act_subscribe(self):
        from . import dialogs
        url = dialogs.ask_text(self, "Subscribe to Podcast", "Podcast address (the feed's URL):", "")
        if url:
            self.podview.subscribe(url.strip())

    def act_import_opml(self):
        from . import dialogs
        f = dialogs.choose_files(self, "Import Podcasts", patterns=[("OPML", ["*.opml", "*.xml"])], multiple=False)
        if f:
            from .podcasts import Podcasts
            for _title, url in Podcasts.read_opml(f[0]):
                self.podview.subscribe(url, quiet=True)

    def act_export_opml(self):
        from . import dialogs
        f = dialogs.save_file(self, "Export Podcasts", "Podcasts.opml")
        if f:
            self.pods.export_opml(f)
            return f

    def act_show_in_files(self):
        rows = self.selected_rows()
        if not rows and self.app.playback.now and self.app.playback.now.get("path"):
            rows = [self.lib.track(self.app.playback.now["id"])]
        if not rows:
            return None
        uri = GLib.filename_to_uri(rows[0]["path"], None)
        try:
            from gi.repository import Gio
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            bus.call_sync("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1", "org.freedesktop.FileManager1",
                          "ShowItems", GLib.Variant("(ass)", ([uri], "")), None, Gio.DBusCallFlags.NONE, 2000, None)
        except Exception:       # noqa: BLE001
            if not os.environ.get("FOLIO_TEST_SCRIPT"):
                Gtk.show_uri_on_window(self, GLib.filename_to_uri(os.path.dirname(rows[0]["path"]), None), Gdk.CURRENT_TIME)
        return uri

    def act_burn(self):
        from . import dialogs
        p = self.current_playlist()
        if not p:
            self.info("Choose the playlist to burn in the source list first.")
            return None
        rows = self.lib.playlist_tracks(p["id"])
        return dialogs.burn(self, p["name"], rows)

    def act_close(self):
        self.close()

    def act_quit(self):
        self.app.quit()

    # ---- Edit
    def act_copy(self):
        rows = self.selected_rows()
        text = "\n".join("%s\t%s\t%s\t%s" % (r["title"], views.fmt_time(r["duration"]), r["artist"] or "", r["album"] or "") for r in rows)
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)
        return text

    def act_delete(self):
        from . import dialogs
        p = self.current_playlist()
        if self.source[0] == "podcasts":
            return self.podview.delete_selected()
        if self.source[0] == "radio":
            return self.radioview.remove_selected()
        ids = self.selected_ids()
        if not ids:
            return None
        if p and p["kind"] == "playlist":
            self.lib.remove_from_playlist(p["id"], self.songs.selected_positions())
            return ids
        if p and p["kind"] != "playlist":
            self.info("Songs can't be removed from a Smart Playlist; change its rules instead.")
            return None
        r = dialogs.choose(self, "Remove %s from your library?" % ("the selected song" if len(ids) == 1 else "%d songs" % len(ids)),
                           "Keep the files, or move them to the Trash as well.", [("Cancel", 0), ("Keep Files", 1), ("Move to Trash", 2)])
        if r in (1, 2):
            if r == 2:
                from gi.repository import Gio
                for i in ids:
                    t = self.lib.track(i)
                    try:
                        Gio.File.new_for_path(t["path"]).trash(None)
                    except GLib.Error:
                        pass
            self.lib.remove(ids)
            return ids
        return None

    def act_select_all(self):
        if isinstance(self.get_focus(), Gtk.Entry):
            self.get_focus().select_region(0, -1)
            return
        self.songs.view.get_selection().select_all()

    def act_select_none(self):
        self.songs.view.get_selection().unselect_all()

    def act_get_info(self):
        from . import dialogs
        if self.source[0] == "podcasts":
            return self.podview.info_selected()
        rows = self.selected_rows()
        if not rows:
            return None
        return dialogs.get_info(self, [r["id"] for r in rows])

    def act_rate(self, v):
        ids = self.selected_ids()
        if ids:
            self.lib.rate(ids, int(v))
        return ids

    def act_check_selection(self):
        self.lib.update(self.selected_ids(), checked=1)

    def act_uncheck_selection(self):
        self.lib.update(self.selected_ids(), checked=0)

    def act_view_options(self):
        from . import dialogs
        cols = dialogs.view_options(self, self.settings["columns"])
        if cols is not None:
            self.settings.set("columns", cols)
            self.songs.set_columns(cols)
            self.apply_search()
        return cols

    def act_options(self):
        from . import dialogs
        return dialogs.options(self)

    def act_add_to(self, pid):
        ids = self.selected_ids()
        if ids:
            self.lib.add_to_playlist(int(pid), ids)
        return ids

    # ---- View
    def act_view(self, key):
        self.set_view(key)

    def act_toggle_browser(self):
        on = not self.browser_box.get_visible()
        self.browser_box.set_visible(on)
        self.settings.set("browser", on)
        self.apply_search()

    def act_toggle_artwork(self):
        self.act_artwork_set("0" if self.art_box.get_visible() else "1")

    def act_artwork_set(self, on):
        on = on == "1"
        self.art_box.set_visible(on)
        self.settings.set("artwork", on)
        self._sync_modes()

    def act_up_next(self):
        from . import extras
        return extras.up_next(self, self.b_upnext)

    def act_visualizer(self):
        from . import extras
        if self.vis is None:
            self.vis = extras.Visualizer(self)
        self.vis.show_all()
        self.vis.present()
        return self.vis

    def act_mini_player(self):
        from . import extras
        if self.mini is None:
            self.mini = extras.MiniPlayer(self)
        self.mini.show_all()
        self.mini.present()
        self.hide()
        return self.mini

    def act_fullscreen(self):
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()

    # ---- Controls
    def act_play_pause(self):
        self.app.playback.toggle()

    def act_play_selection(self):
        rows = self.selected_rows()
        if rows:
            ids = self.songs.ids_in_order() if self.songview.get_visible_child_name() == "list" else [r["id"] for r in rows]
            first = rows[0]["id"]
            self.app.playback.play_songs(ids, ids.index(first) if first in ids else 0)
        elif self.source[0] in ("music", "playlist", "smart", "folder") and self.rows:
            self.app.playback.play_songs(self.songs.ids_in_order(), 0)
        elif self.source[0] == "podcasts":
            self.podview.play_selected()
        elif self.source[0] == "radio":
            self.radioview.play_selected()

    def act_stop(self):
        self.app.playback.stop()

    def act_next(self):
        self.app.playback.next()

    def act_previous(self):
        self.app.playback.previous()

    def act_go_current(self):
        n = self.app.playback.now
        if not n:
            return False
        if n["kind"] == "song":
            if self.source[0] not in ("music", "playlist", "smart", "folder") or not self.songs.select_ids([n["id"]]):
                self.source = ("music", None)
                self.select_source("music")
                self.songs.select_ids([n["id"]])
            return True
        if n["kind"] == "episode":
            self.select_source("podcasts")
            return True
        if n["kind"] == "station":
            self.select_source("radio")
            return True
        return False

    def act_volume_up(self):
        self.app.playback.set_volume(min(1.0, self.app.playback.engine.volume + 0.1))

    def act_volume_down(self):
        self.app.playback.set_volume(max(0.0, self.app.playback.engine.volume - 0.1))

    def act_mute(self):
        self.app.playback.mute()

    def act_shuffle(self):
        self.app.playback.set_shuffle(not self.app.playback.queue.shuffle)

    def act_shuffle_set(self, on):
        self.app.playback.set_shuffle(on == "1")

    def act_shuffle_by(self, by):
        self.app.playback.set_shuffle(True, by)

    def act_repeat(self, mode):
        self.app.playback.set_repeat(mode)

    def act_repeat_cycle(self):
        q = self.app.playback.queue
        self.app.playback.set_repeat({"off": "all", "all": "one", "one": "off"}[q.repeat])

    def act_play_next(self):
        ids = self.selected_ids()
        self.app.playback.queue.play_next(ids)
        return ids

    def act_add_up_next(self):
        ids = self.selected_ids()
        self.app.playback.queue.add(ids)
        return ids

    def act_clear_up_next(self):
        self.app.playback.queue.clear_up_next()

    def act_eject(self):
        if self.cd_device:
            cd.eject(self.cd_device)
            self.cd_info = None
            self.cd_device = None if not self.cd_device.startswith("fake:") else self.cd_device
            self._ejected = True
            self.fill_sources()
            if self.source[0] == "cd":
                self.select_source("music")
            return True
        return False

    # ---- Advanced
    def act_open_stream(self):
        from . import dialogs
        url = dialogs.ask_text(self, "Open Stream", "Address of the stream (http://… or https://…):", "")
        if url and "://" in url:
            self.app.playback.play_uri(url.strip())
            return url.strip()

    def act_refresh_podcasts(self):
        self.podview.refresh_all()

    def act_import_cd(self):
        from . import dialogs
        if not self.cd_info:
            self.info("There's no audio CD in the drive.")
            return None
        return dialogs.import_cd(self)

    def act_get_track_names(self):
        if not self.cd_info:
            self.info("There's no audio CD in the drive.")
            return None
        from . import net
        if not self.cd_info.get("discid"):
            self.info("This disc can't be looked up.")
            return None
        self.lcd.set_busy("Getting track names…")

        def got(found):
            self.lcd.set_busy(None)
            if not found:
                self.info("No track names were found for this CD.")
                return
            self.cd_info.update({k: found[k] for k in ("album", "artist", "year", "disc_no", "disc_count")})
            self.cd_info["tracks"] = (found["tracks"] + [{}] * len(self.cd_info["lengths"]))[:len(self.cd_info["lengths"])]
            self.fill_sources()
            if self.source[0] == "cd":
                self.fill_cd()

        def fail(e):
            self.lcd.set_busy(None)
            self.info("Track names couldn't be looked up: %s" % e)
        net.in_thread(lambda: cd.lookup(self.cd_info["discid"]), got, fail)
        return True

    def act_get_artwork(self):
        """Covers for the selected songs' albums that have none, from the Cover Art Archive."""
        rows = [r for r in self.selected_rows() if not r["has_art"]]
        if not rows:
            self.info("The selected songs already have artwork." if self.selected_rows() else "Select songs first.")
            return None
        albums = {}
        for r in rows:
            albums.setdefault((r["album"] or "", r["album_artist"] or r["artist"] or ""), []).append(r)
        from . import net
        self.lcd.set_busy("Getting album artwork…")

        def work():
            got = {}
            for key in albums:
                try:
                    data = cd.find_artwork(*key)
                except Exception:       # noqa: BLE001
                    data = None
                if data:
                    got[key] = data
            return got

        def done(got):
            self.lcd.set_busy(None)
            n = 0
            for key, data in got.items():
                for r in albums[key]:
                    try:
                        from . import tags
                        tags.set_artwork(r["path"], data)
                        self.lib.add_file(r["path"])
                        n += 1
                    except Exception:       # noqa: BLE001
                        pass
            art._cache.clear()
            self.lib.changed()
            self.last_artwork = n
            if len(got) < len(albums):
                self.info("Artwork was found for %d of %d albums." % (len(got), len(albums)))

        def fail(e):
            self.lcd.set_busy(None)
            self.info("Artwork couldn't be looked up: %s" % e)
        net.in_thread(work, done, fail)
        return list(albums)

    def act_convert(self, fmt):
        from . import dialogs
        rows = self.selected_rows()
        if not rows:
            self.info("Select the songs to convert first.")
            return None
        return dialogs.convert(self, rows, fmt)

    # ---- Window and Help
    def act_minimize(self):
        self.iconify()

    def act_zoom(self):
        if self.is_maximized():
            self.unmaximize()
        else:
            self.maximize()

    def act_equalizer(self):
        from . import extras
        if self.eq_win is None:
            self.eq_win = extras.Equalizer(self)
        self.eq_win.show_all()
        self.eq_win.present()
        return self.eq_win

    def act_front(self):
        if self.mini:
            self.mini.hide()
        self.show()
        self.present()

    def act_shortcuts(self):
        from . import dialogs
        return dialogs.shortcuts(self)

    def act_pod(self, what):
        return self.podview.act(what)

    def act_radio(self, what):
        return self.radioview.act(what)

    def act_about(self):
        from . import dialogs
        return dialogs.about(self, VERSION)
