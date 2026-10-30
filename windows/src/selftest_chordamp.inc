// Chordamp on Windows, checked from inside the program (part of --selftest). The music folder may hold
// testskin.wsz (a skin with window shapes, a pointer and bitmap text, made by the test runner).

static RECT chordamp_rect() {
    RECT u{};
    bool first = true;
    for (auto *p : ca::all_parts())
        if (IsWindowVisible(p->hwnd)) {
            RECT r = p->rect();
            if (first) { u = r; first = false; }
            else UnionRect(&u, &u, &r);
        }
    return u;
}

static void chordamp_tests(HWND h, const std::wstring &music, const std::wstring &outdir) {
    using namespace ca;
    // ---- skins: Chordamp's own (deflated inside the program: the inflater at work)
    Skin *own = skin_own();
    check(own->has(L"main") && own->sheets[L"main"].w == 275 && own->sheets[L"main"].h == 116, "Chordamp's own skin unpacks (main 275x116)",
          std::to_wstring(own->sheets.size()) + L" sheets");
    check(own->has(L"eqmain") && own->has(L"pledit") && own->has(L"cbuttons") && own->has(L"titlebar") && !own->text_bitmap,
          "with the equalizer, playlist, buttons and title bar pictures");
    check(own->vis[2] != own->vis[0] && own->pl_selectedbg == RGB(107, 16, 82), "its colours (viscolor.txt, pledit.txt)");
    std::string raw("\x07\x00\x00", 3);           // block type 3: not a deflate stream
    std::string out;
    check(!inflate_raw((const unsigned char *)raw.data(), raw.size(), out), "a damaged compressed file is refused");
    delete own;
    std::wstring exported = outdir + L"\\Chordamp-export.wsz", err;
    check(skin_export_own(exported), "Save Chordamp Skin As writes a .wsz");
    Skin *back = skin_load(exported, err);
    check(back && back->has(L"main") && back->name == L"Chordamp-export.wsz", "and it loads back as a skin", err);
    delete back;
    write_file(outdir + L"\\not-a-skin.wsz", "hello");
    check(!skin_load(outdir + L"\\not-a-skin.wsz", err) && !err.empty(), "a file that isn't a skin says so", err);

    // ---- the look
    S.pos.clear();
    S.eq = S.pl = true;
    S.shade = S.dbl = S.ontop = false;
    S.vis = L"spectrum";
    switch_look(true);
    pump(500);
    check(g_visible && !IsWindowVisible(h) && IsWindowVisible(g_main_part->hwnd) && IsWindowVisible(g_eq_part->hwnd) &&
              IsWindowVisible(g_pl_part->hwnd), "View > Chordamp: the player, equalizer and playlist editor replace the window");
    RECT mr = g_main_part->rect(), er = g_eq_part->rect(), pr = g_pl_part->rect();
    check(mr.right - mr.left == 275 && mr.bottom - mr.top == 116, "the player is 275 x 116",
          std::to_wstring(mr.right - mr.left) + L"x" + std::to_wstring(mr.bottom - mr.top));
    check(er.top == mr.bottom && pr.top == er.bottom && er.left == mr.left, "the equalizer and playlist sit docked under it");
    check(ca::owns(g_main_part->hwnd) && ca::owns(g_pl_part->hwnd) && !ca::owns(h), "Chordamp's windows take their own keys");

    // ---- playing from the playlist editor
    std::vector<QItem> items;
    for (auto &t : g_lib.tracks) items.push_back(song_item(t));
    g_queue = items;
    make_order(0);
    g_pos = -1;
    g_pl_part->redraw();
    pump(200);
    PlPart *pl = plp();
    int n = (int)g_queue.size();
    if (n >= 2) {
        // a double-click on the second row plays it
        int s = scale();
        SendMessageW(g_pl_part->hwnd, WM_LBUTTONDBLCLK, 0, MAKELPARAM(30 * s, (22 + PlPart::ROW + 3) * s));
        DWORD until = GetTickCount() + 6000;
        while (GetTickCount() < until && !g_player->active()) pump(100);
        check(current_index() == 1 && g_has_now, "double-click in the playlist plays that song", std::to_wstring(current_index()));
        check(title_text().compare(0, 3, L"2. ") == 0, "the player shows its number and name", title_text());
        pump(300);
        check(g_queue[1].duration > 11 && g_queue[1].duration < 13, "its length (from the player when the tags have none)",
              std::to_wstring(g_queue[1].duration));
        pump(1500);
        double p0 = g_player->position();
        pump(800);
        check(g_player->processing() && g_player->position() > p0, "it plays through Chord's own sound engine (time moves on)",
              std::to_wstring(p0) + L" -> " + std::to_wstring(g_player->position()) + (g_player->output_ok() ? L" (sound device)" : L" (no sound device: in time, silently)"));
        std::vector<float> mags;
        bool spec = false;
        for (int i = 0; i < 20 && !spec; i++) { pump(50); spec = g_player->spectrum(mags); }
        float peak = -200;
        for (float v : mags) peak = std::max(peak, v);
        check(spec && mags.size() == 512 && peak > -40, "the spectrum is read from the sound", std::to_wstring(peak));
        pump(300);
        double hb = 0;
        for (double b : mainp()->bars) hb = std::max(hb, b);
        check(hb > 0, "and the visualizer's bars move", std::to_wstring(hb));
        snapshot_rect(chordamp_rect(), outdir + L"\\chordamp.bmp", g_main_part->hwnd);
        // keys
        key('C', false, false, false, g_main_part);
        pump(200);
        check(g_player->paused(), "C pauses");
        key('X', false, false, false, g_main_part);
        pump(200);
        check(g_player->playing(), "X plays again");
        double before = g_player->position();
        key(VK_RIGHT, false, false, false, g_main_part);
        pump(300);
        check(g_player->position() > before + 3, "Right skips 5 seconds", std::to_wstring(before) + L" -> " + std::to_wstring(g_player->position()));
        double v0 = g_vol;
        key(VK_DOWN, false, false, false, g_main_part);
        check(g_vol < v0, "Down lowers the volume");
        key('B', false, false, false, g_main_part);
        pump(300);
        check(current_index() == (n > 2 ? 2 : 0) || g_repeat == 0, "B: the next song", std::to_wstring(current_index()));
        // the scope
        set_vis(L"oscilloscope");
        bool wave = false;
        for (int i = 0; i < 20 && !wave; i++) { pump(60); wave = !mainp()->wave.empty(); }
        check(wave, "Oscilloscope draws the waveform");
        set_vis(L"spectrum");
    }
    // ---- the equalizer
    S.eq_on = false;
    SendMessageW(g_eq_part->hwnd, WM_LBUTTONDOWN, MK_LBUTTON, MAKELPARAM(20, 22));
    SendMessageW(g_eq_part->hwnd, WM_LBUTTONUP, 0, MAKELPARAM(20, 22));
    check(S.eq_on && g_player->eq_on(), "the equalizer's ON button");
    SendMessageW(g_eq_part->hwnd, WM_LBUTTONDOWN, MK_LBUTTON, MAKELPARAM(84, 38));
    SendMessageW(g_eq_part->hwnd, WM_MOUSEMOVE, MK_LBUTTON, MAKELPARAM(84, 39));
    SendMessageW(g_eq_part->hwnd, WM_LBUTTONUP, 0, MAKELPARAM(84, 39));
    check(S.bands[0] > 10 && S.preset == L"Manual", "dragging the 32 Hz slider to the top", std::to_wstring(S.bands[0]));
    g_menu_answer = L"Rock";
    SendMessageW(g_eq_part->hwnd, WM_LBUTTONDOWN, MK_LBUTTON, MAKELPARAM(220, 22));
    SendMessageW(g_eq_part->hwnd, WM_LBUTTONUP, 0, MAKELPARAM(220, 22));
    check(S.preset == L"Rock" && S.bands[0] == 5 && S.bands[9] == 4.5, "Presets > Rock", S.preset);
    // balance
    SendMessageW(g_main_part->hwnd, WM_LBUTTONDOWN, MK_LBUTTON, MAKELPARAM(177 + 7 + 24, 62));
    SendMessageW(g_main_part->hwnd, WM_LBUTTONUP, 0, MAKELPARAM(177 + 7 + 24, 62));
    check(S.balance > 0.9 && g_player->balance() > 0.9, "the balance slider (to the right)", std::to_wstring(S.balance));
    S.balance = 0;
    g_player->set_balance(0);
    // the Standard look's equalizer shows the same settings
    standard_equalizer();
    pump(200);
    wchar_t sel[64] = L"";
    GetWindowTextW(g_eqw.presets, sel, 64);
    check(IsWindowVisible(g_eqw.wnd) && std::wstring(sel) == L"Rock" &&
              SendMessageW(g_eqw.sliders[1], TBM_GETPOS, 0, 0) == -50, "Window > Equalizer shows the same equalizer", sel);
    ShowWindow(g_eqw.wnd, SW_HIDE);

    // ---- shade and double size
    RECT e0 = g_eq_part->rect();
    toggle_shade();
    pump(200);
    RECT m1 = g_main_part->rect(), e1 = g_eq_part->rect();
    check(m1.bottom - m1.top == 14 && e1.top == m1.bottom && e1.top == e0.top - 102, "Shade: the player folds to its title bar; the docked windows follow");
    snapshot_rect(chordamp_rect(), outdir + L"\\chordamp_shade.bmp", g_main_part->hwnd);
    toggle_shade();
    set_double(true);
    pump(300);
    RECT m2 = g_main_part->rect(), e2 = g_eq_part->rect();
    check(m2.right - m2.left == 550 && m2.bottom - m2.top == 232 && e2.top == m2.bottom, "Double Size (Ctrl+D)",
          std::to_wstring(m2.right - m2.left) + L"x" + std::to_wstring(m2.bottom - m2.top));
    auto paint_pixel = [](Part *p, int x, int y) {
        HDC screen = GetDC(nullptr), mem = CreateCompatibleDC(screen);
        HBITMAP bmp = CreateCompatibleBitmap(screen, 600, 260);
        HGDIOBJ old = SelectObject(mem, bmp);
        p->paint(mem);
        COLORREF c = GetPixel(mem, x, y);
        SelectObject(mem, old);
        DeleteObject(bmp);
        DeleteDC(mem);
        ReleaseDC(nullptr, screen);
        return c;
    };
    COLORREF big = paint_pixel(g_main_part, 2 * 20 + 1, 2 * 96 + 1);
    for (auto *p : all_parts()) RedrawWindow(p->hwnd, nullptr, nullptr, RDW_INVALIDATE | RDW_UPDATENOW);
    pump(300);
    snapshot_rect(chordamp_rect(), outdir + L"\\chordamp_double.bmp", g_main_part->hwnd);
    set_double(false);
    pump(200);
    COLORREF small = paint_pixel(g_main_part, 20, 96);
    check(big == small && big != RGB(0, 0, 0), "Double Size draws the skin twice as big (same picture)",
          std::to_wstring(big) + L" / " + std::to_wstring(small));
    pump(200);

    // ---- snapping and docking
    RECT pr0 = g_pl_part->rect();
    SetWindowPos(g_pl_part->hwnd, nullptr, pr0.left + 400, pr0.top, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
    RECT mr3 = g_main_part->rect();
    POINT sp = snap(g_pl_part, mr3.right + 6, mr3.top + 3, {});
    check(sp.x == mr3.right && sp.y == mr3.top, "a window dragged near another snaps to it", std::to_wstring(sp.x) + L"," + std::to_wstring(sp.y));
    SetWindowPos(g_pl_part->hwnd, nullptr, sp.x, sp.y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
    auto d = docked_to(g_main_part);
    check(d.size() == 2, "windows touching the player move with it", std::to_wstring(d.size()));
    // moving the player by its title bar carries them along
    POINT c0;
    GetCursorPos(&c0);
    RECT before_pl = g_pl_part->rect();
    begin_move(g_main_part);
    SetCursorPos(c0.x + 40, c0.y + 30);
    move_motion(g_main_part);
    end_move(g_main_part);
    RECT after_pl = g_pl_part->rect();
    check(after_pl.left - before_pl.left == g_main_part->rect().left - mr3.left && after_pl.left != before_pl.left,
          "dragging the player drags the docked windows", std::to_wstring(after_pl.left - before_pl.left));
    SetCursorPos(c0.x, c0.y);
    S.pos.clear();
    place();
    pump(100);

    // ---- the playlist editor's menus
    if (n >= 3) {
        select(L"all");
        check((int)pl->sel.size() == n, "Sel > Select All");
        std::wstring first = g_queue[0].title;
        sort(L"reverse");
        check(g_queue[n - 1].title == first, "Misc > Reverse List");
        sort(L"title");
        bool sorted = true;
        for (int i = 1; i < n; i++) if (lower(g_queue[i - 1].title) > lower(g_queue[i].title)) sorted = false;
        check(sorted, "Misc > Sort by Title");
        pl->sel = {0};
        std::wstring moved = g_queue[0].title;
        pl->move_rows(1);
        check(g_queue[1].title == moved && pl->sel.count(1), "Alt+Down moves the selected song down");
        pl->sel = {0};
        remove_selected();
        check((int)g_queue.size() == n - 1, "Rem > Remove Selected");
        std::wstring m3u = outdir + L"\\list.m3u";
        check(save_list(m3u), "List > Save List writes an .m3u");
        remove_all();
        check(g_queue.empty(), "Rem > Remove All");
        load_list(m3u);
        DWORD until = GetTickCount() + 8000;
        while (GetTickCount() < until && (int)g_queue.size() < n - 1) pump(100);
        check((int)g_queue.size() == n - 1, "List > Open List brings it back", std::to_wstring(g_queue.size()));
        // Jump to File
        std::wstring want = g_queue.back().title;
        int pick = jump(want, true);
        check(pick == (int)g_queue.size() - 1, "Jump to File (J): type part of a name, Enter plays it", std::to_wstring(pick));
    }
    // ---- the options menu
    g_menu_answer = L"Always on Top";
    options_menu(g_main_part, 0, 0);
    // Windows sets WS_EX_TOPMOST at once; Wine (X11) asks the window manager, and the test display has none
    check(S.ontop && g_ontop_error == 0, "Always on Top (Ctrl+T)", L"error " + std::to_wstring(g_ontop_error));
    fprintf(g_report, "info topmost flag here: %s\n", (GetWindowLongW(g_main_part->hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST) ? "set" : "left to the window manager");
    set_ontop(false);
    check(g_last_menu.size() > 15, "the options menu (right-click) has every entry", std::to_wstring(g_last_menu.size()));
    g_menu_answer = L"Off";
    options_menu(g_main_part, 0, 0);
    check(S.vis == L"off", "Visualization > Off");
    set_vis(L"spectrum");
    key('G', false, true, false, g_main_part);
    check(!S.eq && !IsWindowVisible(g_eq_part->hwnd), "Alt+G hides the equalizer");
    key('G', false, true, false, g_main_part);
    check(S.eq && IsWindowVisible(g_eq_part->hwnd), "and shows it again");
    // ---- the library window
    show_library(1);
    pump(300);
    check(g_lib_wnd && IsWindowVisible(g_lib_wnd) && ListView_GetItemCount(g_libs.list) == (int)g_lib.tracks.size(), "Alt+L: the library window",
          std::to_wstring(ListView_GetItemCount(g_libs.list)));
    show_library(0);

    // ---- a downloaded skin: shapes, pointer, bitmap text
    std::wstring test_skin = music + L"\\testskin.wsz";
    if (GetFileAttributesW(test_skin.c_str()) != INVALID_FILE_ATTRIBUTES) {
        CopyFileW(test_skin.c_str(), (skins_dir() + L"\\testskin.wsz").c_str(), FALSE);
        set_skin(L"testskin.wsz");
        pump(300);
        check(S.skin == L"testskin.wsz" && g_skin->text_bitmap, "Skins > a loaded skin (with its bitmap text)");
        HRGN rg = CreateRectRgn(0, 0, 0, 0);
        int kind = GetWindowRgn(g_main_part->hwnd, rg);
        RECT box{};
        GetRgnBox(rg, &box);
        DeleteObject(rg);
        check(kind == COMPLEXREGION || kind == SIMPLEREGION, "its region.txt shapes the player window", std::to_wstring(kind));
        check(g_skin->cursor(L"normal", 1) != nullptr, "its pointer (.cur) is used");
        check(g_skin->sheets[L"main"].dc && GetPixel(g_skin->sheets[L"main"].dc, 100, 100) == RGB(10, 70, 140), "its pictures replace Chordamp's");
        snapshot_rect(chordamp_rect(), outdir + L"\\chordamp_testskin.bmp", g_main_part->hwnd);
        set_skin(L"");
        HRGN rg2 = CreateRectRgn(0, 0, 0, 0);
        check(GetWindowRgn(g_main_part->hwnd, rg2) == ERROR, "Chordamp's own skin: a plain rectangle again");
        DeleteObject(rg2);
    } else fprintf(g_report, "info no testskin.wsz in the music folder: downloaded skins not checked\n");

    // ---- dark desktop: Chordamp keeps its own colours (it is drawn from the skin)
    snapshot_rect(chordamp_rect(), outdir + L"\\chordamp_final.bmp", g_main_part->hwnd);
    on_command(CMD_STOP);
    // ---- back to Standard
    key('W', true, false, true, g_main_part);
    pump(300);
    check(!g_visible && IsWindowVisible(h) && !IsWindowVisible(g_main_part->hwnd), "Ctrl+Shift+W: back to the Standard look");
    std::string st;
    read_file(settings_path(), st);
    check(st.find("look\tstandard") != std::string::npos && st.find("eq_preset\tRock") != std::string::npos,
          "the look and the equalizer are remembered");
    on_command(CMD_CHORDAMP);
    pump(200);
    check(g_visible && !IsWindowVisible(h), "View > Look: Chordamp (Ctrl+Shift+W) switches again");
    switch_look(false);
    pump(200);
}
