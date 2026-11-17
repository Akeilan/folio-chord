"""A stand-in for the file manager in the window tests: a separate program whose button drags the
files named on its command line (text/uri-list), as Files does. python3 dragsrc.py FILE..."""
import sys, gi
gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib
uris = [GLib.filename_to_uri(p, None) for p in sys.argv[1:]]
w = Gtk.Window(title="Files stand-in"); b = Gtk.Button(label="drag me"); w.add(b); w.move(1350, 200); w.set_default_size(160, 60)
b.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [Gtk.TargetEntry.new("text/uri-list", 0, 0)], Gdk.DragAction.COPY)
b.connect("drag-data-get", lambda wd, ctx, data, info, t: data.set_uris(uris))
b.connect("drag-end", lambda *a: GLib.timeout_add(300, Gtk.main_quit))
w.connect("destroy", Gtk.main_quit); w.show_all()
GLib.timeout_add_seconds(30, Gtk.main_quit)
Gtk.main()
