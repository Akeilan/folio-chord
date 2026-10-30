# C3-27..C3-34: Chordamp, the classic small-player look — switching to it and back from the View
# menu, the player window (transport, time, title, kbps/kHz, visualizer, volume, balance, shuffle,
# repeat, EQ and PL buttons), the equalizer, the playlist editor, the media library, docking and
# snapping, shade mode, double size, always on top, the keys, and classic .wsz skins.
import os
import sys
import zipfile

sys.path.insert(0, os.environ["FOLIO_TESTS"])
from uicommon import OUT, answer, check, music, pump, run, shot, wait  # noqa: E402
from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402
from folio_chord import classic, skin as skinmod  # noqa: E402


def key(ca, keyval, state=0):
    e = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    e.keyval = keyval
    e.state = state
    return ca.key(e)


def px(win, x, y):
    import themecheck
    img, w, h, stride, data = themecheck._grab(win)
    return themecheck._px(data, stride, x, y)


def cur_file(w=16, h=16, hot=(3, 5)):
    """A small Windows .cur (32-bit, magenta) with the given hot spot."""
    import struct
    pixels = b"\xff\x00\xff\xff" * (w * h)
    mask = b"\x00" * (((w + 31) // 32) * 4 * h)
    bih = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(pixels) + len(mask), 0, 0, 0, 0)
    img = bih + pixels + mask
    head = struct.pack("<HHH", 0, 2, 1) + struct.pack("<BBBBHHII", w, h, 0, 0, hot[0], hot[1], len(img), 22)
    return head + img


def solid_bmp(w, h, rgb):
    pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, w, h)
    pb.fill((rgb[0] << 24) | (rgb[1] << 16) | (rgb[2] << 8) | 0xff)
    ok, data = pb.save_to_bufferv("bmp", [], [])
    return bytes(data)


def main():
    w = win  # noqa: F821
    a = app  # noqa: F821
    pb = a.playback
    s = w.settings
    d, songs = music(w, secs=4.0)
    labels = [lab for lab, _c in w.commands]
    check("Standard" in labels and "Chordamp" in labels, "View > Look has Standard and Chordamp")
    # ---- switch to Chordamp
    ca = w.run("look:classic")
    pump(0.5)
    check(isinstance(ca, classic.Chordamp) and ca.shown(ca.main), "View > Look > Chordamp opens the Chordamp player")
    check(not w.get_visible(), "the Standard window steps aside")
    check(s["look"] == "classic", "the look is remembered")
    check(ca.shown(ca.eq) and ca.shown(ca.pl), "the equalizer and playlist editor open with it")
    a1 = ca.main.area.get_allocation()
    check((a1.width, a1.height) == (275, 116), "the player is the classic size", (a1.width, a1.height))
    if ca.stack is None:
        mx, my = ca.main.get_position()
        ex, ey = ca.eq.get_position()
        check(ey == my + 116 and ex == mx, "the equalizer docks under the player", ((mx, my), (ex, ey)))
        check(set(ca.docked_to(ca.main)) == {ca.eq, ca.pl}, "the three windows are docked together")
    else:
        sa = ca.stack.get_allocation()
        check(ca.stack.get_visible() and sa.height >= 116 * 2 + 116, "Wayland: the three dock in one window", (sa.width, sa.height))
    opts = [e[0] for e in ca.options_entries() if e]
    check("Standard Look" in opts and "Skins" in opts and "Double Size" in opts, "the options menu has the way back", opts)
    # ---- play from the media library
    lw = ca.show_library()
    pump(0.3)
    check(len(lw.store) == len(songs), "the library lists the music", len(lw.store))
    lw.list.get_selection().select_path(Gtk.TreePath.new_from_indices([1]))
    lw.play()
    ok = wait(lambda: pb.engine.state == "playing", 5)
    check(ok and pb.now["title"] == lw.store[1][0], "the library plays what you pick")
    check(len(pb.queue.source) == len(songs), "the playlist editor holds the list", len(pb.queue.source))
    t = ca.title_text()
    check(t.startswith("2. ") and pb.now["title"] in t, "the title shows number, artist and song", t)
    info = ca.stream_info()
    check(info[0].strip().isdigit() and info[1].isdigit() and info[2] in (1, 2), "kbps, kHz and mono/stereo are shown", info)
    wait(lambda: any(ca.main.bars), 3)
    check(any(ca.main.bars), "the spectrum moves with the music")
    shot(ca.main.area, "classic_main")
    shot(ca.eq.area, "classic_eq")
    shot(ca.pl.area, "classic_pl")
    shot(lw, "classic_library")
    # ---- transport: buttons and keys
    ca.main.click("pause")
    wait(lambda: pb.engine.state == "paused", 3)
    check(pb.engine.state == "paused", "the pause button")
    ca.main.click("play")
    wait(lambda: pb.engine.state == "playing", 3)
    check(pb.engine.state == "playing", "the play button resumes")
    before = pb.now["title"]
    ca.main.click("next")
    wait(lambda: pb.now and pb.now["title"] != before, 3)
    check(pb.now["title"] != before, "the next button")
    key(ca, Gdk.KEY_z)
    wait(lambda: pb.now and pb.now["title"] == before, 3)
    check(pb.now["title"] == before, "Z goes back")
    key(ca, Gdk.KEY_c)
    wait(lambda: pb.engine.state == "paused", 3)
    check(pb.engine.state == "paused", "C pauses")
    key(ca, Gdk.KEY_x)
    wait(lambda: pb.engine.state == "playing", 3)
    check(pb.engine.state == "playing", "X plays")
    key(ca, Gdk.KEY_v)
    wait(lambda: pb.engine.state == "stopped", 3)
    check(pb.engine.state == "stopped", "V stops")
    key(ca, Gdk.KEY_x)
    wait(lambda: pb.engine.state == "playing", 3)
    check(pb.engine.state == "playing", "X starts again after stop")
    key(ca, Gdk.KEY_b)
    pump(0.3)
    check(pb.engine.state == "playing", "B moves on")
    # ---- shuffle, repeat, volume, balance, seeking
    sh = pb.queue.shuffle
    ca.main.click("shuffle")
    check(pb.queue.shuffle != sh, "the shuffle button")
    ca.main.click("shuffle")
    ca.main.click("repeat")
    check(pb.queue.repeat == "all", "the repeat button")
    ca.main.click("repeat")
    check(pb.queue.repeat == "off", "repeat off again")
    ca.main.slide("volume", 107 + 7 + 27, 60)
    check(abs(pb.engine.volume - 0.5) < 0.03, "the volume slider", pb.engine.volume)
    v = pb.engine.volume
    key(ca, Gdk.KEY_Up)
    check(pb.engine.volume > v, "Up turns it up")
    ca.main.slide("balance", 177 + 7 + 12 + 12, 60)
    check(pb.engine.balance == 1.0, "the balance slider", pb.engine.balance)
    pan = pb.engine.cur.pan
    check(pan is not None and abs(pan.get_property("panorama") - 1.0) < 0.01, "the balance reaches the sound")
    ca.main.slide("balance", 177 + 7 + 12 + 1, 60)
    check(pb.engine.balance == 0.0, "the balance snaps to the middle")
    wait(lambda: pb.engine.duration() > 0, 3)
    ca.main.slide("pos", 16 + 14 + 110, 75)
    ca.main.slide_done("pos", 0, 0)
    pump(0.3)
    check(pb.engine.position() >= pb.engine.duration() * 0.35, "the position bar seeks", (pb.engine.position(), pb.engine.duration()))
    ca.main.click("time")
    check(ca.main.show_left, "clicking the time shows the time left")
    ca.main.click("vis")
    check(s["classic_vis"] == "oscilloscope", "clicking the visualizer changes it")
    wait(lambda: pb.engine.scope and max(pb.engine.scope) > 1000, 3)
    wave = pb.engine.scope
    check(wave and max(wave) > 1000 and min(wave) < -1000, "C3-35: the oscilloscope gets the real waveform",
          (len(wave or []), max(wave or [0]), min(wave or [0])))
    pump(0.3)
    shot(ca.main.area, "classic_osc")
    ca.set_vis("spectrum")
    check(pb.engine.scope is None, "and stops taking it when the oscilloscope is off")
    # ---- equalizer
    on = s["eq_on"]
    ca.eq.click("on")
    check(s["eq_on"] != on and pb.engine.eq_on == s["eq_on"], "the equalizer's ON button")
    ca.load_preset("Rock")
    check(s["eq_on"] and list(s["eq_bands"]) == list(a.eq_preset("Rock")[1]), "presets load into the sliders")
    ca.eq.slide("band3", 0, 38)
    check(s["eq_bands"][3] == 12.0 and s["eq_preset"] == "Manual", "the sliders move the bands", s["eq_bands"])
    check(abs(pb.engine.cur.eq.get_property("band3") - 12.0) < 0.01, "and the sound")
    ca.eq.click("auto")
    check(pb.engine.auto_eq is False and s["eq_auto"] is False, "AUTO turns songs' own presets off")
    ca.eq.click("auto")
    ca.eq.click("close")
    check(not ca.shown(ca.eq) and not s["classic_eq"], "the equalizer closes")
    ca.main.click("eqbtn")
    check(ca.shown(ca.eq), "the EQ button opens it again")
    key(ca, Gdk.KEY_g, Gdk.ModifierType.MOD1_MASK)
    check(not ca.shown(ca.eq), "Alt+G toggles it")
    key(ca, Gdk.KEY_g, Gdk.ModifierType.MOD1_MASK)
    # ---- playlist editor
    q = pb.queue
    n = len(q.source)
    first = q.source[0]
    ca.pl.sel = {0}
    ca.move_rows([0], 2, ca.pl)
    check(q.source[2] == first and ca.pl.sel == {2}, "songs can be moved in the list")
    cur_before = q.current
    ca.sort("title")
    names = [classic.item_name(ca, k).split(" - ", 1)[1].lower() for k in q.source]
    check(names == sorted(names), "Misc > Sort by Title", names)
    check(q.current == cur_before, "sorting doesn't stop the music")
    ca.sort("reverse")
    check([classic.item_name(ca, k).split(" - ", 1)[1].lower() for k in q.source] == sorted(names, reverse=True), "Misc > Reverse List")
    ca.select("all")
    check(ca.pl.sel == set(range(n)), "Select All")
    ca.select("invert")
    check(ca.pl.sel == set(), "Invert Selection")
    m3u = os.path.join(OUT, "classic.m3u")
    ca.save_list(m3u)
    check(open(m3u).read().count("#EXTINF") == n, "List > Save List writes an m3u")
    ca.pl.sel = {0, 1}
    ca.remove_selected()
    check(len(q.source) == n - 2, "Remove Selected")
    ca.pl.sel = {0}
    ca.crop()
    check(len(q.source) == 1, "Crop keeps only the selection")
    ca.remove_all()
    check(q.source == [], "Remove All")
    ids = ca.load_list(m3u)
    check(len(ids) == n and len(q.source) == n, "List > Open List reads it back", len(ids))
    ids = ca.add_files([songs[list(songs)[0]]])
    check(len(q.source) == n + 1, "Add File appends to the list")
    ca.pl.sel = {n}
    ca.remove_selected()

    def jump(dlg):
        dlg.entry.set_text(list(songs)[3].split()[0])
        dlg.refill()
        return Gtk.ResponseType.OK
    answer("Jump to File", jump)
    i = key(ca, Gdk.KEY_j)
    pump(0.4)
    check(pb.now and pb.now["title"] == list(songs)[3], "J jumps to a song by name", pb.now and pb.now["title"])
    # ---- C3-38 Up Next in the playlist editor
    q = pb.queue
    ci = q.current_index()
    queued = q.source[0] if ci != 0 else q.source[1]
    q.add([queued])
    pump(0.7)
    rows = ca.pl.rows()
    d = ca.pl.display_index(ci)
    check(rows[d + 1][0] == "next" and rows[d + 1][2] == queued, "Up Next shows right after the song playing", rows[d:d + 2])
    shot(ca.pl.area, "classic_upnext")
    ca.pl.sel_next = {0}
    ca.remove_selected()
    check(q.up_next == [], "and can be taken out again")
    q.add([queued])
    ca.play_up_next(0)
    wait(lambda: pb.now and pb.now["id"] == queued, 3)
    check(pb.now["id"] == queued and q.up_next == [], "double-clicking it plays it now")
    # ---- C3-37 balance in the Standard look
    eqw = w.run("equalizer")
    eqw.balance.set_value(-0.5)
    check(pb.engine.balance == -0.5 and s["balance"] == -0.5, "Equalizer: the balance slider in Standard")
    ca.set_balance(0.3)
    check(abs(eqw.balance.get_value() - 0.3) < 0.01, "and it follows Chordamp's")
    eqw.balance.set_value(0.02)
    check(pb.engine.balance == 0.0, "it snaps to the middle")
    eqw.hide()
    ca.active_part = ca.pl
    pump(0.2)
    shot(ca.pl.area, "classic_pl2")
    ca.pl.slide("grip", 0, 400)
    check(ca.pl.size()[1] > 232, "the playlist editor can be made taller", ca.pl.size())
    # ---- shade, double size, always on top
    ca.toggle_shade()
    pump(0.3)
    check(ca.main.area.get_allocation().height == 14, "shade mode rolls the player up", ca.main.area.get_allocation().height)
    shot(ca.main.area, "classic_shade")
    ca.main.double(100, 5)
    pump(0.3)
    check(ca.main.area.get_allocation().height == 116, "double-clicking the title bar rolls it down")
    key(ca, Gdk.KEY_d, Gdk.ModifierType.CONTROL_MASK)
    pump(0.4)
    a2 = ca.main.area.get_allocation()
    check((a2.width, a2.height) == (550, 232) and s["classic_double"], "Ctrl+D: double size", (a2.width, a2.height))
    shot(ca.main.area, "classic_double")
    key(ca, Gdk.KEY_d, Gdk.ModifierType.CONTROL_MASK)
    pump(0.3)
    check(ca.main.area.get_allocation().width == 275, "and back")
    key(ca, Gdk.KEY_t, Gdk.ModifierType.CONTROL_MASK)
    check(s["classic_ontop"], "Ctrl+T: always on top")
    key(ca, Gdk.KEY_t, Gdk.ModifierType.CONTROL_MASK)
    # ---- snapping
    if ca.stack is None:
        mx, my = ca.main.get_position()
        sx, sy = ca.snap(ca.pl, mx + 4, my + 116 + 6, ())
        check((sx, sy) == (mx, my + 116) or sy in (my + 116, my + 232), "windows snap to each other", ((mx, my), (sx, sy)))
    check(classic.Chordamp.touching((0, 0, 275, 116), (0, 116, 275, 116)), "touching windows count as docked")
    check(not classic.Chordamp.touching((0, 0, 275, 116), (0, 140, 275, 116)), "apart windows don't")
    # ---- skins
    wsz = os.path.join(OUT, "green.wsz")
    with zipfile.ZipFile(wsz, "w") as z:
        z.writestr("Main.bmp", solid_bmp(275, 116, (0, 160, 0)))
        z.writestr("viscolor.txt", "\n".join("0,%d,0, // c%d" % (i * 10, i) for i in range(24)))
        z.writestr("pledit.txt", "[Text]\nNormal=#00FF00\nCurrent=#FFFFFF\nNormalBG=#002000\nSelectedBG=#0000C0\nFont=Sans\n")
        z.writestr("text.bmp", solid_bmp(155, 18, (0, 255, 0)))
        # a cut-off corner (C3-36): the player is a five-sided shape; the equalizer a smaller box
        z.writestr("region.txt", "[Normal]\nNumPoints=5\nPointList=0,0, 260,0, 275,15, 275,116, 0,116\n"
                                 "[Equalizer]\nNumPoints=4\nPointList=0,0 275,0 275,100 0,100\n")
        z.writestr("Normal.cur", cur_file(hot=(3, 5)))
        z.writestr("CLOSE.CUR", cur_file(hot=(8, 8)))
    name = ca.load_skin(wsz)
    pump(0.3)
    check(name == "green.wsz" and s["skin"] == "green.wsz", "a classic skin loads", name)
    check(ca.skin.pl["normal"] == (0.0, 1.0, 0.0) and ca.skin.text_font == "text", "with its playlist colours and font")
    c = px(ca.main.area, 150, 108)
    check(c[1] > 140 and c[0] < 30, "the player wears it", c)
    check("green.wsz" in skinmod.installed(), "it is kept with the skins")
    if ca.stack is None:
        rg = ca.main.shape
        check(rg is not None and not rg.contains_point(272, 2) and rg.contains_point(100, 50) and rg.contains_point(272, 100),
              "C3-36: the skin's region.txt shapes the player window")
        check(ca.eq.shape is not None and not ca.eq.shape.contains_point(10, 110), "and the equalizer")
    pb_, hx, hy = ca.skin.cursors["normal"]
    check((hx, hy) == (3, 5) and pb_.get_width() == 16 and "close" in ca.skin.cursors, "its own mouse pointers load, with hot spots")
    ca.main.update_cursor(100, 60)
    gw = ca.main.area.get_window()
    check(gw is not None and gw.get_cursor() is not None and ca.main._cursor_name == "normal", "and are used over the player")
    ca.main.update_cursor(266, 5)
    check(ca.main._cursor_name == "close" and gw.get_cursor() is ca.cursor("close"), "a different one over the close button")
    shot(ca.main.area, "classic_skin")
    shot(ca.pl.area, "classic_skin_pl")
    out = ca.export_skin(os.path.join(OUT, "Chordamp.wsz"))
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
    check({"main.bmp", "cbuttons.bmp", "pledit.bmp", "eqmain.bmp", "viscolor.txt"} <= names, "Chordamp's own skin can be saved as a .wsz", names)
    check(skinmod.load_wsz(out).has("cbuttons"), "and read back")
    ca.set_skin("")
    pump(0.2)
    check(ca.main.shape is None and ca.main.area.get_window().get_cursor() is None, "Chordamp's own skin: plain shape, the desktop's pointer")
    c = px(ca.main.area, 150, 108)
    check(not (c[1] > 140 and c[0] < 30), "Skins > Chordamp goes back to Chordamp's own")
    # ---- back to Standard
    key(ca, Gdk.KEY_w, Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK)
    pump(0.4)
    check(w.get_visible() and not ca.shown(ca.main) and not ca.shown(ca.pl), "Ctrl+Shift+W goes back to Standard")
    check(s["look"] == "standard", "Standard is remembered")
    check(pb.engine.state == "playing", "the music carries on through the switch")
    w.run("look:classic")
    pump(0.3)
    check(ca.shown(ca.main) and not w.get_visible(), "and Chordamp again")
    ca.options_entries()[0][1]()
    pump(0.3)
    check(w.get_visible() and not ca.shown(ca.main), "Options > Standard Look")
    w.run("stop")


run(main)
