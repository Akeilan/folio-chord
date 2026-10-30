"""The song views (C3-01, C3-08): the striped song list with its columns, the column browser
(Genres, Artists, Albums), the album list and the grid of album covers."""
import time

from gi.repository import Gdk, GdkPixbuf, GLib, GObject, Gtk, Pango

from . import art, theme

# column key: (title, model index, width, sort index)
COLS = [
    ("checked", "", 1, 24, 1), ("track_no", "#", 2, 34, 19), ("title", "Name", 3, 230, 3),
    ("duration", "Time", 4, 52, 11), ("artist", "Artist", 5, 160, 5), ("album", "Album", 6, 170, 6),
    ("genre", "Genre", 7, 100, 7), ("rating", "Rating", 8, 80, 12), ("play_count", "Plays", 9, 48, 13),
    ("year", "Year", 10, 48, 14), ("album_artist", "Album Artist", 15, 140, 15), ("composer", "Composer", 16, 130, 16),
    ("kind", "Kind", 17, 120, 17), ("bitrate", "Bit Rate", 18, 70, 20), ("date_added", "Date Added", 21, 120, 22),
    ("last_played", "Last Played", 23, 120, 24), ("comments", "Comments", 25, 150, 25),
]
COL = {c[0]: c for c in COLS}
#        0 id, 1 checked, 2 num, 3 title, 4 time, 5 artist, 6 album, 7 genre, 8 stars, 9 plays, 10 year,
#        11 duration(f), 12 rating(i), 13 plays(i), 14 year(i), 15 album artist, 16 composer, 17 kind, 18 bitrate,
#        19 track(i), 20 bitrate(i), 21 date added, 22 added(f), 23 last played, 24 last(f), 25 comments, 26 order(i),
#        27 playing(bool)
TYPES = [int, bool, str, str, str, str, str, str, str, str, str, float, int, int, int, str, str, str, str, int, int,
         str, float, str, float, str, int, bool]


def fmt_time(secs):
    secs = int(round(secs or 0))
    if secs >= 3600:
        return "%d:%02d:%02d" % (secs // 3600, secs // 60 % 60, secs % 60)
    return "%d:%02d" % (secs // 60, secs % 60)


def fmt_date(t):
    return time.strftime("%d-%m-%Y %H:%M", time.localtime(t)) if t else ""


def stars(rating):
    n = int(round((rating or 0) / 20.0))
    return "★" * n + "·" * (5 - n) if n else "·····"


class SongList(Gtk.ScrolledWindow):
    """A list of songs. Signals: play(index), changed()."""
    __gsignals__ = {"play": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
                    "context": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    "selection": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, win, columns):
        super().__init__()
        self.win = win
        self.lib = win.app.lib
        self.rows = []
        self.playlist = None        # id of a plain playlist, when showing one (then rows can be reordered)
        self.store = Gtk.ListStore(*TYPES)
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_name("chord-songs")
        self.view.set_rubber_banding(True)
        self.view.set_enable_search(False)
        self.view.set_headers_clickable(True)
        self.view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.view.connect("row-activated", lambda v, p, c: self.emit("play", self._index(p)))
        self.view.connect("button-press-event", self._press)
        self.view.connect("key-press-event", self._key)
        self.view.get_selection().connect("changed", lambda s: self.emit("selection"))
        self.add(self.view)
        self.columns = {}
        self.set_columns(columns)
        # drag songs onto playlists, and within a playlist to reorder it
        t = [Gtk.TargetEntry.new("application/x-chord-tracks", Gtk.TargetFlags.SAME_APP, 1)]
        self.view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, t, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        self.view.enable_model_drag_dest(t, Gdk.DragAction.MOVE)
        self.view.connect("drag-data-get", self._drag_get)
        self.view.connect("drag-data-received", self._drag_received)

    # ---------------------------------------------------------------- columns
    def set_columns(self, keys):
        for c in list(self.view.get_columns()):
            self.view.remove_column(c)
        self.columns = {}
        playing = Gtk.TreeViewColumn("")
        pr = Gtk.CellRendererPixbuf()
        playing.pack_start(pr, False)
        playing.set_cell_data_func(pr, self._playing_cell)
        playing.set_fixed_width(20)
        playing.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        self.view.append_column(playing)
        for k in keys:
            if k not in COL:
                continue
            key, title, idx, width, sort = COL[k]
            if key == "checked":
                r = Gtk.CellRendererToggle()
                r.set_activatable(True)
                r.connect("toggled", self._toggled)
                col = Gtk.TreeViewColumn(title, r, active=idx)
                col.set_cell_data_func(r, self._stripe)
            else:
                r = Gtk.CellRendererText()
                r.set_property("ellipsize", Pango.EllipsizeMode.END)
                if key in ("duration", "play_count", "track_no", "bitrate", "year"):
                    r.set_property("xalign", 1.0)
                col = Gtk.TreeViewColumn(title, r, text=idx)
                col.set_resizable(True)
                col.set_cell_data_func(r, self._stripe)
            col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            col.set_fixed_width(width)
            col.set_sort_column_id(sort)
            col.key = key
            self.columns[key] = col
            self.view.append_column(col)
        last = Gtk.TreeViewColumn("")
        rr = Gtk.CellRendererText()
        last.pack_start(rr, True)
        last.set_cell_data_func(rr, self._stripe)
        last.set_expand(True)
        self.view.append_column(last)

    def _stripe(self, col, cell, model, it, data=None):
        path = model.get_path(it)
        sel = self.view.get_selection().iter_is_selected(it)
        c = theme.colours(self.win.dark)
        if sel:
            cell.set_property("cell-background-set", False)
            if isinstance(cell, Gtk.CellRendererText):
                cell.set_property("foreground", c["sel_fg"])
        else:
            if path.get_indices()[0] % 2:
                cell.set_property("cell-background", c["stripe"])
                cell.set_property("cell-background-set", True)
            else:
                cell.set_property("cell-background-set", False)
            if isinstance(cell, Gtk.CellRendererText):
                cell.set_property("foreground", c["star"] if getattr(col, "key", "") == "rating" and model[it][12] else
                                  c["star_off"] if getattr(col, "key", "") == "rating" else c["list_fg"])
        if isinstance(cell, Gtk.CellRendererText):
            cell.set_property("weight", Pango.Weight.BOLD if model[it][27] else Pango.Weight.NORMAL)

    def _playing_cell(self, col, cell, model, it, data=None):
        cell.set_property("icon-name", "chord-volume-high-symbolic" if model[it][27] else None)
        self._stripe(col, cell, model, it)

    # ---------------------------------------------------------------- rows
    def set_rows(self, rows, playlist=None, keep_sort=True):
        sort = self.store.get_sort_column_id() if keep_sort else (None, None)
        self.playlist = playlist
        self.rows = list(rows)
        self.store = Gtk.ListStore(*TYPES)
        playing = self.win.app.playback.now
        pid = playing["id"] if playing and playing.get("kind") == "song" else None
        for i, r in enumerate(self.rows):
            self.store.append(self._row(r, i, pid))
        self.view.set_model(self.store)
        self.view.set_reorderable(False)
        if sort and sort[0] is not None and sort[0] >= 0:
            self.store.set_sort_column_id(*sort)
        else:
            self.store.set_sort_column_id(26, Gtk.SortType.ASCENDING)

    def _row(self, r, i, playing_id):
        return [r["id"], bool(r["checked"]), str(r["track_no"] or "") if self.playlist is None else str(i + 1),
                r["title"] or "", fmt_time(r["duration"]), r["artist"] or "", r["album"] or "", r["genre"] or "",
                stars(r["rating"]), str(r["play_count"] or "") if r["play_count"] else "", str(r["year"] or "") if r["year"] else "",
                float(r["duration"] or 0), int(r["rating"] or 0), int(r["play_count"] or 0), int(r["year"] or 0),
                r["album_artist"] or "", r["composer"] or "", r["kind"] or "", "%d kbps" % r["bitrate"] if r["bitrate"] else "",
                int(r["track_no"] or 0), int(r["bitrate"] or 0), fmt_date(r["date_added"]), float(r["date_added"] or 0),
                fmt_date(r["last_played"]), float(r["last_played"] or 0), r["comments"] or "", i, r["id"] == playing_id]

    def refresh_row(self, tid):
        new = self.lib.track(tid)
        if new is None:
            return
        for i, r in enumerate(self.rows):
            if r["id"] == tid:
                self.rows[i] = new
        playing = self.win.app.playback.now
        pid = playing["id"] if playing and playing.get("kind") == "song" else None
        for row in self.store:
            if row[0] == tid:
                vals = self._row(new, row[26], pid)
                for j, v in enumerate(vals):
                    row[j] = v

    def mark_playing(self, tid):
        for row in self.store:
            row[27] = row[0] == tid

    def ids_in_order(self):
        """The songs as shown (sorted as the list is), for playing through."""
        return [row[0] for row in self.store]

    def _index(self, path):
        return path.get_indices()[0]

    def selected_ids(self):
        model, paths = self.view.get_selection().get_selected_rows()
        return [model[p][0] for p in paths]

    def selected_positions(self):
        model, paths = self.view.get_selection().get_selected_rows()
        return [model[p][26] for p in paths]

    def select_ids(self, ids, scroll=True):
        sel = self.view.get_selection()
        sel.unselect_all()
        first = None
        for row in self.store:
            if row[0] in ids:
                sel.select_path(row.path)
                first = first or row.path
        if first is not None and scroll:
            self.view.scroll_to_cell(first, None, True, 0.4, 0)
        return first is not None

    # ---------------------------------------------------------------- clicks
    def _toggled(self, cell, path):
        row = self.store[path]
        row[1] = not row[1]
        self.lib.update([row[0]], checked=1 if row[1] else 0)

    def _press(self, view, ev):
        hit = view.get_path_at_pos(int(ev.x), int(ev.y))
        if ev.button == 3:
            if hit:
                sel = view.get_selection()
                if not sel.path_is_selected(hit[0]):
                    sel.unselect_all()
                    sel.select_path(hit[0])
            self.emit("context", ev)
            return True
        if ev.button == 1 and hit and getattr(hit[1], "key", "") == "rating":
            x = hit[2]
            n = max(0, min(5, int((x - 4) / 12.0 + 1)))
            row = self.store[hit[0]]
            new = 0 if n * 20 == row[12] and n == 1 else n * 20
            self.lib.rate([row[0]], new)
            row[12] = new
            row[8] = stars(new)
            return True
        return False

    def _key(self, view, ev):
        if ev.keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace, Gdk.KEY_KP_Delete):
            self.win.run("delete")
            return True
        if ev.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            model, paths = view.get_selection().get_selected_rows()
            if paths:
                self.emit("play", paths[0].get_indices()[0])
            return True
        return False

    # ---------------------------------------------------------------- drag and drop
    def _drag_get(self, view, ctx, data, info, t):
        ids = self.selected_ids()
        data.set(Gdk.Atom.intern("application/x-chord-tracks", False), 8, (",".join(map(str, ids))).encode())

    def _drag_received(self, view, ctx, x, y, data, info, t):
        if self.playlist is None:
            ctx.finish(False, False, t)
            return
        dest = view.get_dest_row_at_pos(x, y)
        at = len(self.rows)
        if dest:
            path, pos = dest
            at = self.store[path][26] + (1 if pos in (Gtk.TreeViewDropPosition.AFTER, Gtk.TreeViewDropPosition.INTO_OR_AFTER) else 0)
        self.reorder(self.selected_positions(), at)
        ctx.finish(True, False, t)

    def reorder(self, positions, at):
        self.lib.reorder_playlist(self.playlist, positions, at)
        self.set_rows(self.lib.playlist_tracks(self.playlist), self.playlist, keep_sort=False)


class ColumnBrowser(Gtk.Box):
    """Genres | Artists | Albums above the song list. Signal: changed()."""
    __gsignals__ = {"changed": (GObject.SignalFlags.RUN_FIRST, None, ())}
    KEYS = [("genre", "Genres"), ("artist", "Artists"), ("album", "Albums")]

    def __init__(self, win):
        super().__init__(spacing=0)
        self.win = win
        self.get_style_context().add_class("chord-browser")
        self.set_homogeneous(True)
        self.lists = {}
        self.choice = {"genre": None, "artist": None, "album": None}
        self.rows = []
        self._busy = False
        for key, title in self.KEYS:
            store = Gtk.ListStore(str, str, bool)      # shown, value, the All row
            v = Gtk.TreeView(model=store)
            v.get_style_context().add_class("chord-browse")
            r = Gtk.CellRendererText()
            r.set_property("ellipsize", Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title, r, text=0)
            v.append_column(col)
            v.set_enable_search(True)
            v.get_selection().connect("changed", self._picked, key)
            sw = Gtk.ScrolledWindow()
            sw.set_size_request(-1, 150)
            sw.add(v)
            self.pack_start(sw, True, True, 0)
            self.lists[key] = (v, store)

    def _value(self, r, key):
        if key == "artist":
            return r["album_artist"] or r["artist"] or ""
        return r[key] or ""

    def set_rows(self, rows):
        self.rows = rows
        self._fill()

    def _fill(self, start="genre"):
        self._busy = True
        rows = self.rows
        order = [k for k, _t in self.KEYS]
        for key in order:
            v, store = self.lists[key]
            if order.index(key) >= order.index(start):
                vals = sorted({self._value(r, key) for r in rows}, key=lambda s: s.lower())
                store.clear()
                name = {"genre": "Genres", "artist": "Artists", "album": "Albums"}[key]
                store.append(["All (%d %s)" % (len(vals), name if len(vals) != 1 else name[:-1]), "", True])
                for x in vals:
                    store.append([x or "Unknown " + name[:-1], x, False])
                want = self.choice[key]
                sel = v.get_selection()
                found = False
                for row in store:
                    if want is not None and not row[2] and row[1] == want:
                        sel.select_path(row.path)
                        found = True
                if not found:
                    self.choice[key] = None
                    sel.select_path(Gtk.TreePath.new_first())
            if self.choice[key] is not None:
                rows = [r for r in rows if self._value(r, key) == self.choice[key]]
        self._busy = False

    def _picked(self, sel, key):
        if self._busy:
            return
        model, it = sel.get_selected()
        if it is None:
            return
        self.choice[key] = None if model[it][2] else model[it][1]
        order = [k for k, _t in self.KEYS]
        nxt = order.index(key) + 1
        if nxt < len(order):
            self._fill(order[nxt])
        self.emit("changed")

    def filter(self, rows):
        for key, _t in self.KEYS:
            if self.choice[key] is not None:
                rows = [r for r in rows if self._value(r, key) == self.choice[key]]
        return rows

    def reset(self):
        self.choice = {"genre": None, "artist": None, "album": None}


class AlbumGrid(Gtk.ScrolledWindow):
    """The albums as covers. Signals: play(album rows), open(album rows)."""
    __gsignals__ = {"play": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
                    "context": (GObject.SignalFlags.RUN_FIRST, None, (object,))}

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, object)
        self.view = Gtk.IconView(model=self.store)
        self.view.set_pixbuf_column(0)
        self.view.set_markup_column(1)
        self.view.set_item_width(140)
        self.view.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        self.view.connect("item-activated", lambda v, p: self.emit("play", self.store[p][2]))
        self.view.connect("button-press-event", self._press)
        self.add(self.view)
        self.albums = []

    def set_rows(self, rows):
        groups = {}
        for r in rows:
            k = ((r["album_artist"] or r["artist"] or "").lower(), (r["album"] or "").lower())
            groups.setdefault(k, []).append(r)
        self.albums = [groups[k] for k in sorted(groups, key=lambda k: (k[1], k[0]))]
        self.store.clear()
        ph = art.placeholder(128, self.win.dark)
        for g in self.albums:
            r = g[0]
            a = GLib.markup_escape_text(r["album"] or "Unknown Album")
            b = GLib.markup_escape_text(r["album_artist"] or r["artist"] or "Unknown Artist")
            self.store.append([art.for_song(r["path"], 128) if r["has_art"] else (art.for_song(r["path"], 128) or ph),
                               "<b>%s</b>\n<small>%s</small>" % (a, b), g])
        for row in self.store:
            if row[0] is None:
                row[0] = ph

    def selected_rows(self):
        out = []
        for p in self.view.get_selected_items():
            out += self.store[p][2]
        return out

    def _press(self, v, ev):
        if ev.button == 3:
            p = v.get_path_at_pos(int(ev.x), int(ev.y))
            if p is not None and not v.path_is_selected(p):
                v.unselect_all()
                v.select_path(p)
            self.emit("context", ev)
            return True
        return False


class AlbumList(Gtk.ScrolledWindow):
    """iTunes' album list: each album's cover beside its songs."""
    __gsignals__ = {"play": (GObject.SignalFlags.RUN_FIRST, None, (object, int)),
                    "context": (GObject.SignalFlags.RUN_FIRST, None, (object,))}

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.store = Gtk.TreeStore(GdkPixbuf.Pixbuf, str, str, str, int, object)
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_headers_visible(True)
        self.view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        c0 = Gtk.TreeViewColumn("Album")
        pr = Gtk.CellRendererPixbuf()
        c0.pack_start(pr, False)
        c0.add_attribute(pr, "pixbuf", 0)
        tr = Gtk.CellRendererText()
        tr.set_property("ellipsize", Pango.EllipsizeMode.END)
        c0.pack_start(tr, True)
        c0.add_attribute(tr, "markup", 1)
        c0.set_fixed_width(300)
        c0.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        self.view.append_column(c0)
        for title, i, w in (("Name", 2, 260), ("Time", 3, 60)):
            r = Gtk.CellRendererText()
            r.set_property("ellipsize", Pango.EllipsizeMode.END)
            c = Gtk.TreeViewColumn(title, r, text=i)
            c.set_fixed_width(w)
            c.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            self.view.append_column(c)
        self.view.append_column(Gtk.TreeViewColumn(""))
        self.view.connect("row-activated", self._activated)
        self.view.connect("button-press-event", self._press)
        self.add(self.view)

    def set_rows(self, rows):
        self.store.clear()
        groups, order = {}, []
        for r in rows:
            k = ((r["album_artist"] or r["artist"] or "").lower(), (r["album"] or "").lower())
            if k not in groups:
                groups[k] = []
                order.append(k)
            groups[k].append(r)
        ph = art.placeholder(64, self.win.dark)
        for k in order:
            g = groups[k]
            r = g[0]
            head = "<b>%s</b>\n%s\n<small>%d songs, %s</small>" % (
                GLib.markup_escape_text(r["album"] or "Unknown Album"),
                GLib.markup_escape_text(r["album_artist"] or r["artist"] or ""), len(g),
                fmt_time(sum(x["duration"] or 0 for x in g)))
            parent = self.store.append(None, [art.for_song(r["path"], 64) or ph, head, "", "", -1, g])
            for i, x in enumerate(g):
                self.store.append(parent, [None, "", "%s%s" % ("%d. " % x["track_no"] if x["track_no"] else "", x["title"] or ""),
                                           fmt_time(x["duration"]), i, g])
        self.view.expand_all()

    def _activated(self, v, path, col):
        row = self.store[path]
        self.emit("play", row[5], max(0, row[4]))

    def selected_rows(self):
        model, paths = self.view.get_selection().get_selected_rows()
        out, seen = [], set()
        for p in paths:
            row = model[p]
            items = row[5] if row[4] < 0 else [row[5][row[4]]]
            for x in items:
                if x["id"] not in seen:
                    seen.add(x["id"])
                    out.append(x)
        return out

    def _press(self, v, ev):
        if ev.button == 3:
            hit = v.get_path_at_pos(int(ev.x), int(ev.y))
            if hit and not v.get_selection().path_is_selected(hit[0]):
                v.get_selection().unselect_all()
                v.get_selection().select_path(hit[0])
            self.emit("context", ev)
            return True
        return False
