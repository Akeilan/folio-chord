# C3-01, C3-03, C3-04, C3-08: the library in the window — folders, column browser, search, views,
# sorting, ratings, check boxes, Get Info, playlists, Smart Playlists, View Options, deleting.
import os
import sys

sys.path.insert(0, os.environ["FOLIO_TESTS"])
from uicommon import answer, check, music, pump, run, shot, wait  # noqa: E402
from gi.repository import Gtk  # noqa: E402
from folio_chord import dialogs, library, tags  # noqa: E402


def main():
    lib = app.lib  # noqa: F821
    w = win  # noqa: F821
    d, songs = music(w)
    check(len(w.rows) == 7 and w.status.get_text().startswith("7 songs"), "songs from the added folder; status line", w.status.get_text())
    check(d in w.settings["music_folders"], "the folder is watched from now on")
    # column browser
    v, store = w.browser.lists["genre"]
    check([r[0] for r in store] == ["All (3 Genres)", "Classical", "Jazz", "Rock"], "column browser: genres with All")
    v.get_selection().select_path(Gtk.TreePath.new_from_indices([2]))
    pump(0.2)
    check(len(w.rows) == 4 and {r["genre"] for r in w.rows} == {"Jazz"}, "pick a genre: only its songs")
    av, astore = w.browser.lists["artist"]
    check([r[0] for r in astore] == ["All (1 Artist)", "Coltrane Quartet"], "artists narrow to the genre")
    v.get_selection().select_path(Gtk.TreePath.new_first())
    pump(0.2)
    check(len(w.rows) == 7, "All again")
    w.run("toggle-browser")
    check(not w.browser_box.get_visible(), "hide the column browser (Ctrl+B)")
    w.run("toggle-browser")
    # search
    w.search.set_text("garage")
    pump(0.4)
    check(sorted(r["title"] for r in w.rows) == ["Grunge Waltz", "Teen Spirit Cover"], "search by artist")
    w.search.set_text("night blue")
    pump(0.4)
    check([r["title"] for r in w.rows] == ["Blue Train"], "search with two words")
    w.search.set_text("")
    pump(0.4)
    # views
    w.run("view:albums")
    check(w.songview.get_visible_child_name() == "albums" and len(w.albumlist.store) == 3, "album list: three albums")
    w.run("view:grid")
    check(w.songview.get_visible_child_name() == "grid" and len(w.grid.store) == 3, "grid of album covers")
    shot(w, "lib_grid")
    w.grid.view.select_path(Gtk.TreePath.new_first())
    check(len(w.selected_rows()) == 1, "pick an album in the grid", len(w.selected_rows()))
    w.run("view:list")
    check(w.viewbtns["list"].get_active() and not w.viewbtns["grid"].get_active(), "view buttons follow")
    # sorting by a column
    w.songs.columns["title"].clicked()
    pump(0.2)
    names = [r[3] for r in w.songs.store]
    check(names == sorted(names, key=str.lower), "click Name to sort", names)
    w.songs.columns["title"].clicked()
    pump(0.2)
    check([r[3] for r in w.songs.store] == sorted(names, key=str.lower, reverse=True), "click again: reversed")
    w.songs.store.set_sort_column_id(26, Gtk.SortType.ASCENDING)
    # rating and check box
    ids = {r["title"]: r["id"] for r in w.rows}
    w.songs.select_ids([ids["Blue Train"]])
    w.run("rate:80")
    check(lib.track(ids["Blue Train"])["rating"] == 80, "Edit > Rating")
    row = [r for r in w.songs.store if r[0] == ids["Lazy Bird"]][0]
    w.songs._toggled(None, row.path)
    check(lib.track(ids["Lazy Bird"])["checked"] == 0, "untick a song")
    w.songs.select_ids([ids["Lazy Bird"]])
    w.run("check-selection")
    check(lib.track(ids["Lazy Bird"])["checked"] == 1, "Check Selection")
    # Get Info, one song
    w.songs.select_ids([ids["Locomotion"]])

    def edit(dlg):
        dlg.entries["title"].set_text("Locomotion (Take 2)")
        dlg.entries["comments"].set_text("alternate take")
        dlg.entries["year"].set_text("1958")
        dlg.rating.set_active_id("100")
        dlg.vol.set_value(50)
        dlg.set_art(open(os.path.join(os.environ["FOLIO_TESTS"], "art.png"), "rb").read())
        check(dlg.nb.get_n_pages() == 5, "Get Info: Summary, Info, Options, Lyrics, Artwork")
        return Gtk.ResponseType.OK
    answer("Get Info", edit)
    w.run("get-info")
    pump(0.3)
    t = tags.read(songs["Locomotion"])
    r = lib.track(ids["Locomotion"])
    check(t["title"] == "Locomotion (Take 2)" and t["comments"] == "alternate take" and t["year"] == 1958, "Get Info writes the tags", t)
    check(r["title"] == "Locomotion (Take 2)" and r["rating"] == 100 and r["volume_adjust"] == 50 and r["has_art"], "and the library",
          (r["title"], r["rating"], r["volume_adjust"], r["has_art"]))
    check(tags.artwork(songs["Locomotion"]) is not None, "artwork added to the file")
    # Get Info, several songs: only what changes is written
    w.songs.select_ids([ids["Teen Spirit Cover"], ids["Grunge Waltz"]])

    def multi(dlg):
        check(dlg.get_title() == "Multiple Item Information" and dlg.entries["artist"].get_text() == "The Garage"
              and dlg.entries["title"].get_text() == "", "several songs: shared fields shown, different ones left blank")
        dlg.entries["genre"].set_text("Grunge")
        return Gtk.ResponseType.OK
    answer("Get Info", multi)
    answer("Multiple Item Information", multi)
    w.run("get-info")
    pump(0.3)
    check(tags.read(songs["Teen Spirit Cover"])["genre"] == "Grunge" and tags.read(songs["Grunge Waltz"])["genre"] == "Grunge"
          and tags.read(songs["Grunge Waltz"])["title"] == "Grunge Waltz", "only the changed field is written to each")
    # playlists
    n0 = len(lib.playlists())
    w.songs.select_ids([ids["Blue Train"], ids["Lazy Bird"]])
    pid = w.run("new-playlist-selection")
    check(len(lib.playlists()) == n0 + 1 and [x["title"] for x in lib.playlist_tracks(pid)] == ["Blue Train", "Lazy Bird"],
          "New Playlist from Selection (named after the album)", lib.playlist(pid)["name"])
    check(w.source == ("playlist", pid) and len(w.rows) == 2, "the new playlist is shown")
    w._src_renamed(None, [str(r.path) for r in _rows(w.src_store) if r[3] == pid][0], "Road Trip")
    check(lib.playlist(pid)["name"] == "Road Trip", "rename a playlist")
    # drop more songs onto it from the library
    w.drop_on_source([r for r in _rows(w.src_store) if r[3] == pid][0], [ids["Sonata in C"]])
    check(len(lib.playlist_tracks(pid)) == 3, "drag songs onto a playlist")
    w.select_source("playlist", pid)
    pump(0.2)
    w.songs.reorder([2], 0)
    check([x["title"] for x in lib.playlist_tracks(pid)][0] == "Sonata in C", "drag to reorder in the playlist")
    w.songs.select_ids([ids["Sonata in C"]])
    w.run("delete")
    check(len(lib.playlist_tracks(pid)) == 2 and lib.track(ids["Sonata in C"]) is not None, "Delete in a playlist removes it from the playlist only")
    fid = w.run("new-folder")
    lib.move_playlist(pid, fid)
    w.fill_sources()
    check(len(lib.playlist_tracks(fid)) == 2, "a playlist folder")
    # Smart Playlist dialog
    def smart(dlg):
        dlg.name.set_text("Jazz I Love")
        rec = dlg.rule_rows[0]
        rec["field"].set_active_id("genre")
        rec["op"].set_active_id("is")
        rec["v1"].set_text("Jazz")
        rec2 = dlg.add_rule(None, rec)
        rec2["field"].set_active_id("rating")
        rec2["op"].set_active_id("is greater than")
        rec2["rating"].set_active_id("60")
        return Gtk.ResponseType.OK
    answer("Smart Playlist", smart)
    sid = w.run("new-smart")
    got = sorted(x["title"] for x in lib.playlist_tracks(sid))
    check(lib.playlist(sid)["name"] == "Jazz I Love" and got == ["Blue Train", "Locomotion (Take 2)"], "New Smart Playlist", got)

    def edit_smart(dlg):
        check(dlg.rule_rows[0]["v1"].get_text() == "Jazz" and len(dlg.rule_rows) == 2, "Edit Smart Playlist shows its rules")
        dlg.match.set_active_id("any")
        dlg.use_limit.set_active(True)
        dlg.limit_n.set_value(1)
        dlg.sel_by.set_active_id("highest rating")
        return Gtk.ResponseType.OK
    answer("Smart Playlist", edit_smart)
    w.run("edit-smart")
    check([x["title"] for x in lib.playlist_tracks(sid)] == ["Locomotion (Take 2)"], "edited: any rule, limit 1 by highest rating")
    # date rules survive the dialog
    lib.set_rules(sid, {"match": "all", "rules": [["date_added", "is in the last", 3, "weeks"]]})
    answer("Smart Playlist", lambda dlg: Gtk.ResponseType.OK)
    w.run("edit-smart")
    check(library.rules_sql(__import__("json").loads(lib.playlist(sid)["rules"]))[1][0] > 0
          and __import__("json").loads(lib.playlist(sid)["rules"])["rules"][0][3] == "weeks", "a date rule keeps its unit")
    # View Options
    def cols(dlg):
        dlg.checks["year"].set_active(True)
        dlg.checks["genre"].set_active(False)
        return Gtk.ResponseType.OK
    answer("View Options", cols)
    w.select_source("music")
    w.run("view-options")
    check("year" in w.songs.columns and "genre" not in w.songs.columns and "year" in w.settings["columns"], "View Options: columns")
    # copy, show in files
    w.songs.select_ids([ids["Blue Train"]])
    txt = w.run("copy")
    check(txt.startswith("Blue Train\t0:02\tColtrane Quartet"), "Copy puts the song's details on the clipboard")
    check(w.run("show-in-files").endswith(".flac"), "Show in Files")
    # export and import a playlist
    out = os.path.join(d, "trip.m3u")
    dialogs.save_file = lambda *a: out
    w.select_source("playlist", pid)
    w.run("export-playlist")
    check(os.path.exists(out) and "Blue Train" in open(out).read(), "Export Playlist (M3U)")
    dialogs.choose_files = lambda *a, **k: [out]
    p2 = w.run("import-playlist")
    check(len(lib.playlist_tracks(p2)) == 2, "Import Playlist")
    # delete from the library (keeping the file)
    w.select_source("music")
    w.songs.select_ids([ids["Sonata in C"]])
    answer("Choose", 2)
    w.run("delete")
    check(lib.track(ids["Sonata in C"]) is None and os.path.exists(songs["Sonata in C"]), "Delete from Library, keep the file")
    # delete a playlist
    answer("Confirm", Gtk.ResponseType.OK)
    w.select_source("playlist", p2)
    w.run("delete-playlist")
    check(lib.playlist(p2) is None and w.source[0] == "music", "delete a playlist", (p2, lib.playlist(p2) and dict(lib.playlist(p2)), w.source))
    # the source list's menu
    w.select_source("smart", sid)
    w._src_menu(None)
    check(("Edit Smart Playlist…", "edit-smart") in w.last_popup, "right-click a Smart Playlist: Edit")
    w.select_source("music")
    w.songs.select_ids([ids["Blue Train"]])
    w.song_menu(None)
    labels = [x[0] for x in w.last_popup]
    check(["Play", "Play Next", "Add to Up Next"] == labels[:3] and "Get Info" in labels and "Delete from Library" in labels,
          "right-click songs: Play Next, Get Info, Rating, Add to Playlist…", labels)
    # the empty library says how to add music
    lib.remove([r["id"] for r in lib.tracks()])
    w.load_songs()
    check(w.banner.get_visible() and "empty" in w.banner_label.get_text(), "an empty library says how to add music")
    shot(w, "lib_empty")


def _rows(store):
    out = []
    store.foreach(lambda m, p, it: out.append(m[it]) and False)
    return out


run(main)
