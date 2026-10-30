import os, sys, time, subprocess
sys.path.insert(0, os.environ["FOLIO_TESTS"])
import mkaudio
from gi.repository import Gtk
def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.005)
d = "/tmp/chord_music"
if not os.path.exists(d):
    mkaudio.make(d)
win.add_paths([d]); win.load_songs(); win.move(0, 0); pump(1.5)
from gi.repository import Gdk
w = Gdk.get_default_root_window()
pb = Gdk.pixbuf_get_from_window(w, 0, 0, 1200, 760)
pb.savev("/tmp/chord_ui/x_%s.png" % os.environ.get("FOLIO_THEME"), "png", [], [])
print("ok"); sys.stdout.flush(); os._exit(0)
