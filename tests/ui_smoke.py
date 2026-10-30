import os
import sys
print("window", win.get_title(), "source", win.source, "commands", len(win.commands))
win.run("view:grid")
win.run("view:albums")
win.run("view:list")
for k in ("podcasts", "radio", "music"):
    win.select_source(k)
print("ok")
sys.stdout.flush()
os._exit(0)
