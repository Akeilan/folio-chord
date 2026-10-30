"""Watching the music folders (C3-14): files added, changed, renamed or deleted there show up in
the library straight away. One monitor per folder (the system watches folders, not trees); a
burst of changes is handled together a moment after it ends."""
import os

from gi.repository import Gio, GLib

from . import tags


class Watcher:
    def __init__(self, lib, on_change=None, delay_ms=1500):
        self.lib = lib
        self.on_change = on_change
        self.delay = delay_ms
        self.monitors = {}
        self.pending = set()
        self.gone = set()
        self._timer = None
        self.paused = False

    def watch(self, roots):
        for r in roots:
            if os.path.isdir(r):
                for d, dirs, _files in os.walk(r):
                    dirs[:] = [x for x in dirs if not x.startswith(".")]
                    self._add(d)

    def _add(self, d):
        if d in self.monitors:
            return
        try:
            m = Gio.File.new_for_path(d).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
        except GLib.Error:
            return
        m.connect("changed", self._changed)
        self.monitors[d] = m

    def stop(self):
        for m in self.monitors.values():
            m.cancel()
        self.monitors = {}

    def _changed(self, mon, f, other, ev):
        if self.paused:
            return
        E = Gio.FileMonitorEvent
        p = f.get_path()
        if p is None:
            return
        if ev in (E.CREATED, E.CHANGES_DONE_HINT, E.MOVED_IN, E.ATTRIBUTE_CHANGED):
            self.pending.add(p)
        elif ev in (E.DELETED, E.MOVED_OUT):
            self.gone.add(p)
        elif ev == E.RENAMED:
            self.gone.add(p)
            if other is not None and other.get_path():
                self.pending.add(other.get_path())
        else:
            return
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(self.delay, self._flush)

    def _flush(self):
        self._timer = None
        pending, gone = self.pending, self.gone
        self.pending, self.gone = set(), set()
        changed = False
        for p in sorted(pending):
            if os.path.isdir(p):
                self.watch([p])
                for d, dirs, files in os.walk(p):
                    for fn in files:
                        if tags.is_audio(fn) and self.lib.add_file(os.path.join(d, fn), commit=False):
                            changed = True
            elif tags.is_audio(p) and os.path.exists(p):
                if self.lib.add_file(p, commit=False):
                    changed = True
        for p in gone:
            if os.path.exists(p):
                continue
            pre = p.rstrip("/") + "/"
            rows = self.lib.q("select id from tracks where (path=? or path like ?) and not missing",
                              (p, pre.replace("%", "\\%") + "%"))
            if rows:
                with self.lib.lock:
                    for r in rows:
                        self.lib.db.execute("update tracks set missing=1 where id=?", (r["id"],))
                changed = True
            m = self.monitors.pop(p, None)
            if m:
                m.cancel()
        if changed:
            with self.lib.lock:
                self.lib.db.commit()
            self.lib.changed()
            if self.on_change:
                self.on_change()
        return False
