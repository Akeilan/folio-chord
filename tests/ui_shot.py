import os, sys, time
sys.path.insert(0, os.environ["FOLIO_TESTS"])
import mkaudio, themecheck
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
win.add_paths([d])
win.load_songs()
pump(0.5)
win.songs.view.set_cursor(Gtk.TreePath.new_from_indices([1]))
win.run("play-selection")
pump(1.0)
out = os.environ.get("UI_OUT", "/tmp/ui_out"); os.makedirs(out, exist_ok=True)
themecheck.save(win, out + "/main_%s.png" % os.environ.get("FOLIO_THEME"))
win.run("view:grid"); pump(0.5)
themecheck.save(win, out + "/grid_%s.png" % os.environ.get("FOLIO_THEME"))
win.run("view:list")
win.select_source("podcasts"); pump(0.4)
themecheck.save(win, out + "/pods_%s.png" % os.environ.get("FOLIO_THEME"))
print("shots done")
sys.stdout.flush()
os._exit(0)
