// Folio Chord for Windows: checks that run inside the program (FolioChord.exe --selftest <report> [music folder]).
// The release script runs them under Wine; the window is opened, driven and photographed too.

static FILE *g_report;
static int g_checks, g_fails;

static void check(bool ok, const char *what, const std::wstring &detail = L"") {
    g_checks++;
    if (!ok) g_fails++;
    fprintf(g_report, "%s %s%s%s\n", ok ? "ok  " : "FAIL", what, detail.empty() ? "" : "  -- ", narrow(detail).c_str());
    fflush(g_report);
}

static void pump(DWORD ms) {
    DWORD end = GetTickCount() + ms;
    MSG msg;
    while (GetTickCount() < end) {
        while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        Sleep(10);
    }
}

static void snapshot_rect(RECT rc, const std::wstring &path, HWND front);
static void snapshot(const std::wstring &path) {
    RECT rc;
    GetWindowRect(g_wnd, &rc);
    snapshot_rect(rc, path, g_wnd);
}

static void snapshot_rect(RECT rc, const std::wstring &path, HWND front) {
    RECT scr{0, 0, GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN)};
    IntersectRect(&rc, &rc, &scr);           // Wine copies nothing when the area runs off the screen
    int w = rc.right - rc.left, h = rc.bottom - rc.top;
    HDC screen = GetDC(nullptr), mem = CreateCompatibleDC(screen);
    BITMAPINFO bi = {};
    bi.bmiHeader = {sizeof(BITMAPINFOHEADER), w, -h, 1, 32, BI_RGB};
    void *bits = nullptr;
    HBITMAP bmp = CreateDIBSection(screen, &bi, DIB_RGB_COLORS, &bits, nullptr, 0);
    HGDIOBJ old = SelectObject(mem, bmp);
    // what's on the screen where the window is (PrintWindow leaves child windows out under Wine)
    SetForegroundWindow(front);
    RedrawWindow(front, nullptr, nullptr, RDW_INVALIDATE | RDW_UPDATENOW | RDW_ALLCHILDREN);
    pump(150);
    BitBlt(mem, 0, 0, w, h, screen, rc.left, rc.top, SRCCOPY | CAPTUREBLT);
    BITMAPFILEHEADER fh = {0x4D42, (DWORD)(sizeof fh + sizeof bi.bmiHeader + w * h * 4), 0, 0, sizeof fh + sizeof bi.bmiHeader};
    std::string data((const char *)&fh, sizeof fh);
    bi.bmiHeader.biHeight = -h;
    data.append((const char *)&bi.bmiHeader, sizeof bi.bmiHeader);
    data.append((const char *)bits, (size_t)w * h * 4);
    write_file(path, data);
    SelectObject(mem, old);
    DeleteObject(bmp);
    DeleteDC(mem);
    ReleaseDC(nullptr, screen);
}

static HTREEITEM find_source(int kind, int id) {
    for (auto &kv : g_tree) if (kv.second.first == kind && kv.second.second == id) return kv.first;
    return nullptr;
}

static const char *RSS =
    "<?xml version='1.0' encoding='UTF-8'?><rss version='2.0' xmlns:itunes='http://www.itunes.com/dtds/podcast-1.0.dtd'>"
    "<channel><title>Tech Show</title><itunes:author>Tech Media</itunes:author><itunes:image href='http://x/a.png'/>"
    "<item><title>Episode 2 &amp; more</title><guid>g2</guid><pubDate>Tue, 08 Sep 2026 10:00:00 +0000</pubDate>"
    "<itunes:duration>1:02:03</itunes:duration><enclosure url='http://x/2.mp3' type='audio/mpeg' length='1'/></item>"
    "<item><title><![CDATA[Episode 1]]></title><pubDate>Mon, 07 Sep 2026 10:00:00 +0000</pubDate>"
    "<itunes:duration>125</itunes:duration><enclosure url='http://x/1.mp3' type='audio/mpeg' length='1'/></item>"
    "<item><title>No audio</title></item></channel></rss>";

#include "selftest_chordamp.inc"

static int selftest(const std::wstring &report, const std::wstring &music) {
    g_report = _wfopen(report.c_str(), L"w");
    if (!g_report) return 2;
    std::wstring outdir = report.substr(0, report.find_last_of(L"\\/"));

    // ---- the small pieces
    Json j;
    bool ok = JsonParser::parse("{\"a\": [1, 2.5, \"x\\u00e9\\n\"], \"b\": {\"c\": true, \"d\": null}, \"e\": \"\\ud83c\\udfb5\"}", j);
    check(ok && j["a"].size() == 3 && j["a"][1].n() == 2.5 && j["a"][2].s() == "x\xc3\xa9\n" && j["b"]["c"].b, "JSON: objects, arrays, numbers, escapes");
    check(j["e"].s() == "\xf0\x9f\x8e\xb5", "JSON: characters outside the basic plane");
    std::wstring odd = L"tab\there\nnew\\line";
    check(tsv_unescape(tsv_escape(odd)) == odd, "saved text keeps tabs, new lines and backslashes");
    check(url_encode(L"rock & roll/é") == L"rock%20%26%20roll%2F%C3%A9", "web addresses are encoded", url_encode(L"rock & roll/é"));
    check(fmt_time(65) == L"1:05" && fmt_time(3725) == L"1:02:05", "times are shown as m:ss and h:mm:ss");
    Show show;
    std::vector<Episode> eps;
    std::wstring err;
    ok = podcast_parse(RSS, show, eps, err);
    check(ok && show.title == L"Tech Show" && show.author == L"Tech Media" && show.artwork == L"http://x/a.png", "a podcast feed: the show", show.title);
    check(eps.size() == 2 && eps[0].title == L"Episode 2 & more" && eps[1].title == L"Episode 1", "its episodes (one without audio left out)");
    check(eps.size() == 2 && eps[0].duration == 3723 && eps[1].duration == 125, "episode lengths (h:mm:ss and seconds)");
    check(eps.size() == 2 && eps[0].guid == L"g2" && eps[1].guid == L"http://x/1.mp3", "an episode without an id is known by its address");
    check(eps.size() == 2 && eps[0].published - eps[1].published == 86400, "episode dates");

    // ---- the library
    Library lib;
    lib.load();
    int n_files = 0;
    if (!music.empty()) {
        WIN32_FIND_DATAW fd;
        HANDLE h = FindFirstFileW((music + L"\\*").c_str(), &fd);
        if (h != INVALID_HANDLE_VALUE) {
            do if (is_audio_file(fd.cFileName)) n_files++;
            while (FindNextFileW(h, &fd));
            FindClose(h);
        }
        auto ids = lib.add_folder(music);
        check((int)ids.size() == n_files && n_files > 0, "Add Folder: every music file", std::to_wstring(ids.size()) + L" of " + std::to_wstring(n_files));
        bool titled = true;
        for (auto &t : lib.tracks) if (t.title.empty()) titled = false;
        check(titled, "every song has a name (its file's name when the tags have none)");
        auto again = lib.add_folder(music);
        check(lib.tracks.size() == ids.size(), "adding the folder again doesn't add songs twice");
        lib.tracks[0].rating = 80;
        lib.played(lib.tracks[0].id);
        int pid = lib.new_playlist(L"Road trip\twith tab");
        lib.playlist(pid)->tracks = {lib.tracks[0].id, lib.tracks.back().id};
        lib.save();
        Library back;
        back.load();
        check(back.tracks.size() == lib.tracks.size() && back.tracks[0].rating == 80 && back.tracks[0].plays == 1,
              "the library is kept: songs, ratings, play counts");
        check(back.playlists.size() == 1 && back.playlists[0].name == L"Road trip\twith tab" && back.playlists[0].tracks.size() == 2,
              "and playlists");
        check(back.folders.size() == 1, "and the folders added (for Check Music Folders Again)");
        back.remove({back.tracks[0].id});
        check(back.tracks.size() == lib.tracks.size() - 1 && back.playlists[0].tracks.size() == 1, "removing a song takes it out of playlists too");
    }
    OnlineStore os;
    os.load();
    Station st;
    st.uuid = L"u1";
    st.name = L"Jazz FM";
    st.url = L"http://x/jazz";
    os.set_favourite(st, true);
    int sid = os.subscribe(show, eps);
    std::vector<Episode> more = eps;
    Episode e3 = eps[0];
    e3.guid = L"g3";
    e3.title = L"Episode 3";
    e3.published += 86400;
    more.push_back(e3);
    check(os.merge(sid, more) == 1, "refreshing a show adds only the new episodes");
    OnlineStore os2;
    os2.load();
    check(os2.favourites.size() == 1 && os2.shows.size() == 1 && os2.episodes_of(sid).size() == 3, "favourite stations and podcasts are kept");

    // ---- the window
    g_lib.load();
    g_online.load();
    WNDCLASSEXW wc = {sizeof wc};
    wc.lpfnWndProc = wnd_proc;
    wc.hInstance = g_inst;
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    wc.lpszClassName = L"FolioChord";
    ATOM atom = RegisterClassExW(&wc);
    fprintf(g_report, "info class %u (error %lu)\n", atom, GetLastError());
    HWND h = CreateWindowExW(0, L"FolioChord", L"Folio Chord", WS_OVERLAPPEDWINDOW, 20, 20, 1180, 740, nullptr, build_menu(), g_inst, nullptr);
    fprintf(g_report, "info window %p (error %lu), search box %d, list %d\n", (void *)h, GetLastError(), IsWindow(g_search), IsWindow(g_list));
    if (!h) { fprintf(g_report, "SELFTEST FAILS (no window)\n"); fclose(g_report); return 1; }
    fill_sources();
    update_controls();
    ShowWindow(h, SW_SHOW);
    ShowWindow(h, SW_SHOW);
    pump(800);
    check(IsWindowVisible(h) && g_src == SRC_MUSIC, "the window opens on Music", std::to_wstring(IsWindowVisible(h)) + L" " + std::to_wstring(g_src));
    check((int)g_rows.size() == n_files, "Music lists the library", std::to_wstring(g_rows.size()));
    snapshot(outdir + L"\\win_music.bmp");
    SetWindowTextW(g_search, L"zzz-nothing");
    pump(200);
    check(g_rows.empty(), "the search box filters the list", std::to_wstring(g_rows.size()) + L" " + search_text());
    SetWindowTextW(g_search, L"");
    pump(200);
    if (!g_rows.empty()) {
        SendMessageW(g_list, WM_LBUTTONDOWN, 0, 0);
        g_sort_col = 0;
        g_sort_desc = true;
        fill_list();
        bool desc = true;
        for (size_t i = 1; i < g_rows.size(); i++)
            if (_wcsicmp(col_text(g_rows[i - 1], 0).c_str(), col_text(g_rows[i], 0).c_str()) < 0) desc = false;
        check(desc, "clicking a column sorts by it");
        ListView_SetItemState(g_list, 0, LVIS_SELECTED, LVIS_SELECTED);
        on_command(CMD_RATE4);
        check(g_lib.tracks[g_rows[0].index].rating == 80, "Rating > 4 stars");
        on_command(CMD_SELECT_ALL);
        check((int)selected_rows().size() == (int)g_rows.size(), "Select All");
        on_command(CMD_PLAYLIST_BASE + 0);
        check(!g_lib.playlists.empty() && g_lib.playlists[0].tracks.size() >= g_rows.size(), "Add to Playlist");
        // play the first song: Media Foundation under Wine may not have every decoder; this says what happened
        ListView_SetItemState(g_list, -1, 0, LVIS_SELECTED);
        play_row(0);
        DWORD until = GetTickCount() + 6000;
        while (GetTickCount() < until && !g_player->active() && g_lcd_message.empty()) pump(100);
        check(g_has_now && g_now.title == col_text(g_rows[0], 0), "double-click plays: the status display shows the song", g_now.title);
        fprintf(g_report, "info Media Foundation: %s\n",
                g_player->active() ? "playing" : narrow(L"not playing here (" + g_player->last_error + L")").c_str());
        pump(1200);
        snapshot(outdir + L"\\win_playing.bmp");
        on_command(CMD_SHUFFLE);
        check(g_shuffle && (GetMenuState(GetMenu(h), CMD_SHUFFLE, MF_BYCOMMAND) & MF_CHECKED), "Shuffle (and its menu tick)");
        on_command(CMD_SHUFFLE);
        on_command(CMD_REPEAT_ALL);
        check(g_repeat == 1, "Repeat > All");
        on_command(CMD_REPEAT_OFF);
        double v = g_vol;
        on_command(CMD_VOL_DOWN);
        check(g_vol < v && SendMessageW(g_volume, TBM_GETPOS, 0, 0) == (LRESULT)(g_vol * 100), "Decrease Volume moves the slider");
        on_command(CMD_STOP);
        check(!g_player->active(), "Stop");
    }
    if (HTREEITEM pl = g_lib.playlists.empty() ? nullptr : find_source(SRC_PLAYLIST, g_lib.playlists[0].id)) {
        TreeView_SelectItem(g_sources, pl);
        pump(200);
        check(g_src == SRC_PLAYLIST && !g_rows.empty(), "a playlist shows its songs");
    }
    TreeView_SelectItem(g_sources, find_source(SRC_RADIO_FAVS, 0));
    pump(300);
    check(g_src == SRC_RADIO_FAVS && g_rows.size() == 1 && col_text(g_rows[0], 1) == L"Jazz FM", "Radio > Favourites");
    check(g_rows.size() == 1 && col_text(g_rows[0], 0) == L"♥", "favourites are marked with a heart");
    snapshot(outdir + L"\\win_radio.bmp");
    HTREEITEM sh = find_source(SRC_SHOW, sid);
    check(sh != nullptr, "a subscribed podcast is in the source list");
    TreeView_SelectItem(g_sources, sh);
    pump(300);
    check(g_src == SRC_SHOW && g_rows.size() == 3 && col_text(g_rows[0], 1) == L"Episode 3", "its episodes, newest first");
    if (g_rows.empty()) { fprintf(g_report, "SELFTEST FAILS (no episodes)\n"); fclose(g_report); return 1; }
    snapshot(outdir + L"\\win_podcast.bmp");
    ListView_SetItemState(g_list, 0, LVIS_SELECTED, LVIS_SELECTED);
    on_command(CMD_MARK_PLAYED);
    check(col_text(g_rows[0], 0).empty(), "Mark as Played");
    TreeView_SelectItem(g_sources, find_source(SRC_PODCASTS, 0));
    pump(200);
    check(g_src == SRC_PODCASTS && g_rows.size() == 1, "Podcasts lists the shows");
    // every menu command runs (dialogs that need a person are answered by the self test)
    int ran = 0;
    for (int id : {CMD_GO_CURRENT, CMD_IMPORT_CD, CMD_BURN, CMD_MINI_PLAYER, CMD_CONVERT,
                   CMD_ORGANIZE, CMD_STORE_SEARCH, CMD_STORE_SIGNIN, CMD_ABOUT, CMD_SHORTCUTS, CMD_MUTE, CMD_MUTE, CMD_PREV,
                   CMD_NEXT, CMD_STOP}) { on_command(id); ran++; }
    check(ran == 15, "the menu commands run without trouble");
    chordamp_tests(h, music, outdir);
    // dark
    g_dark = true;
    apply_colours();
    TreeView_SelectItem(g_sources, find_source(SRC_MUSIC, 0));
    pump(400);
    snapshot(outdir + L"\\win_dark.bmp");
    g_dark = false;
    apply_colours();
    DestroyWindow(h);
    pump(200);
    fprintf(g_report, "%d checks, %d failed\n%s\n", g_checks, g_fails, g_fails ? "SELFTEST FAILS" : "SELFTEST all passed");
    fclose(g_report);
    return g_fails ? 1 : 0;
}
