// Folio Chord for Windows: the window (Standard look) — menus, top bar with the status display,
// source list, song list — and everything the commands do.
#include "common.h"
#include "library.h"
#include "player.h"
#include "online.h"
#include "net.h"
#include "json.h"
#include "resource.h"
#include <commctrl.h>
#include <commdlg.h>
#include <shellapi.h>
#include <dwmapi.h>
#include <uxtheme.h>
#include <windowsx.h>
#include <thread>
#include <random>
#include <ctime>

// ================================================================ ids
enum {
    IDC_SOURCES = 100, IDC_LIST, IDC_SEARCH, IDC_PREV, IDC_PLAY, IDC_NEXT, IDC_VOLUME, IDC_LCD, IDC_STATUS,
    // File
    CMD_ADD_FILE = 1000, CMD_ADD_FOLDER, CMD_NEW_PLAYLIST, CMD_RESCAN, CMD_IMPORT_CD, CMD_BURN, CMD_EXIT,
    // Edit
    CMD_SELECT_ALL = 1100, CMD_DELETE, CMD_GET_INFO, CMD_RATE0, CMD_RATE1, CMD_RATE2, CMD_RATE3, CMD_RATE4, CMD_RATE5,
    CMD_RENAME_PLAYLIST, CMD_DELETE_PLAYLIST, CMD_SHOW_IN_EXPLORER, CMD_PLAY_SELECTION, CMD_ADD_TO_PLAYLIST_NEW,
    CMD_FAVOURITE, CMD_UNSUBSCRIBE, CMD_REFRESH_SHOW, CMD_SUBSCRIBE_SELECTED, CMD_MARK_PLAYED,
    // View
    CMD_CHORDAMP = 1200, CMD_GO_CURRENT,
    // Controls
    CMD_PLAY_PAUSE = 1300, CMD_STOP, CMD_NEXT, CMD_PREV, CMD_VOL_UP, CMD_VOL_DOWN, CMD_MUTE, CMD_SHUFFLE,
    CMD_REPEAT_OFF, CMD_REPEAT_ALL, CMD_REPEAT_ONE,
    // Store (as on Linux: not part of Folio)
    CMD_STORE_SEARCH = 1400, CMD_STORE_SIGNIN,
    // Advanced
    CMD_OPEN_STREAM = 1500, CMD_SUBSCRIBE_URL, CMD_REFRESH_PODCASTS, CMD_ORGANIZE, CMD_CONVERT,
    // Window
    CMD_MINIMIZE = 1600, CMD_EQUALIZER, CMD_MINI_PLAYER,
    // Help
    CMD_ABOUT = 1700, CMD_SHORTCUTS,
    CMD_PLAYLIST_BASE = 5000,       // "Add to Playlist" > each playlist
};

enum SourceKind { SRC_MUSIC = 1, SRC_PLAYLIST, SRC_RADIO_POPULAR, SRC_RADIO_FAVS, SRC_RADIO_RECENT, SRC_RADIO_SEARCH,
                  SRC_PODCASTS, SRC_SHOW, SRC_PODCAST_SEARCH, SRC_HEADER };

struct QItem {                      // one thing in the play queue
    int kind = 0;                   // 1 song, 2 episode, 3 station
    int id = 0;                     // song id / show id
    std::wstring key, url, title, artist;
    double duration = 0;
};

struct Row {                        // one row of the list
    int kind = 0;                   // 1 song, 2 station, 3 show, 4 episode, 5 directory result
    int index = 0;                  // into the matching vector
};

// ================================================================ state
static HINSTANCE g_inst;
static HWND g_wnd, g_sources, g_list, g_search, g_prev, g_play, g_next, g_volume, g_lcd, g_status;
static HFONT g_font, g_font_bold, g_font_small, g_font_sym;
static Library g_lib;
static OnlineStore g_online;
static Player *g_player;
static std::vector<QItem> g_queue;
static std::vector<int> g_order;
static int g_pos = -1;
static QItem g_now;
static bool g_has_now = false, g_shuffle = false, g_dark = false, g_muted = false;
static int g_repeat = 0;            // 0 off, 1 all, 2 one
static double g_vol = 0.8, g_vol_before_mute = 0.8;
static int g_src = SRC_MUSIC, g_src_id = 0;
static std::vector<Row> g_rows;
static std::vector<Station> g_stations;      // the list on show (popular / search)
static std::vector<Show> g_found;            // podcast directory results
static int g_sort_col = -1;
static bool g_sort_desc = false;
static std::wstring g_busy;                  // shown in the status display while working
static std::map<HTREEITEM, std::pair<int, int>> g_tree;
static std::wstring g_lcd_message;
static DWORD g_lcd_message_until = 0;
static bool g_selftest = false;

static const int TOPBAR = 64, SOURCES_W = 210;
static COLORREF C_ACCENT() { return g_dark ? RGB(0xa8, 0x23, 0x7d) : RGB(0xb8, 0x18, 0x7f); }
static COLORREF C_BG() { return g_dark ? RGB(0x2a, 0x2a, 0x2a) : RGB(0xe8, 0xe8, 0xe8); }
static COLORREF C_FG() { return g_dark ? RGB(0xec, 0xec, 0xec) : RGB(0x1e, 0x1e, 0x1e); }
static COLORREF C_LIST() { return g_dark ? RGB(0x1f, 0x1f, 0x1f) : RGB(0xff, 0xff, 0xff); }
static COLORREF C_SRC() { return g_dark ? RGB(0x2c, 0x26, 0x2c) : RGB(0xe6, 0xe0, 0xe6); }

// ================================================================ small helpers
static void info(const std::wstring &text, const wchar_t *title = L"Folio Chord") {
    if (g_selftest) return;
    MessageBoxW(g_wnd, text.c_str(), title, MB_OK | MB_ICONINFORMATION);
}

static void not_here(const std::wstring &what) {
    info(L"“" + what + L"” isn't available in Folio Chord for Windows yet.");
}

static void flash(const std::wstring &text, DWORD ms = 4000) {
    g_lcd_message = text;
    g_lcd_message_until = GetTickCount() + ms;
    InvalidateRect(g_lcd, nullptr, FALSE);
}

// run work off the window's thread; done() runs back on it
static void background(std::function<void()> work, std::function<void()> done) {
    auto *fn = new std::function<void()>(done);
    std::thread([work, fn]() {
        CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        work();
        CoUninitialize();
        PostMessageW(g_wnd, WM_CHORD_TASK, 0, (LPARAM)fn);
    }).detach();
}

static std::wstring settings_path() { return data_dir() + L"\\settings.tsv"; }
namespace ca {
std::wstring save_lines();
void load(std::map<std::wstring, std::wstring> &m);
void redraw_all();
void switch_look(bool chordamp);
void standard_equalizer();
void apply_eq(bool save);
bool owns(HWND h);
extern bool g_visible;
}

static void save_settings() {
    std::wstring o;
    wchar_t v[64];
    swprintf(v, 64, L"%.3f", g_muted ? g_vol_before_mute : g_vol);
    o += L"volume\t" + std::wstring(v) + L"\n";
    o += L"shuffle\t" + std::to_wstring(g_shuffle) + L"\n";
    o += L"repeat\t" + std::to_wstring(g_repeat) + L"\n";
    WINDOWPLACEMENT wp = {sizeof wp};
    if (g_wnd && GetWindowPlacement(g_wnd, &wp)) {
        RECT &r = wp.rcNormalPosition;
        o += L"window\t" + std::to_wstring(r.left) + L"," + std::to_wstring(r.top) + L"," + std::to_wstring(r.right) + L"," +
             std::to_wstring(r.bottom) + L"," + std::to_wstring(wp.showCmd == SW_SHOWMAXIMIZED) + L"\n";
    }
    o += ca::save_lines();
    write_file(settings_path(), narrow(o));
}

static std::map<std::wstring, std::wstring> load_settings() {
    std::map<std::wstring, std::wstring> m;
    std::string d;
    if (read_file(settings_path(), d))
        for (auto &l : lines_of(d)) {
            auto f = split(l, L'\t');
            if (f.size() >= 2) m[f[0]] = f[1];
        }
    return m;
}

static bool windows_dark() {
    DWORD v = 1, sz = sizeof v;
    wchar_t env[16];
    if (GetEnvironmentVariableW(L"FOLIO_THEME", env, 16)) return lower(env) == L"dark";
    if (RegGetValueW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
                     L"AppsUseLightTheme", RRF_RT_REG_DWORD, nullptr, &v, &sz) == ERROR_SUCCESS)
        return v == 0;
    return false;
}

// the title bar in Chord's fuchsia, as on Linux (Windows 11; older Windows keeps its own)
static void apply_title_colour() {
    BOOL dark = g_dark;
    DwmSetWindowAttribute(g_wnd, 20 /* DWMWA_USE_IMMERSIVE_DARK_MODE */, &dark, sizeof dark);
    COLORREF cap = C_ACCENT(), text = RGB(255, 255, 255);
    DwmSetWindowAttribute(g_wnd, 35 /* DWMWA_CAPTION_COLOR */, &cap, sizeof cap);
    DwmSetWindowAttribute(g_wnd, 36 /* DWMWA_TEXT_COLOR */, &text, sizeof text);
}

static void apply_colours() {
    ListView_SetBkColor(g_list, C_LIST());
    ListView_SetTextBkColor(g_list, C_LIST());
    ListView_SetTextColor(g_list, C_FG());
    TreeView_SetBkColor(g_sources, C_SRC());
    TreeView_SetTextColor(g_sources, C_FG());
    // Windows 10 and 11 draw the list's header and the scroll bars dark with these themes
    SetWindowTheme(g_list, g_dark ? L"DarkMode_Explorer" : L"Explorer", nullptr);
    SetWindowTheme(ListView_GetHeader(g_list), g_dark ? L"DarkMode_ItemsView" : L"ItemsView", nullptr);
    SetWindowTheme(g_sources, g_dark ? L"DarkMode_Explorer" : L"Explorer", nullptr);
    SetWindowTheme(g_search, g_dark ? L"DarkMode_CFD" : nullptr, nullptr);
    apply_title_colour();
    InvalidateRect(g_wnd, nullptr, TRUE);
}

// ================================================================ input box
struct InputArgs { std::wstring title, prompt, value; };
static INT_PTR CALLBACK input_proc(HWND d, UINT m, WPARAM w, LPARAM l) {
    static InputArgs *a;
    if (m == WM_INITDIALOG) {
        a = (InputArgs *)l;
        SetWindowTextW(d, a->title.c_str());
        SetDlgItemTextW(d, IDC_PROMPT, a->prompt.c_str());
        SetDlgItemTextW(d, IDC_TEXT, a->value.c_str());
        SendDlgItemMessageW(d, IDC_TEXT, EM_SETSEL, 0, -1);
        return TRUE;
    }
    if (m == WM_COMMAND && (LOWORD(w) == IDOK || LOWORD(w) == IDCANCEL)) {
        if (LOWORD(w) == IDOK) {
            wchar_t buf[2048];
            GetDlgItemTextW(d, IDC_TEXT, buf, 2048);
            a->value = buf;
        }
        EndDialog(d, LOWORD(w));
        return TRUE;
    }
    return FALSE;
}

static bool ask_text(const std::wstring &title, const std::wstring &prompt, std::wstring &value) {
    InputArgs a{title, prompt, value};
    if (DialogBoxParamW(g_inst, MAKEINTRESOURCEW(IDD_INPUT), g_wnd, input_proc, (LPARAM)&a) != IDOK) return false;
    value = trim(a.value);
    return true;
}

// ================================================================ the play queue
static void update_controls();
static void fill_list();
static void fill_sources();
static void select_source(int kind, int id);

static void make_order(int first) {
    g_order.clear();
    for (int i = 0; i < (int)g_queue.size(); i++) g_order.push_back(i);
    if (g_shuffle && !g_order.empty()) {
        static std::mt19937 rng((unsigned)time(nullptr));
        std::shuffle(g_order.begin(), g_order.end(), rng);
        auto it = std::find(g_order.begin(), g_order.end(), first);
        if (it != g_order.end()) std::iter_swap(g_order.begin(), it);
    }
}

static void start(const QItem &q) {
    g_now = q;
    g_has_now = true;
    std::wstring url = q.url;
    if (q.kind == 3) {
        // a station given as a playlist: open the stream inside it (off the window's thread)
        g_busy = L"Connecting to " + q.title + L"…";
        InvalidateRect(g_lcd, nullptr, FALSE);
        QItem qq = q;
        auto *real = new std::wstring;
        background([qq, real]() { *real = radio_resolve(qq.url); },
                   [real]() {
                       g_busy.clear();
                       if (!g_player->open(*real)) flash(L"“" + g_now.title + L"” couldn't be played: " + g_player->last_error);
                       delete real;
                   });
    } else if (!g_player->open(url)) {
        flash(L"“" + q.title + L"” couldn't be played: " + g_player->last_error);
    }
    update_controls();
    InvalidateRect(g_list, nullptr, FALSE);
}

static void play_queue(const std::vector<QItem> &items, int index) {
    if (items.empty()) return;
    g_queue = items;
    make_order(index);
    g_pos = (int)(std::find(g_order.begin(), g_order.end(), index) - g_order.begin());
    start(g_queue[g_order[g_pos]]);
}

static QItem song_item(const Track &t) {
    QItem q;
    q.kind = 1;
    q.id = t.id;
    q.url = t.path;
    q.title = t.title;
    q.artist = t.artist;
    q.duration = t.duration;
    return q;
}

static QItem episode_item(const Episode &e) {
    QItem q;
    q.kind = 2;
    q.id = e.show;
    q.key = e.guid;
    q.url = e.url;
    q.title = e.title;
    Show *s = g_online.show(e.show);
    q.artist = s ? s->title : L"";
    q.duration = e.duration;
    return q;
}

static QItem station_item(const Station &s) {
    QItem q;
    q.kind = 3;
    q.key = s.uuid;
    q.url = s.url;
    q.title = s.name;
    q.artist = s.tags.substr(0, s.tags.find(L','));
    return q;
}

static void next(bool user) {
    if (g_queue.empty() || g_order.empty()) { g_player->stop(); g_has_now = false; update_controls(); return; }
    if (g_repeat == 2 && !user) { start(g_queue[g_order[g_pos]]); return; }
    g_pos++;
    if (g_pos >= (int)g_order.size()) {
        if (g_repeat == 0) {
            g_pos = (int)g_order.size() - 1;
            g_player->stop();
            g_has_now = false;
            update_controls();
            return;
        }
        make_order(-1);
        g_pos = 0;
    }
    start(g_queue[g_order[g_pos]]);
}

static void previous() {
    if (g_player->position() > 3) { g_player->seek(0); return; }
    if (g_order.empty()) return;
    if (g_pos > 0) g_pos--;
    else if (g_repeat == 1) g_pos = (int)g_order.size() - 1;
    start(g_queue[g_order[g_pos]]);
}

static void remember_episode_position() {
    if (!g_has_now || g_now.kind != 2) return;
    for (auto &e : g_online.episodes)
        if (e.show == g_now.id && e.guid == g_now.key) {
            double pos = g_player->position(), dur = g_player->duration();
            e.position = pos;
            if (dur > 0 && pos > dur - 30) { e.played = true; e.position = 0; }
        }
}

// ================================================================ the list
static std::wstring col_text(const Row &r, int col);

struct ColumnSet { std::vector<std::pair<const wchar_t *, int>> cols; };

static ColumnSet columns_for(int src) {
    switch (src) {
        case SRC_MUSIC: case SRC_PLAYLIST:
            return {{{L"Name", 260}, {L"Time", 60}, {L"Artist", 170}, {L"Album", 170}, {L"Genre", 100}, {L"Rating", 80}, {L"Plays", 50}}};
        case SRC_RADIO_POPULAR: case SRC_RADIO_FAVS: case SRC_RADIO_RECENT: case SRC_RADIO_SEARCH:
            return {{{L"", 24}, {L"Station", 280}, {L"Genre", 200}, {L"Country", 130}, {L"Bit Rate", 70}}};
        case SRC_PODCASTS: case SRC_PODCAST_SEARCH:
            return {{{L"Podcast", 340}, {L"Author", 240}, {L"Episodes", 80}}};
        case SRC_SHOW:
            return {{{L"", 24}, {L"Episode", 380}, {L"Date", 180}, {L"Time", 70}}};
    }
    return {};
}

static int g_cols_for = -1;
static void set_columns() {
    int key = g_src == SRC_PLAYLIST ? SRC_MUSIC : g_src;
    if (key == g_cols_for) return;
    g_cols_for = key;
    while (ListView_DeleteColumn(g_list, 0)) {}
    auto cs = columns_for(g_src);
    for (size_t i = 0; i < cs.cols.size(); i++) {
        LVCOLUMNW c = {};
        c.mask = LVCF_TEXT | LVCF_WIDTH | LVCF_FMT;
        c.pszText = (LPWSTR)cs.cols[i].first;
        c.cx = cs.cols[i].second;
        c.fmt = (cs.cols[i].first == std::wstring(L"Time") || cs.cols[i].first == std::wstring(L"Plays")) ? LVCFMT_RIGHT : LVCFMT_LEFT;
        ListView_InsertColumn(g_list, (int)i, &c);
    }
    g_sort_col = -1;
}

static bool matches(const std::wstring &hay, const std::vector<std::wstring> &words) {
    std::wstring h = lower(hay);
    for (auto &w : words) if (h.find(w) == std::wstring::npos) return false;
    return true;
}

static std::wstring search_text() {
    wchar_t buf[512];
    GetWindowTextW(g_search, buf, 512);
    return trim(buf);
}

static void sort_rows() {
    if (g_sort_col < 0) return;
    std::stable_sort(g_rows.begin(), g_rows.end(), [](const Row &a, const Row &b) {
        if (a.kind == 1 && b.kind == 1) {
            const Track &x = g_lib.tracks[a.index], &y = g_lib.tracks[b.index];
            int c = 0;
            switch (g_sort_col) {
                case 1: c = x.duration < y.duration ? -1 : x.duration > y.duration; break;
                case 5: c = x.rating - y.rating; break;
                case 6: c = x.plays - y.plays; break;
                default: c = _wcsicmp(col_text(a, g_sort_col).c_str(), col_text(b, g_sort_col).c_str());
            }
            return g_sort_desc ? c > 0 : c < 0;
        }
        int c = _wcsicmp(col_text(a, g_sort_col).c_str(), col_text(b, g_sort_col).c_str());
        return g_sort_desc ? c > 0 : c < 0;
    });
}

static void update_status() {
    std::wstring s;
    if (g_src == SRC_MUSIC || g_src == SRC_PLAYLIST) {
        double total = 0;
        for (auto &r : g_rows) total += g_lib.tracks[r.index].duration;
        wchar_t b[128];
        swprintf(b, 128, L"%d songs, %.1f %ls", (int)g_rows.size(), total >= 3600 ? total / 3600 : total / 60,
                 total >= 3600 ? L"hours" : L"minutes");
        s = b;
    } else if (g_src == SRC_SHOW) s = std::to_wstring(g_rows.size()) + L" episodes";
    else if (g_src == SRC_PODCASTS || g_src == SRC_PODCAST_SEARCH) s = std::to_wstring(g_rows.size()) + L" podcasts";
    else s = std::to_wstring(g_rows.size()) + L" stations";
    SendMessageW(g_status, SB_SETTEXTW, 0, (LPARAM)s.c_str());
}

static void fill_list() {
    set_columns();
    g_rows.clear();
    std::wstring q = lower(search_text());
    std::vector<std::wstring> words;
    for (auto &w : split(q, L' ')) if (!w.empty()) words.push_back(w);
    std::lock_guard<std::recursive_mutex> g(g_lib.lock);
    if (g_src == SRC_MUSIC) {
        for (size_t i = 0; i < g_lib.tracks.size(); i++) {
            auto &t = g_lib.tracks[i];
            if (words.empty() || matches(t.title + L" " + t.artist + L" " + t.album + L" " + t.genre, words))
                g_rows.push_back({1, (int)i});
        }
        if (g_sort_col < 0)
            std::stable_sort(g_rows.begin(), g_rows.end(), [](const Row &a, const Row &b) {
                const Track &x = g_lib.tracks[a.index], &y = g_lib.tracks[b.index];
                std::wstring ax = x.album_artist.empty() ? x.artist : x.album_artist, ay = y.album_artist.empty() ? y.artist : y.album_artist;
                int c = _wcsicmp(ax.c_str(), ay.c_str());
                if (c) return c < 0;
                c = _wcsicmp(x.album.c_str(), y.album.c_str());
                if (c) return c < 0;
                if (x.disc_no != y.disc_no) return x.disc_no < y.disc_no;
                if (x.track_no != y.track_no) return x.track_no < y.track_no;
                return _wcsicmp(x.title.c_str(), y.title.c_str()) < 0;
            });
    } else if (g_src == SRC_PLAYLIST) {
        if (Playlist *p = g_lib.playlist(g_src_id))
            for (int id : p->tracks)
                for (size_t i = 0; i < g_lib.tracks.size(); i++)
                    if (g_lib.tracks[i].id == id) {
                        auto &t = g_lib.tracks[i];
                        if (words.empty() || matches(t.title + L" " + t.artist + L" " + t.album, words)) g_rows.push_back({1, (int)i});
                    }
    } else if (g_src == SRC_RADIO_FAVS || g_src == SRC_RADIO_RECENT) {
        g_stations = g_src == SRC_RADIO_FAVS ? g_online.favourites : g_online.recent;
        for (size_t i = 0; i < g_stations.size(); i++)
            if (words.empty() || matches(g_stations[i].name + L" " + g_stations[i].tags, words)) g_rows.push_back({2, (int)i});
    } else if (g_src == SRC_RADIO_POPULAR || g_src == SRC_RADIO_SEARCH) {
        for (size_t i = 0; i < g_stations.size(); i++) g_rows.push_back({2, (int)i});
    } else if (g_src == SRC_PODCASTS) {
        for (size_t i = 0; i < g_online.shows.size(); i++)
            if (words.empty() || matches(g_online.shows[i].title + L" " + g_online.shows[i].author, words)) g_rows.push_back({3, (int)i});
    } else if (g_src == SRC_PODCAST_SEARCH) {
        for (size_t i = 0; i < g_found.size(); i++) g_rows.push_back({5, (int)i});
    } else if (g_src == SRC_SHOW) {
        auto eps = g_online.episodes_of(g_src_id);
        for (auto *e : eps) {
            size_t idx = e - &g_online.episodes[0];
            if (words.empty() || matches(e->title, words)) g_rows.push_back({4, (int)idx});
        }
    }
    sort_rows();
    ListView_SetItemCountEx(g_list, (int)g_rows.size(), LVSICF_NOINVALIDATEALL);
    InvalidateRect(g_list, nullptr, TRUE);
    update_status();
}

static std::wstring stars(int rating) {
    int n = (rating + 10) / 20;
    std::wstring s;
    for (int i = 0; i < 5; i++) s += i < n ? L"★" : L"·";
    return s;
}

static std::wstring col_text(const Row &r, int col) {
    if (r.kind == 1) {
        if (r.index >= (int)g_lib.tracks.size()) return L"";
        const Track &t = g_lib.tracks[r.index];
        switch (col) {
            case 0: return t.title;
            case 1: return fmt_time(t.duration);
            case 2: return t.artist;
            case 3: return t.album;
            case 4: return t.genre;
            case 5: return stars(t.rating);
            case 6: return t.plays ? std::to_wstring(t.plays) : L"";
        }
    } else if (r.kind == 2) {
        if (r.index >= (int)g_stations.size()) return L"";
        const Station &s = g_stations[r.index];
        switch (col) {
            case 0: return g_online.is_favourite(s.uuid) ? L"♥" : L"";
            case 1: return s.name;
            case 2: return s.tags;
            case 3: return s.country;
            case 4: return s.bitrate ? std::to_wstring(s.bitrate) + L" kbps" : L"";
        }
    } else if (r.kind == 3) {
        const Show &s = g_online.shows[r.index];
        switch (col) {
            case 0: return s.title;
            case 1: return s.author;
            case 2: return std::to_wstring(g_online.episodes_of(s.id).size());
        }
    } else if (r.kind == 5) {
        const Show &s = g_found[r.index];
        switch (col) {
            case 0: return s.title;
            case 1: return s.author;
            case 2: return L"";
        }
    } else if (r.kind == 4) {
        const Episode &e = g_online.episodes[r.index];
        switch (col) {
            case 0: return e.played ? L"" : L"●";
            case 1: return e.title;
            case 2: return e.date.size() > 16 ? e.date.substr(0, 16) : e.date;
            case 3: return e.duration > 0 ? fmt_time(e.duration) : L"";
        }
    }
    return L"";
}

static std::vector<int> selected_rows() {
    std::vector<int> out;
    int i = -1;
    for (;;) {
        int n = ListView_GetNextItem(g_list, i, LVNI_SELECTED);
        if (n < 0 || n <= i || n >= (int)g_rows.size()) break;      // never loop on a list that answers oddly
        out.push_back(n);
        i = n;
    }
    return out;
}

static std::vector<int> selected_track_ids() {
    std::vector<int> out;
    for (int i : selected_rows())
        if (i < (int)g_rows.size() && g_rows[i].kind == 1) out.push_back(g_lib.tracks[g_rows[i].index].id);
    return out;
}

static void play_row(int row) {
    if (row < 0 || row >= (int)g_rows.size()) return;
    const Row &r = g_rows[row];
    if (r.kind == 1) {
        std::vector<QItem> items;
        for (auto &x : g_rows) items.push_back(song_item(g_lib.tracks[x.index]));
        play_queue(items, row);
    } else if (r.kind == 2) {
        Station s = g_stations[r.index];
        g_queue.clear();
        g_order.clear();
        g_pos = -1;
        start(station_item(s));
        g_online.played_station(s);
        background([s]() { radio_clicked(s); }, []() {});
    } else if (r.kind == 4) {
        std::vector<QItem> items;
        for (auto &x : g_rows) items.push_back(episode_item(g_online.episodes[x.index]));
        play_queue(items, row);
        const Episode &e = g_online.episodes[r.index];
        if (e.position > 5) {
            double pos = e.position;
            g_now.duration = e.duration;
            // carry on where it was left once it has started
            static double resume_at;
            resume_at = pos;
            SetTimer(g_wnd, 78, 800, [](HWND, UINT, UINT_PTR id, DWORD) {
                if (g_player->active()) { g_player->seek(resume_at); KillTimer(g_wnd, id); }
            });
        }
    } else if (r.kind == 3) {
        // a show: open its episodes
        int id = g_online.shows[r.index].id;
        for (auto &kv : g_tree)
            if (kv.second.first == SRC_SHOW && kv.second.second == id) TreeView_SelectItem(g_sources, kv.first);
    } else if (r.kind == 5) {
        SendMessageW(g_wnd, WM_COMMAND, CMD_SUBSCRIBE_SELECTED, 0);
    }
}

// ================================================================ the sources
static HTREEITEM add_source(HTREEITEM parent, const std::wstring &text, int kind, int id) {
    TVINSERTSTRUCTW ins = {};
    ins.hParent = parent;
    ins.hInsertAfter = TVI_LAST;
    ins.item.mask = TVIF_TEXT | TVIF_STATE;
    ins.item.pszText = (LPWSTR)text.c_str();
    ins.item.state = ins.item.stateMask = kind == SRC_HEADER ? TVIS_BOLD | TVIS_EXPANDED : TVIS_EXPANDED;
    HTREEITEM h = TreeView_InsertItem(g_sources, &ins);
    g_tree[h] = {kind, id};
    return h;
}

static bool g_filling_sources = false;
static void fill_sources() {
    g_filling_sources = true;
    TreeView_DeleteAllItems(g_sources);
    g_tree.clear();
    HTREEITEM lib = add_source(TVI_ROOT, L"LIBRARY", SRC_HEADER, 0);
    HTREEITEM sel = nullptr;
    HTREEITEM music = add_source(lib, L"Music", SRC_MUSIC, 0);
    HTREEITEM pods = add_source(lib, L"Podcasts", SRC_PODCASTS, 0);
    for (auto &s : g_online.shows) {
        HTREEITEM h = add_source(pods, s.title, SRC_SHOW, s.id);
        if (g_src == SRC_SHOW && g_src_id == s.id) sel = h;
    }
    HTREEITEM radio = add_source(lib, L"Radio", SRC_RADIO_POPULAR, 0);
    HTREEITEM favs = add_source(radio, L"Favourites", SRC_RADIO_FAVS, 0);
    HTREEITEM rec = add_source(radio, L"Recently Played", SRC_RADIO_RECENT, 0);
    HTREEITEM pls = add_source(TVI_ROOT, L"PLAYLISTS", SRC_HEADER, 0);
    for (auto &p : g_lib.playlists) {
        HTREEITEM h = add_source(pls, p.name, SRC_PLAYLIST, p.id);
        if (g_src == SRC_PLAYLIST && g_src_id == p.id) sel = h;
    }
    TreeView_Expand(g_sources, lib, TVE_EXPAND);
    TreeView_Expand(g_sources, pods, TVE_EXPAND);
    TreeView_Expand(g_sources, radio, TVE_EXPAND);
    TreeView_Expand(g_sources, pls, TVE_EXPAND);
    if (!sel) sel = g_src == SRC_PODCASTS || g_src == SRC_PODCAST_SEARCH ? pods
                  : g_src == SRC_RADIO_FAVS ? favs : g_src == SRC_RADIO_RECENT ? rec
                  : g_src == SRC_RADIO_POPULAR || g_src == SRC_RADIO_SEARCH ? radio : music;
    TreeView_SelectItem(g_sources, sel);
    g_filling_sources = false;
    select_source(g_src, g_src_id);
}

static void load_popular_stations() {
    g_busy = L"Loading the most popular stations…";
    InvalidateRect(g_lcd, nullptr, FALSE);
    auto *got = new std::vector<Station>;
    auto *err = new std::wstring;
    background([got, err]() { radio_top(*got, *err); },
               [got, err]() {
                   g_busy.clear();
                   if (got->empty() && !err->empty()) flash(L"The radio directory couldn't be reached: " + *err);
                   if (g_src == SRC_RADIO_POPULAR) { g_stations = *got; fill_list(); }
                   delete got;
                   delete err;
               });
}

static void select_source(int kind, int id) {
    g_src = kind;
    g_src_id = id;
    SetWindowTextW(g_search, L"");
    const wchar_t *cue = kind == SRC_PODCASTS ? L"Search the podcast directory"
                       : (kind >= SRC_RADIO_POPULAR && kind <= SRC_RADIO_SEARCH) ? L"Search stations"
                       : L"Search";
    SendMessageW(g_search, EM_SETCUEBANNER, TRUE, (LPARAM)cue);
    if (kind == SRC_RADIO_POPULAR) { g_stations.clear(); load_popular_stations(); }
    fill_list();
}

// ================================================================ the status display (LCD)
static RECT lcd_bar(const RECT &rc) {
    RECT b = {rc.left + 70, rc.bottom - 16, rc.right - 70, rc.bottom - 10};
    return b;
}

static void paint_lcd(HWND h, HDC hdc) {
    RECT rc;
    GetClientRect(h, &rc);
    HDC mem = CreateCompatibleDC(hdc);
    HBITMAP bmp = CreateCompatibleBitmap(hdc, rc.right, rc.bottom);
    HGDIOBJ old = SelectObject(mem, bmp);
    HBRUSH bg = CreateSolidBrush(C_BG());
    FillRect(mem, &rc, bg);
    DeleteObject(bg);
    COLORREF lcd1 = g_dark ? RGB(0x20, 0x25, 0x1c) : RGB(0xf3, 0xf4, 0xea), lcd_fg = g_dark ? RGB(0xe3, 0xed, 0xd2) : RGB(0x1e, 0x23, 0x16),
             lcd_dim = g_dark ? RGB(0xa9, 0xb6, 0x94) : RGB(0x52, 0x5a, 0x44), line = g_dark ? RGB(0x4c, 0x56, 0x41) : RGB(0x8f, 0x9a, 0x7c);
    HBRUSH b = CreateSolidBrush(lcd1);
    HPEN p = CreatePen(PS_SOLID, 1, line);
    SelectObject(mem, b);
    SelectObject(mem, p);
    RoundRect(mem, 0, 0, rc.right, rc.bottom, 10, 10);
    DeleteObject(b);
    DeleteObject(p);
    SetBkMode(mem, TRANSPARENT);
    SetTextColor(mem, lcd_fg);
    RECT t = {12, 6, rc.right - 12, 24};
    std::wstring line1, line2;
    bool show_msg = !g_lcd_message.empty() && GetTickCount() < g_lcd_message_until;
    if (!g_busy.empty()) line1 = g_busy;
    else if (show_msg) line1 = g_lcd_message;
    else if (g_has_now) { line1 = g_now.title; line2 = g_now.artist; }
    else line1 = L"Folio Chord";
    SelectObject(mem, g_font_bold);
    DrawTextW(mem, line1.c_str(), -1, &t, DT_CENTER | DT_SINGLELINE | DT_END_ELLIPSIS | DT_NOPREFIX);
    if (!line2.empty()) {
        SelectObject(mem, g_font_small);
        SetTextColor(mem, lcd_dim);
        RECT t2 = {12, 23, rc.right - 12, 38};
        DrawTextW(mem, line2.c_str(), -1, &t2, DT_CENTER | DT_SINGLELINE | DT_END_ELLIPSIS | DT_NOPREFIX);
    }
    if (g_has_now && g_busy.empty() && !show_msg) {
        double pos = g_player->position(), dur = g_player->duration();
        SelectObject(mem, g_font_small);
        SetTextColor(mem, lcd_fg);
        RECT bar = lcd_bar(rc);
        if (dur > 0) {
            RECT l = {8, bar.top - 5, bar.left - 6, bar.bottom + 5}, r = {bar.right + 6, bar.top - 5, rc.right - 8, bar.bottom + 5};
            DrawTextW(mem, fmt_time(pos).c_str(), -1, &l, DT_RIGHT | DT_SINGLELINE | DT_VCENTER);
            DrawTextW(mem, (L"-" + fmt_time(dur - pos)).c_str(), -1, &r, DT_LEFT | DT_SINGLELINE | DT_VCENTER);
            HBRUSH trough = CreateSolidBrush(g_dark ? RGB(0x3a, 0x42, 0x32) : RGB(0xc3, 0xc9, 0xb1));
            FillRect(mem, &bar, trough);
            DeleteObject(trough);
            RECT fill = bar;
            fill.right = bar.left + (LONG)((bar.right - bar.left) * std::min(1.0, pos / dur));
            HBRUSH fb = CreateSolidBrush(g_dark ? RGB(0xc9, 0xd6, 0xb3) : RGB(0x59, 0x63, 0x4a));
            FillRect(mem, &fill, fb);
            DeleteObject(fb);
        } else if (g_now.kind == 3) {
            RECT l = {12, bar.top - 6, rc.right - 12, bar.bottom + 6};
            DrawTextW(mem, (L"Live • " + fmt_time(pos)).c_str(), -1, &l, DT_CENTER | DT_SINGLELINE | DT_VCENTER);
        }
    }
    BitBlt(hdc, 0, 0, rc.right, rc.bottom, mem, 0, 0, SRCCOPY);
    SelectObject(mem, old);
    DeleteObject(bmp);
    DeleteDC(mem);
}

static LRESULT CALLBACK lcd_proc(HWND h, UINT m, WPARAM w, LPARAM l) {
    switch (m) {
        case WM_PAINT: {
            PAINTSTRUCT ps;
            HDC hdc = BeginPaint(h, &ps);
            paint_lcd(h, hdc);
            EndPaint(h, &ps);
            return 0;
        }
        case WM_ERASEBKGND: return 1;
        case WM_LBUTTONDOWN: {
            RECT rc;
            GetClientRect(h, &rc);
            RECT bar = lcd_bar(rc);
            int x = GET_X_LPARAM(l), y = GET_Y_LPARAM(l);
            double dur = g_player->duration();
            if (dur > 0 && y >= bar.top - 6 && x >= bar.left && x <= bar.right) {
                g_player->seek(dur * (x - bar.left) / (double)(bar.right - bar.left));
                InvalidateRect(h, nullptr, FALSE);
            }
            return 0;
        }
    }
    return DefWindowProcW(h, m, w, l);
}

static void update_controls() {
    SetWindowTextW(g_play, g_player && g_player->playing() ? L"Pause" : L"Play");
    InvalidateRect(g_play, nullptr, FALSE);
    HMENU menu = GetMenu(g_wnd);
    CheckMenuItem(menu, CMD_SHUFFLE, g_shuffle ? MF_CHECKED : MF_UNCHECKED);
    CheckMenuRadioItem(menu, CMD_REPEAT_OFF, CMD_REPEAT_ONE, CMD_REPEAT_OFF + g_repeat, MF_BYCOMMAND);
    InvalidateRect(g_lcd, nullptr, FALSE);
    if (ca::g_visible) ca::redraw_all();
}

static void set_volume(double v) {
    g_vol = std::max(0.0, std::min(1.0, v));
    g_player->set_volume(g_vol);
    SendMessageW(g_volume, TBM_SETPOS, TRUE, (LPARAM)(g_vol * 100));
}

// ================================================================ menus
static HMENU g_add_to_menu;

static HMENU build_menu() {
    HMENU bar = CreateMenu();
    auto add = [](HMENU m, UINT id, const wchar_t *t) { AppendMenuW(m, MF_STRING, id, t); };
    auto sep = [](HMENU m) { AppendMenuW(m, MF_SEPARATOR, 0, nullptr); };
    HMENU f = CreatePopupMenu();
    add(f, CMD_ADD_FILE, L"Add &File to Library…\tCtrl+O");
    add(f, CMD_ADD_FOLDER, L"Add F&older to Library…\tCtrl+Shift+O");
    add(f, CMD_RESCAN, L"Check Music Folders &Again");
    sep(f);
    add(f, CMD_NEW_PLAYLIST, L"&New Playlist\tCtrl+N");
    sep(f);
    add(f, CMD_IMPORT_CD, L"&Import CD");
    add(f, CMD_BURN, L"&Burn Playlist to Disc…");
    sep(f);
    add(f, CMD_EXIT, L"E&xit\tAlt+F4");
    AppendMenuW(bar, MF_POPUP, (UINT_PTR)f, L"&File");
    HMENU e = CreatePopupMenu();
    add(e, CMD_SELECT_ALL, L"Select &All\tCtrl+A");
    add(e, CMD_DELETE, L"&Delete\tDel");
    sep(e);
    add(e, CMD_GET_INFO, L"Get &Info\tCtrl+I");
    HMENU r = CreatePopupMenu();
    const wchar_t *R[] = {L"None", L"★", L"★★", L"★★★", L"★★★★", L"★★★★★"};
    for (int i = 5; i >= 0; i--) add(r, CMD_RATE0 + i, R[i]);
    AppendMenuW(e, MF_POPUP, (UINT_PTR)r, L"&Rating");
    g_add_to_menu = CreatePopupMenu();
    AppendMenuW(e, MF_POPUP, (UINT_PTR)g_add_to_menu, L"Add to &Playlist");
    add(e, CMD_SHOW_IN_EXPLORER, L"Show in &File Explorer\tCtrl+Shift+R");
    AppendMenuW(bar, MF_POPUP, (UINT_PTR)e, L"&Edit");
    HMENU v = CreatePopupMenu();
    add(v, CMD_GO_CURRENT, L"Go to &Current Song\tCtrl+L");
    sep(v);
    add(v, CMD_CHORDAMP, L"Look: &Chordamp");
    AppendMenuW(bar, MF_POPUP, (UINT_PTR)v, L"&View");
    HMENU c = CreatePopupMenu();
    add(c, CMD_PLAY_PAUSE, L"&Play/Pause\tSpace");
    add(c, CMD_STOP, L"&Stop\tCtrl+.");
    add(c, CMD_NEXT, L"&Next\tCtrl+Right");
    add(c, CMD_PREV, L"P&revious\tCtrl+Left");
    sep(c);
    add(c, CMD_VOL_UP, L"&Increase Volume\tCtrl+Up");
    add(c, CMD_VOL_DOWN, L"&Decrease Volume\tCtrl+Down");
    add(c, CMD_MUTE, L"&Mute\tCtrl+Alt+Down");
    sep(c);
    add(c, CMD_SHUFFLE, L"S&huffle\tCtrl+S");
    HMENU rep = CreatePopupMenu();
    add(rep, CMD_REPEAT_OFF, L"&Off");
    add(rep, CMD_REPEAT_ALL, L"&All");
    add(rep, CMD_REPEAT_ONE, L"O&ne");
    AppendMenuW(c, MF_POPUP, (UINT_PTR)rep, L"R&epeat");
    AppendMenuW(bar, MF_POPUP, (UINT_PTR)c, L"&Controls");
    HMENU s = CreatePopupMenu();
    add(s, CMD_STORE_SEARCH, L"Search the Store");
    add(s, CMD_STORE_SIGNIN, L"Sign In…");
    AppendMenuW(bar, MF_POPUP, (UINT_PTR)s, L"&Store");
    HMENU a = CreatePopupMenu();
    add(a, CMD_OPEN_STREAM, L"Open &Stream…\tCtrl+U");
    add(a, CMD_SUBSCRIBE_URL, L"S&ubscribe to Podcast…");
    add(a, CMD_REFRESH_PODCASTS, L"&Refresh All Podcasts");
    sep(a);
    add(a, CMD_CONVERT, L"Create &MP3 Version");
    add(a, CMD_ORGANIZE, L"&Organize Music Folder…");
    AppendMenuW(bar, MF_POPUP, (UINT_PTR)a, L"&Advanced");
    HMENU w = CreatePopupMenu();
    add(w, CMD_MINIMIZE, L"&Minimize\tCtrl+M");
    add(w, CMD_EQUALIZER, L"&Equalizer");
    add(w, CMD_MINI_PLAYER, L"Mini &Player");
    AppendMenuW(bar, MF_POPUP, (UINT_PTR)w, L"&Window");
    HMENU h = CreatePopupMenu();
    add(h, CMD_SHORTCUTS, L"&Keyboard Shortcuts\tF1");
    add(h, CMD_ABOUT, L"&About Folio Chord");
    AppendMenuW(bar, MF_POPUP, (UINT_PTR)h, L"&Help");
    return bar;
}

static void fill_add_to_menu(HMENU m) {
    while (GetMenuItemCount(m) > 0) DeleteMenu(m, 0, MF_BYPOSITION);
    AppendMenuW(m, MF_STRING, CMD_ADD_TO_PLAYLIST_NEW, L"New Playlist…");
    if (!g_lib.playlists.empty()) AppendMenuW(m, MF_SEPARATOR, 0, nullptr);
    for (size_t i = 0; i < g_lib.playlists.size(); i++)
        AppendMenuW(m, MF_STRING, CMD_PLAYLIST_BASE + (UINT)i, g_lib.playlists[i].name.c_str());
}

static HACCEL build_accels() {
    ACCEL a[] = {
        {FCONTROL | FVIRTKEY, 'O', CMD_ADD_FILE}, {FCONTROL | FSHIFT | FVIRTKEY, 'O', CMD_ADD_FOLDER},
        {FCONTROL | FVIRTKEY, 'N', CMD_NEW_PLAYLIST}, {FCONTROL | FVIRTKEY, 'A', CMD_SELECT_ALL},
        {FCONTROL | FVIRTKEY, 'I', CMD_GET_INFO}, {FCONTROL | FSHIFT | FVIRTKEY, 'R', CMD_SHOW_IN_EXPLORER},
        {FCONTROL | FVIRTKEY, 'L', CMD_GO_CURRENT}, {FCONTROL | FVIRTKEY, VK_OEM_PERIOD, CMD_STOP},
        {FCONTROL | FVIRTKEY, VK_RIGHT, CMD_NEXT}, {FCONTROL | FVIRTKEY, VK_LEFT, CMD_PREV},
        {FCONTROL | FVIRTKEY, VK_UP, CMD_VOL_UP}, {FCONTROL | FVIRTKEY, VK_DOWN, CMD_VOL_DOWN},
        {FCONTROL | FALT | FVIRTKEY, VK_DOWN, CMD_MUTE}, {FCONTROL | FVIRTKEY, 'S', CMD_SHUFFLE},
        {FCONTROL | FVIRTKEY, 'U', CMD_OPEN_STREAM}, {FCONTROL | FVIRTKEY, 'M', CMD_MINIMIZE},
        {FVIRTKEY, VK_F1, CMD_SHORTCUTS}, {FCONTROL | FSHIFT | FVIRTKEY, 'W', CMD_CHORDAMP}, {FCONTROL | FALT | FVIRTKEY, 'E', CMD_EQUALIZER},
    };
    return CreateAcceleratorTableW(a, sizeof a / sizeof a[0]);
}

// ================================================================ commands
static void add_paths(std::vector<std::wstring> paths, bool play) {
    g_busy = L"Adding to the library…";
    InvalidateRect(g_lcd, nullptr, FALSE);
    auto *ids = new std::vector<int>;
    background(
        [paths, ids]() {
            for (auto &p : paths) {
                DWORD a = GetFileAttributesW(p.c_str());
                if (a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY)) {
                    auto got = g_lib.add_folder(p, [](int n) {
                        g_busy = L"Adding to the library… " + std::to_wstring(n);
                        InvalidateRect(g_lcd, nullptr, FALSE);
                    });
                    ids->insert(ids->end(), got.begin(), got.end());
                } else if (int id = g_lib.add_file(p)) ids->push_back(id);
            }
            g_lib.save();
        },
        [ids, play]() {
            g_busy.clear();
            fill_list();
            flash(std::to_wstring(ids->size()) + (ids->size() == 1 ? L" song" : L" songs") + L" added");
            if (play && !ids->empty()) {
                std::vector<QItem> items;
                for (int id : *ids) if (Track *t = g_lib.find(id)) items.push_back(song_item(*t));
                play_queue(items, 0);
            }
            delete ids;
        });
}

static std::vector<std::wstring> choose_files() {
    std::vector<wchar_t> buf(65536, 0);
    OPENFILENAMEW o = {sizeof o};
    o.hwndOwner = g_wnd;
    o.lpstrFilter = L"Music\0*.mp3;*.m4a;*.m4b;*.aac;*.flac;*.wav;*.wma;*.aif;*.aiff;*.alac;*.ogg;*.opus\0All files\0*.*\0";
    o.lpstrFile = buf.data();
    o.nMaxFile = (DWORD)buf.size();
    o.lpstrTitle = L"Add to Library";
    o.Flags = OFN_ALLOWMULTISELECT | OFN_EXPLORER | OFN_FILEMUSTEXIST;
    std::vector<std::wstring> out;
    if (!GetOpenFileNameW(&o)) return out;
    std::wstring dir = buf.data();
    const wchar_t *p = buf.data() + dir.size() + 1;
    if (!*p) out.push_back(dir);
    while (*p) { out.push_back(dir + L"\\" + p); p += wcslen(p) + 1; }
    return out;
}

static std::wstring choose_folder() {
    std::wstring out;
    IFileOpenDialog *d = nullptr;
    if (SUCCEEDED(CoCreateInstance(CLSID_FileOpenDialog, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&d)))) {
        DWORD opts = 0;
        d->GetOptions(&opts);
        d->SetOptions(opts | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM);
        d->SetTitle(L"Add Folder to Library");
        if (SUCCEEDED(d->Show(g_wnd))) {
            IShellItem *it = nullptr;
            if (SUCCEEDED(d->GetResult(&it))) {
                PWSTR p = nullptr;
                if (SUCCEEDED(it->GetDisplayName(SIGDN_FILESYSPATH, &p))) { out = p; CoTaskMemFree(p); }
                it->Release();
            }
        }
        d->Release();
    }
    return out;
}

static void subscribe(const std::wstring &feed) {
    g_busy = L"Subscribing…";
    InvalidateRect(g_lcd, nullptr, FALSE);
    auto *show = new Show;
    auto *eps = new std::vector<Episode>;
    auto *err = new std::wstring;
    auto *ok = new bool(false);
    background([=]() { *ok = podcast_fetch(feed, *show, *eps, *err); },
               [=]() {
                   g_busy.clear();
                   if (*ok) {
                       int id = g_online.subscribe(*show, *eps);
                       g_src = SRC_SHOW;
                       g_src_id = id;
                       fill_sources();
                       flash(L"Subscribed to " + show->title);
                   } else info(L"That podcast couldn't be subscribed to: " + *err);
                   delete show; delete eps; delete err; delete ok;
               });
}

static void refresh_shows(std::vector<Show> shows) {
    if (shows.empty()) return;
    g_busy = L"Refreshing podcasts…";
    InvalidateRect(g_lcd, nullptr, FALSE);
    auto *results = new std::vector<std::pair<int, std::vector<Episode>>>;
    background([shows, results]() {
                   for (auto &s : shows) {
                       Show tmp;
                       std::vector<Episode> eps;
                       std::wstring err;
                       if (podcast_fetch(s.feed, tmp, eps, err)) results->push_back({s.id, eps});
                   }
               },
               [results]() {
                   g_busy.clear();
                   int added = 0;
                   for (auto &r : *results) added += g_online.merge(r.first, r.second);
                   flash(added ? std::to_wstring(added) + L" new episodes" : L"No new episodes");
                   fill_list();
                   delete results;
               });
}

static void show_info() {
    auto ids = selected_track_ids();
    if (ids.empty()) return;
    Track *t = g_lib.find(ids[0]);
    if (!t) return;
    std::wstring s = t->title + L"\n" + t->artist + L"\n" + t->album + L"\n\n";
    s += L"Genre: " + t->genre + L"\n";
    if (t->year) s += L"Year: " + std::to_wstring(t->year) + L"\n";
    if (t->track_no) s += L"Track: " + std::to_wstring(t->track_no) + L"\n";
    s += L"Time: " + fmt_time(t->duration) + L"\n";
    if (t->bitrate) s += L"Bit rate: " + std::to_wstring(t->bitrate) + L" kbps\n";
    s += L"Plays: " + std::to_wstring(t->plays) + L"\n\n" + t->path;
    info(s, L"Get Info");
}

static void on_command(int id) {
    if (id >= CMD_PLAYLIST_BASE && id < CMD_PLAYLIST_BASE + 1000) {
        size_t i = id - CMD_PLAYLIST_BASE;
        if (i < g_lib.playlists.size()) {
            for (int t : selected_track_ids()) g_lib.playlists[i].tracks.push_back(t);
            g_lib.save();
            flash(L"Added to " + g_lib.playlists[i].name);
        }
        return;
    }
    switch (id) {
        case CMD_ADD_FILE: { auto f = choose_files(); if (!f.empty()) add_paths(f, false); break; }
        case CMD_ADD_FOLDER: { auto f = choose_folder(); if (!f.empty()) add_paths({f}, false); break; }
        case CMD_RESCAN: add_paths(g_lib.folders, false); break;
        case CMD_NEW_PLAYLIST: case CMD_ADD_TO_PLAYLIST_NEW: {
            std::wstring name = L"untitled playlist";
            if (!ask_text(L"New Playlist", L"Name of the playlist:", name) || name.empty()) break;
            int pid = g_lib.new_playlist(name);
            if (id == CMD_ADD_TO_PLAYLIST_NEW)
                for (int t : selected_track_ids()) g_lib.playlist(pid)->tracks.push_back(t);
            g_lib.save();
            g_src = SRC_PLAYLIST;
            g_src_id = pid;
            fill_sources();
            break;
        }
        case CMD_RENAME_PLAYLIST: {
            Playlist *p = g_lib.playlist(g_src_id);
            if (!p) break;
            std::wstring name = p->name;
            if (ask_text(L"Rename Playlist", L"Name of the playlist:", name) && !name.empty()) {
                p->name = name;
                g_lib.save();
                fill_sources();
            }
            break;
        }
        case CMD_DELETE_PLAYLIST:
            if (g_src == SRC_PLAYLIST && (g_selftest || MessageBoxW(g_wnd, L"Delete this playlist? The songs stay in your library.",
                                                                    L"Folio Chord", MB_OKCANCEL | MB_ICONQUESTION) == IDOK)) {
                g_lib.delete_playlist(g_src_id);
                g_lib.save();
                g_src = SRC_MUSIC;
                fill_sources();
            }
            break;
        case CMD_EXIT: DestroyWindow(g_wnd); break;
        case CMD_SELECT_ALL: ListView_SetItemState(g_list, -1, LVIS_SELECTED, LVIS_SELECTED); break;
        case CMD_DELETE: {
            auto ids = selected_track_ids();
            if (ids.empty()) {
                if (g_src == SRC_SHOW) SendMessageW(g_wnd, WM_COMMAND, CMD_UNSUBSCRIBE, 0);
                break;
            }
            if (g_src == SRC_PLAYLIST) {
                if (Playlist *p = g_lib.playlist(g_src_id)) {
                    auto rows = selected_rows();
                    std::vector<int> keep;
                    for (size_t i = 0; i < p->tracks.size(); i++)
                        if (std::find(rows.begin(), rows.end(), (int)i) == rows.end()) keep.push_back(p->tracks[i]);
                    p->tracks = keep;
                }
            } else {
                std::wstring q = ids.size() == 1 ? L"Remove this song from your library? The file stays on your computer."
                                                 : L"Remove these " + std::to_wstring(ids.size()) + L" songs from your library? The files stay on your computer.";
                if (!g_selftest && MessageBoxW(g_wnd, q.c_str(), L"Folio Chord", MB_OKCANCEL | MB_ICONQUESTION) != IDOK) break;
                g_lib.remove(ids);
            }
            g_lib.save();
            ListView_SetItemState(g_list, -1, 0, LVIS_SELECTED);
            fill_list();
            break;
        }
        case CMD_GET_INFO: show_info(); break;
        case CMD_RATE0: case CMD_RATE1: case CMD_RATE2: case CMD_RATE3: case CMD_RATE4: case CMD_RATE5:
            for (int t : selected_track_ids()) if (Track *x = g_lib.find(t)) x->rating = (id - CMD_RATE0) * 20;
            g_lib.save();
            InvalidateRect(g_list, nullptr, FALSE);
            break;
        case CMD_SHOW_IN_EXPLORER: {
            auto ids = selected_track_ids();
            if (ids.empty()) break;
            if (Track *t = g_lib.find(ids[0])) {
                std::wstring args = L"/select,\"" + t->path + L"\"";
                ShellExecuteW(g_wnd, nullptr, L"explorer.exe", args.c_str(), nullptr, SW_SHOWNORMAL);
            }
            break;
        }
        case CMD_PLAY_SELECTION: {
            auto rows = selected_rows();
            play_row(rows.empty() ? 0 : rows[0]);
            break;
        }
        case CMD_GO_CURRENT:
            if (g_has_now && g_now.kind == 1) {
                if (g_src != SRC_MUSIC) { g_src = SRC_MUSIC; fill_sources(); }
                SetWindowTextW(g_search, L"");
                fill_list();
                for (size_t i = 0; i < g_rows.size(); i++)
                    if (g_lib.tracks[g_rows[i].index].id == g_now.id) {
                        ListView_SetItemState(g_list, -1, 0, LVIS_SELECTED);
                        ListView_SetItemState(g_list, (int)i, LVIS_SELECTED | LVIS_FOCUSED, LVIS_SELECTED | LVIS_FOCUSED);
                        ListView_EnsureVisible(g_list, (int)i, FALSE);
                    }
            }
            break;
        case CMD_PLAY_PAUSE:
            if (g_player->active()) {
                if (g_now.kind == 3 && g_player->playing()) g_player->stop();     // a station stops rather than pausing
                else g_player->toggle();
            } else if (g_has_now) start(g_now);
            else SendMessageW(g_wnd, WM_COMMAND, CMD_PLAY_SELECTION, 0);
            update_controls();
            break;
        case CMD_STOP: remember_episode_position(); g_player->stop(); update_controls(); break;
        case CMD_NEXT: remember_episode_position(); next(true); break;
        case CMD_PREV: previous(); break;
        case CMD_VOL_UP: set_volume(g_vol + 0.1); break;
        case CMD_VOL_DOWN: set_volume(g_vol - 0.1); break;
        case CMD_MUTE:
            if (g_muted) { g_muted = false; set_volume(g_vol_before_mute); }
            else { g_muted = true; g_vol_before_mute = g_vol; set_volume(0); }
            break;
        case CMD_SHUFFLE: {
            g_shuffle = !g_shuffle;
            int cur = g_pos >= 0 && g_pos < (int)g_order.size() ? g_order[g_pos] : -1;
            make_order(cur);
            g_pos = cur >= 0 ? (int)(std::find(g_order.begin(), g_order.end(), cur) - g_order.begin()) : -1;
            update_controls();
            save_settings();
            break;
        }
        case CMD_REPEAT_OFF: case CMD_REPEAT_ALL: case CMD_REPEAT_ONE:
            g_repeat = id - CMD_REPEAT_OFF;
            update_controls();
            save_settings();
            break;
        case CMD_OPEN_STREAM: {
            std::wstring url;
            if (!ask_text(L"Open Stream", L"Address of the stream (http://… or https://…):", url) || url.find(L"://") == std::wstring::npos) break;
            Station s;
            s.uuid = L"custom:" + url;
            s.name = url;
            s.url = url;
            g_queue.clear();
            g_order.clear();
            start(station_item(s));
            break;
        }
        case CMD_SUBSCRIBE_URL: {
            std::wstring url;
            if (ask_text(L"Subscribe to Podcast", L"Address of the podcast's feed:", url) && url.find(L"://") != std::wstring::npos)
                subscribe(url);
            break;
        }
        case CMD_SUBSCRIBE_SELECTED: {
            auto rows = selected_rows();
            if (!rows.empty() && g_rows[rows[0]].kind == 5) subscribe(g_found[g_rows[rows[0]].index].feed);
            break;
        }
        case CMD_REFRESH_PODCASTS: refresh_shows(g_online.shows); break;
        case CMD_REFRESH_SHOW:
            if (Show *s = g_online.show(g_src_id)) refresh_shows({*s});
            break;
        case CMD_UNSUBSCRIBE:
            if (Show *s = g_online.show(g_src_id)) {
                std::wstring q = L"Unsubscribe from “" + s->title + L"”?";
                if (g_selftest || MessageBoxW(g_wnd, q.c_str(), L"Folio Chord", MB_OKCANCEL | MB_ICONQUESTION) == IDOK) {
                    g_online.unsubscribe(g_src_id);
                    g_src = SRC_PODCASTS;
                    fill_sources();
                }
            }
            break;
        case CMD_MARK_PLAYED:
            for (int i : selected_rows())
                if (g_rows[i].kind == 4) g_online.episodes[g_rows[i].index].played = !g_online.episodes[g_rows[i].index].played;
            g_online.save();
            InvalidateRect(g_list, nullptr, FALSE);
            break;
        case CMD_FAVOURITE:
            for (int i : selected_rows())
                if (g_rows[i].kind == 2) {
                    Station s = g_stations[g_rows[i].index];
                    g_online.set_favourite(s, !g_online.is_favourite(s.uuid));
                }
            if (g_src == SRC_RADIO_FAVS) fill_list();
            InvalidateRect(g_list, nullptr, FALSE);
            break;
        case CMD_MINIMIZE: ShowWindow(g_wnd, SW_MINIMIZE); break;
        case CMD_ABOUT:
            info(L"Folio Chord for Windows " CHORD_VERSION L"\n\nMusic, internet radio and podcasts.\nPart of Folio Studio.", L"About Folio Chord");
            break;
        case CMD_SHORTCUTS:
            info(L"Space\tPlay / Pause\nCtrl+Right\tNext\nCtrl+Left\tPrevious\nCtrl+Up / Down\tVolume\nCtrl+S\tShuffle\n"
                 L"Ctrl+O\tAdd File\nCtrl+N\tNew Playlist\nCtrl+I\tGet Info\nCtrl+L\tGo to Current Song\nCtrl+U\tOpen Stream\nDel\tDelete",
                 L"Keyboard Shortcuts");
            break;
        case CMD_IMPORT_CD: not_here(L"Import CD"); break;
        case CMD_BURN: not_here(L"Burn Playlist to Disc"); break;
        case CMD_CHORDAMP: ca::switch_look(true); break;
        case CMD_EQUALIZER: ca::standard_equalizer(); break;
        case CMD_MINI_PLAYER: not_here(L"Mini Player"); break;
        case CMD_CONVERT: not_here(L"Create MP3 Version"); break;
        case CMD_ORGANIZE: not_here(L"Organize Music Folder"); break;
        case CMD_STORE_SEARCH: info(L"There is no store in Folio Chord: it plays your own music, radio and podcasts."); break;
        case CMD_STORE_SIGNIN: info(L"Folio Chord has no accounts and nothing to sign in to."); break;
    }
}

// ================================================================ search box: Enter searches online
static WNDPROC g_search_old;
static LRESULT CALLBACK search_proc(HWND h, UINT m, WPARAM w, LPARAM l) {
    if (m == WM_KEYDOWN && w == VK_RETURN) {
        std::wstring q = search_text();
        if (q.empty()) return 0;
        if (g_src == SRC_RADIO_POPULAR || g_src == SRC_RADIO_SEARCH) {
            g_src = SRC_RADIO_SEARCH;
            g_busy = L"Searching stations…";
            InvalidateRect(g_lcd, nullptr, FALSE);
            auto *got = new std::vector<Station>;
            auto *err = new std::wstring;
            background([q, got, err]() { radio_search(q, *got, *err); },
                       [got, err]() {
                           g_busy.clear();
                           g_stations = *got;
                           if (got->empty()) flash(err->empty() ? L"No stations found" : L"The radio directory couldn't be reached: " + *err);
                           fill_list();
                           delete got;
                           delete err;
                       });
            return 0;
        }
        if (g_src == SRC_PODCASTS || g_src == SRC_PODCAST_SEARCH) {
            g_src = SRC_PODCAST_SEARCH;
            g_busy = L"Searching podcasts…";
            InvalidateRect(g_lcd, nullptr, FALSE);
            auto *got = new std::vector<Show>;
            auto *err = new std::wstring;
            background([q, got, err]() { podcast_search(q, *got, *err); },
                       [got, err]() {
                           g_busy.clear();
                           g_found = *got;
                           if (got->empty()) flash(err->empty() ? L"No podcasts found" : L"The podcast directory couldn't be reached: " + *err);
                           fill_list();
                           delete got;
                           delete err;
                       });
            return 0;
        }
    }
    if (m == WM_CHAR && w == VK_RETURN) return 0;
    return CallWindowProcW(g_search_old, h, m, w, l);
}

// ================================================================ layout and the window
static void layout() {
    RECT rc;
    GetClientRect(g_wnd, &rc);
    SendMessageW(g_status, WM_SIZE, 0, 0);
    RECT sr;
    GetWindowRect(g_status, &sr);
    int sh = sr.bottom - sr.top;
    int w = rc.right, h = rc.bottom;
    int x = 12;
    MoveWindow(g_prev, x, 14, 40, 36, TRUE);
    MoveWindow(g_play, x + 44, 10, 46, 44, TRUE);
    MoveWindow(g_next, x + 94, 14, 40, 36, TRUE);
    MoveWindow(g_volume, x + 146, 20, 110, 26, TRUE);
    int lcdw = std::min(520, std::max(260, w - 640));
    MoveWindow(g_lcd, (w - lcdw) / 2, 6, lcdw, TOPBAR - 12, TRUE);
    MoveWindow(g_search, w - 232, 20, 220, 26, TRUE);
    MoveWindow(g_sources, 0, TOPBAR, SOURCES_W, h - TOPBAR - sh, TRUE);
    MoveWindow(g_list, SOURCES_W, TOPBAR, w - SOURCES_W, h - TOPBAR - sh, TRUE);
}

static HWND make_button(const wchar_t *text, int id, const wchar_t *tip) {
    HWND b = CreateWindowExW(0, L"BUTTON", text, WS_CHILD | WS_VISIBLE | BS_OWNERDRAW, 0, 0, 10, 10, g_wnd, (HMENU)(INT_PTR)id, g_inst, nullptr);
    SendMessageW(b, WM_SETFONT, (WPARAM)g_font_sym, TRUE);
    (void)tip;
    return b;
}

// the round transport buttons, drawn by Chord (no font needed for the symbols)
static void draw_button(DRAWITEMSTRUCT *d) {
    HDC dc = d->hDC;
    RECT r = d->rcItem;
    HBRUSH bg = CreateSolidBrush(g_dark ? RGB(0x3c, 0x3c, 0x3c) : RGB(0xd2, 0xd2, 0xd2));
    FillRect(dc, &r, bg);
    DeleteObject(bg);
    bool down = d->itemState & ODS_SELECTED;
    COLORREF face = down ? (g_dark ? RGB(0x30, 0x30, 0x30) : RGB(0xd8, 0xd8, 0xd8)) : (g_dark ? RGB(0x5a, 0x5a, 0x5a) : RGB(0xfa, 0xfa, 0xfa));
    HBRUSH fb = CreateSolidBrush(face);
    HPEN pen = CreatePen(PS_SOLID, 1, g_dark ? RGB(0x1c, 0x1c, 0x1c) : RGB(0x8a, 0x8a, 0x8a));
    HGDIOBJ ob = SelectObject(dc, fb), op = SelectObject(dc, pen);
    Ellipse(dc, r.left + 1, r.top + 1, r.right - 1, r.bottom - 1);
    COLORREF ink = g_dark ? RGB(0xec, 0xec, 0xec) : RGB(0x26, 0x26, 0x26);
    HBRUSH ib = CreateSolidBrush(ink);
    HPEN ip = CreatePen(PS_SOLID, 1, ink);
    SelectObject(dc, ib);
    SelectObject(dc, ip);
    int cx = (r.left + r.right) / 2, cy = (r.top + r.bottom) / 2, s = (r.bottom - r.top) / 5;
    int id = GetDlgCtrlID(d->hwndItem);
    auto tri = [&](int x0, int dir) {     // dir 1: pointing right
        POINT p[3] = {{x0, cy - s}, {x0, cy + s}, {x0 + dir * s * 3 / 2, cy}};
        Polygon(dc, p, 3);
    };
    if (id == IDC_PLAY) {
        if (g_player && g_player->playing()) {
            RECT a = {cx - s, cy - s, cx - s / 3, cy + s + 1}, b = {cx + s / 3, cy - s, cx + s, cy + s + 1};
            FillRect(dc, &a, ib);
            FillRect(dc, &b, ib);
        } else tri(cx - s / 2, 1);
    } else if (id == IDC_NEXT) {
        tri(cx - s * 3 / 2, 1);
        tri(cx, 1);
        RECT bar = {cx + s * 3 / 2, cy - s, cx + s * 3 / 2 + 2, cy + s + 1};
        FillRect(dc, &bar, ib);
    } else {
        tri(cx + s * 3 / 2, -1);
        tri(cx, -1);
        RECT bar = {cx - s * 3 / 2 - 2, cy - s, cx - s * 3 / 2, cy + s + 1};
        FillRect(dc, &bar, ib);
    }
    SelectObject(dc, ob);
    SelectObject(dc, op);
    DeleteObject(fb);
    DeleteObject(pen);
    DeleteObject(ib);
    DeleteObject(ip);
}

static void context_menu(int x, int y) {
    HMENU m = CreatePopupMenu();
    auto rows = selected_rows();
    if (g_src == SRC_MUSIC || g_src == SRC_PLAYLIST) {
        AppendMenuW(m, MF_STRING, CMD_PLAY_SELECTION, L"Play");
        AppendMenuW(m, MF_STRING, CMD_GET_INFO, L"Get Info");
        HMENU add = CreatePopupMenu();
        fill_add_to_menu(add);
        AppendMenuW(m, MF_POPUP, (UINT_PTR)add, L"Add to Playlist");
        AppendMenuW(m, MF_STRING, CMD_SHOW_IN_EXPLORER, L"Show in File Explorer");
        AppendMenuW(m, MF_SEPARATOR, 0, nullptr);
        AppendMenuW(m, MF_STRING, CMD_DELETE, g_src == SRC_PLAYLIST ? L"Remove from Playlist" : L"Remove from Library");
    } else if (g_src >= SRC_RADIO_POPULAR && g_src <= SRC_RADIO_SEARCH) {
        AppendMenuW(m, MF_STRING, CMD_PLAY_SELECTION, L"Play");
        bool fav = !rows.empty() && g_rows[rows[0]].kind == 2 && g_online.is_favourite(g_stations[g_rows[rows[0]].index].uuid);
        AppendMenuW(m, MF_STRING, CMD_FAVOURITE, fav ? L"Remove from Favourites" : L"Add to Favourites");
    } else if (g_src == SRC_SHOW) {
        AppendMenuW(m, MF_STRING, CMD_PLAY_SELECTION, L"Play");
        AppendMenuW(m, MF_STRING, CMD_MARK_PLAYED, L"Mark as Played / Unplayed");
        AppendMenuW(m, MF_SEPARATOR, 0, nullptr);
        AppendMenuW(m, MF_STRING, CMD_REFRESH_SHOW, L"Refresh Podcast");
        AppendMenuW(m, MF_STRING, CMD_UNSUBSCRIBE, L"Unsubscribe");
    } else if (g_src == SRC_PODCAST_SEARCH) {
        AppendMenuW(m, MF_STRING, CMD_SUBSCRIBE_SELECTED, L"Subscribe");
    } else {
        DestroyMenu(m);
        return;
    }
    TrackPopupMenu(m, TPM_RIGHTBUTTON, x, y, 0, g_wnd, nullptr);
    DestroyMenu(m);
}

static LRESULT CALLBACK wnd_proc(HWND h, UINT m, WPARAM w, LPARAM l) {
    switch (m) {
        case WM_CREATE: {
            g_wnd = h;
            g_player = new Player(h);
            NONCLIENTMETRICSW ncm = {sizeof ncm};
            SystemParametersInfoW(SPI_GETNONCLIENTMETRICS, sizeof ncm, &ncm, 0);
            ncm.lfMessageFont.lfHeight = -13;
            wcscpy(ncm.lfMessageFont.lfFaceName, L"Segoe UI");
            g_font = CreateFontIndirectW(&ncm.lfMessageFont);
            LOGFONTW lf = ncm.lfMessageFont;
            lf.lfWeight = FW_SEMIBOLD;
            g_font_bold = CreateFontIndirectW(&lf);
            lf.lfWeight = FW_NORMAL;
            lf.lfHeight = -11;
            g_font_small = CreateFontIndirectW(&lf);
            lf.lfHeight = -16;
            wcscpy(lf.lfFaceName, L"Segoe UI Symbol");
            g_font_sym = CreateFontIndirectW(&lf);
            g_prev = make_button(L"⏮", IDC_PREV, L"Previous");
            g_play = make_button(L"▶", IDC_PLAY, L"Play");
            g_next = make_button(L"⏭", IDC_NEXT, L"Next");
            g_volume = CreateWindowExW(0, TRACKBAR_CLASSW, L"", WS_CHILD | WS_VISIBLE | TBS_NOTICKS | TBS_BOTH, 0, 0, 10, 10, h,
                                       (HMENU)IDC_VOLUME, g_inst, nullptr);
            SendMessageW(g_volume, TBM_SETRANGE, TRUE, MAKELPARAM(0, 100));
            WNDCLASSW lc = {};
            lc.lpfnWndProc = lcd_proc;
            lc.hInstance = g_inst;
            lc.hCursor = LoadCursor(nullptr, IDC_ARROW);
            lc.lpszClassName = L"ChordLCD";
            RegisterClassW(&lc);
            g_lcd = CreateWindowExW(0, L"ChordLCD", L"", WS_CHILD | WS_VISIBLE, 0, 0, 10, 10, h, (HMENU)IDC_LCD, g_inst, nullptr);
            g_search = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"", WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL, 0, 0, 10, 10, h,
                                       (HMENU)IDC_SEARCH, g_inst, nullptr);
            SendMessageW(g_search, WM_SETFONT, (WPARAM)g_font, TRUE);
            SendMessageW(g_search, EM_SETCUEBANNER, TRUE, (LPARAM)L"Search");
            g_search_old = (WNDPROC)SetWindowLongPtrW(g_search, GWLP_WNDPROC, (LONG_PTR)search_proc);
            g_sources = CreateWindowExW(0, WC_TREEVIEWW, L"", WS_CHILD | WS_VISIBLE | TVS_SHOWSELALWAYS | TVS_FULLROWSELECT | TVS_NOHSCROLL,
                                        0, 0, 10, 10, h, (HMENU)IDC_SOURCES, g_inst, nullptr);
            SendMessageW(g_sources, WM_SETFONT, (WPARAM)g_font, TRUE);
            TreeView_SetItemHeight(g_sources, 24);
            TreeView_SetIndent(g_sources, 14);
            g_list = CreateWindowExW(0, WC_LISTVIEWW, L"", WS_CHILD | WS_VISIBLE | LVS_REPORT | LVS_OWNERDATA | LVS_SHOWSELALWAYS,
                                     0, 0, 10, 10, h, (HMENU)IDC_LIST, g_inst, nullptr);
            ListView_SetExtendedListViewStyle(g_list, LVS_EX_FULLROWSELECT | LVS_EX_DOUBLEBUFFER | LVS_EX_HEADERDRAGDROP);
            SendMessageW(g_list, WM_SETFONT, (WPARAM)g_font, TRUE);
            g_status = CreateWindowExW(0, STATUSCLASSNAMEW, L"", WS_CHILD | WS_VISIBLE | SBARS_SIZEGRIP, 0, 0, 0, 0, h, (HMENU)IDC_STATUS,
                                       g_inst, nullptr);
            SendMessageW(g_status, WM_SETFONT, (WPARAM)g_font, TRUE);
            DragAcceptFiles(h, TRUE);
            g_dark = windows_dark();
            apply_colours();
            SetTimer(h, 1, 500, nullptr);
            return 0;
        }
        case WM_SIZE: layout(); return 0;
        case WM_DRAWITEM: draw_button((DRAWITEMSTRUCT *)l); return TRUE;
        case WM_GETMINMAXINFO: ((MINMAXINFO *)l)->ptMinTrackSize = {760, 420}; return 0;
        case WM_ERASEBKGND: {
            RECT rc;
            GetClientRect(h, &rc);
            rc.bottom = TOPBAR;
            TRIVERTEX v[2] = {{0, 0, 0, 0, 0, 0}, {rc.right, TOPBAR, 0, 0, 0, 0}};
            COLORREF a = g_dark ? RGB(0x4a, 0x4a, 0x4a) : RGB(0xe4, 0xe4, 0xe4), b = g_dark ? RGB(0x2e, 0x2e, 0x2e) : RGB(0xb9, 0xb9, 0xb9);
            v[0].Red = GetRValue(a) << 8; v[0].Green = GetGValue(a) << 8; v[0].Blue = GetBValue(a) << 8;
            v[1].Red = GetRValue(b) << 8; v[1].Green = GetGValue(b) << 8; v[1].Blue = GetBValue(b) << 8;
            GRADIENT_RECT gr = {0, 1};
            GradientFill((HDC)w, v, 2, &gr, 1, GRADIENT_FILL_RECT_V);
            return 1;
        }
        case WM_CTLCOLORSTATIC: {
            SetBkColor((HDC)w, C_BG());
            static HBRUSH br;
            if (br) DeleteObject(br);
            br = CreateSolidBrush(C_BG());
            return (LRESULT)br;
        }
        case WM_CTLCOLOREDIT:
            if ((HWND)l == g_search) {
                static HBRUSH eb;
                if (eb) DeleteObject(eb);
                eb = CreateSolidBrush(g_dark ? RGB(0x1b, 0x1b, 0x1b) : RGB(0xff, 0xff, 0xff));
                SetBkColor((HDC)w, g_dark ? RGB(0x1b, 0x1b, 0x1b) : RGB(0xff, 0xff, 0xff));
                SetTextColor((HDC)w, C_FG());
                return (LRESULT)eb;
            }
            break;
        case WM_SETTINGCHANGE:
            if (l && wcscmp((const wchar_t *)l, L"ImmersiveColorSet") == 0) {
                g_dark = windows_dark();
                apply_colours();
            }
            return 0;
        case WM_TIMER:
            if (w == 1) {
                if (g_has_now) InvalidateRect(g_lcd, nullptr, FALSE);
                static int ticks;
                if (++ticks % 20 == 0) { remember_episode_position(); }
            }
            return 0;
        case WM_HSCROLL:
            if ((HWND)l == g_volume) {
                g_muted = false;
                g_vol = SendMessageW(g_volume, TBM_GETPOS, 0, 0) / 100.0;
                g_player->set_volume(g_vol);
            }
            return 0;
        case WM_COMMAND:
            if (LOWORD(w) == IDC_PLAY) { on_command(CMD_PLAY_PAUSE); SetFocus(g_list); return 0; }
            if (LOWORD(w) == IDC_NEXT) { on_command(CMD_NEXT); SetFocus(g_list); return 0; }
            if (LOWORD(w) == IDC_PREV) { on_command(CMD_PREV); SetFocus(g_list); return 0; }
            if (LOWORD(w) == IDC_SEARCH && HIWORD(w) == EN_CHANGE) {
                // live filtering of what's in the list; Enter searches the directories (radio, podcasts)
                if (g_src != SRC_RADIO_POPULAR && g_src != SRC_RADIO_SEARCH && g_src != SRC_PODCAST_SEARCH) fill_list();
                return 0;
            }
            on_command(LOWORD(w));
            return 0;
        case WM_INITMENUPOPUP:
            if ((HMENU)w == g_add_to_menu) fill_add_to_menu(g_add_to_menu);
            return 0;
        case WM_NOTIFY: {
            NMHDR *n = (NMHDR *)l;
            if (n->hwndFrom == g_list) {
                if (n->code == LVN_GETDISPINFOW) {
                    auto *d = (NMLVDISPINFOW *)l;
                    if ((d->item.mask & LVIF_TEXT) && d->item.iItem < (int)g_rows.size()) {
                        static std::wstring s;
                        s = col_text(g_rows[d->item.iItem], d->item.iSubItem);
                        lstrcpynW(d->item.pszText, s.c_str(), d->item.cchTextMax);
                    }
                    return 0;
                }
                if (n->code == NM_DBLCLK) {
                    auto *a = (NMITEMACTIVATE *)l;
                    if (a->iItem >= 0) play_row(a->iItem);
                    return 0;
                }
                if (n->code == LVN_KEYDOWN) {
                    auto *k = (NMLVKEYDOWN *)l;
                    if (k->wVKey == VK_RETURN) { on_command(CMD_PLAY_SELECTION); return 0; }
                    if (k->wVKey == VK_DELETE) { on_command(CMD_DELETE); return 0; }
                    if (k->wVKey == VK_SPACE) { on_command(CMD_PLAY_PAUSE); return 0; }
                }
                if (n->code == LVN_COLUMNCLICK) {
                    auto *c = (NMLISTVIEW *)l;
                    if (g_sort_col == c->iSubItem) g_sort_desc = !g_sort_desc;
                    else { g_sort_col = c->iSubItem; g_sort_desc = false; }
                    fill_list();
                    return 0;
                }
                if (n->code == NM_CUSTOMDRAW) {
                    auto *cd = (NMLVCUSTOMDRAW *)l;
                    if (cd->nmcd.dwDrawStage == CDDS_PREPAINT) return CDRF_NOTIFYITEMDRAW;
                    if (cd->nmcd.dwDrawStage == CDDS_ITEMPREPAINT) {
                        int i = (int)cd->nmcd.dwItemSpec;
                        bool even = i % 2 == 0;
                        cd->clrTextBk = even ? C_LIST() : (g_dark ? RGB(0x2a, 0x24, 0x29) : RGB(0xf8, 0xf0, 0xf5));
                        cd->clrText = C_FG();
                        if (ListView_GetItemState(g_list, i, LVIS_SELECTED) & LVIS_SELECTED) {
                            // selected rows in Chord's colour, as on Linux
                            cd->nmcd.uItemState &= ~CDIS_SELECTED;
                            cd->clrTextBk = GetFocus() == g_list ? C_ACCENT() : (g_dark ? RGB(0x4e, 0x2a, 0x44) : RGB(0xef, 0xcd, 0xe3));
                            cd->clrText = GetFocus() == g_list ? RGB(255, 255, 255) : C_FG();
                            return CDRF_NEWFONT;
                        }
                        if (g_has_now && i < (int)g_rows.size()) {
                            const Row &r = g_rows[i];
                            bool now = (r.kind == 1 && g_now.kind == 1 && g_lib.tracks[r.index].id == g_now.id) ||
                                       (r.kind == 2 && g_now.kind == 3 && g_stations[r.index].uuid == g_now.key) ||
                                       (r.kind == 4 && g_now.kind == 2 && g_online.episodes[r.index].guid == g_now.key);
                            if (now) { cd->clrText = C_ACCENT(); SelectObject(cd->nmcd.hdc, g_font_bold); return CDRF_NEWFONT; }
                        }
                        return CDRF_DODEFAULT;
                    }
                }
            }
            if (n->hwndFrom == g_sources) {
                if (n->code == NM_CUSTOMDRAW) {
                    auto *cd = (NMTVCUSTOMDRAW *)l;
                    if (cd->nmcd.dwDrawStage == CDDS_PREPAINT) return CDRF_NOTIFYITEMDRAW;
                    if (cd->nmcd.dwDrawStage == CDDS_ITEMPREPAINT) {
                        auto it = g_tree.find((HTREEITEM)cd->nmcd.dwItemSpec);
                        bool header = it != g_tree.end() && it->second.first == SRC_HEADER;
                        if (cd->nmcd.uItemState & CDIS_SELECTED) {
                            cd->nmcd.uItemState &= ~(CDIS_SELECTED | CDIS_FOCUS);
                            cd->clrTextBk = C_ACCENT();
                            cd->clrText = RGB(255, 255, 255);
                        } else if (header) {
                            cd->clrTextBk = C_SRC();
                            cd->clrText = g_dark ? RGB(0xb0, 0x9a, 0xac) : RGB(0x77, 0x68, 0x7a);
                        } else {
                            cd->clrTextBk = C_SRC();
                            cd->clrText = C_FG();
                        }
                        return CDRF_NEWFONT;
                    }
                    return CDRF_DODEFAULT;
                }
                if (n->code == TVN_SELCHANGEDW && !g_filling_sources) {
                    auto *t = (NMTREEVIEWW *)l;
                    auto it = g_tree.find(t->itemNew.hItem);
                    if (it != g_tree.end() && it->second.first != SRC_HEADER) select_source(it->second.first, it->second.second);
                    else if (it != g_tree.end() && it->second.first == SRC_HEADER) fill_sources();
                    return 0;
                }
                if (n->code == TVN_SELCHANGINGW) {
                    auto *t = (NMTREEVIEWW *)l;
                    auto it = g_tree.find(t->itemNew.hItem);
                    if (it != g_tree.end() && it->second.first == SRC_HEADER) return TRUE;   // headers aren't sources
                    return FALSE;
                }
                if (n->code == NM_RCLICK) {
                    POINT p;
                    GetCursorPos(&p);
                    TVHITTESTINFO ht = {};
                    ht.pt = p;
                    ScreenToClient(g_sources, &ht.pt);
                    HTREEITEM hit = TreeView_HitTest(g_sources, &ht);
                    auto it = g_tree.find(hit);
                    if (it != g_tree.end()) {
                        TreeView_SelectItem(g_sources, hit);
                        HMENU mm = CreatePopupMenu();
                        if (it->second.first == SRC_PLAYLIST) {
                            AppendMenuW(mm, MF_STRING, CMD_RENAME_PLAYLIST, L"Rename");
                            AppendMenuW(mm, MF_STRING, CMD_DELETE_PLAYLIST, L"Delete");
                        } else if (it->second.first == SRC_SHOW) {
                            AppendMenuW(mm, MF_STRING, CMD_REFRESH_SHOW, L"Refresh Podcast");
                            AppendMenuW(mm, MF_STRING, CMD_UNSUBSCRIBE, L"Unsubscribe");
                        } else if (it->second.first == SRC_PODCASTS) {
                            AppendMenuW(mm, MF_STRING, CMD_SUBSCRIBE_URL, L"Subscribe to Podcast…");
                            AppendMenuW(mm, MF_STRING, CMD_REFRESH_PODCASTS, L"Refresh All Podcasts");
                        } else if (it->second.first == SRC_MUSIC) {
                            AppendMenuW(mm, MF_STRING, CMD_ADD_FOLDER, L"Add Folder to Library…");
                            AppendMenuW(mm, MF_STRING, CMD_NEW_PLAYLIST, L"New Playlist");
                        }
                        if (GetMenuItemCount(mm)) TrackPopupMenu(mm, TPM_RIGHTBUTTON, p.x, p.y, 0, h, nullptr);
                        DestroyMenu(mm);
                    }
                    return TRUE;
                }
            }
            return 0;
        }
        case WM_CONTEXTMENU:
            if ((HWND)w == g_list) {
                int x = GET_X_LPARAM(l), y = GET_Y_LPARAM(l);
                if (x == -1) { RECT r; GetWindowRect(g_list, &r); x = r.left + 40; y = r.top + 40; }
                context_menu(x, y);
                return 0;
            }
            break;
        case WM_DROPFILES: {
            HDROP d = (HDROP)w;
            UINT n = DragQueryFileW(d, 0xFFFFFFFF, nullptr, 0);
            std::vector<std::wstring> paths;
            for (UINT i = 0; i < n; i++) {
                wchar_t p[MAX_PATH * 4];
                DragQueryFileW(d, i, p, MAX_PATH * 4);
                paths.push_back(p);
            }
            DragFinish(d);
            add_paths(paths, false);
            return 0;
        }
        case WM_CHORD_PLAYER:
            if (w == PE_ENDED) {
                if (g_now.kind == 1) g_lib.played(g_now.id), g_lib.save();
                if (g_now.kind == 2) {
                    for (auto &e : g_online.episodes)
                        if (e.show == g_now.id && e.guid == g_now.key) { e.played = true; e.position = 0; }
                    g_online.save();
                }
                next(false);
            } else if (w == PE_ERROR) {
                flash(L"“" + g_now.title + L"” couldn't be played: " + g_player->last_error, 6000);
                if (g_now.kind == 1 && g_queue.size() > 1) SetTimer(h, 2, 600, [](HWND, UINT, UINT_PTR id, DWORD) { KillTimer(g_wnd, id); next(true); });
            }
            update_controls();
            InvalidateRect(g_list, nullptr, FALSE);
            return 0;
        case WM_CHORD_TASK: {
            auto *fn = (std::function<void()> *)l;
            (*fn)();
            delete fn;
            return 0;
        }
        case WM_CLOSE:
            remember_episode_position();
            g_online.save();
            g_lib.save();
            save_settings();
            DestroyWindow(h);
            return 0;
        case WM_DESTROY:
            delete g_player;
            g_player = nullptr;
            PostQuitMessage(0);
            return 0;
    }
    return DefWindowProcW(h, m, w, l);
}

// ================================================================ Chordamp
#include "chordamp.inc"

// ================================================================ self test (run under Wine by the release script)
#include "selftest.inc"

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE, PWSTR, int show) {
    g_inst = inst;
    CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    INITCOMMONCONTROLSEX icc = {sizeof icc, ICC_LISTVIEW_CLASSES | ICC_TREEVIEW_CLASSES | ICC_BAR_CLASSES | ICC_STANDARD_CLASSES};
    InitCommonControlsEx(&icc);
    int argc = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (argc >= 3 && wcscmp(argv[1], L"--selftest") == 0) { g_selftest = true; return selftest(argv[2], argc > 3 ? argv[3] : L""); }
    g_lib.load();
    g_online.load();
    auto st = load_settings();
    if (st.count(L"volume")) g_vol = _wtof(st[L"volume"].c_str());
    g_shuffle = st.count(L"shuffle") && st[L"shuffle"] == L"1";
    g_repeat = st.count(L"repeat") ? _wtoi(st[L"repeat"].c_str()) : 0;
    ca::load(st);

    WNDCLASSEXW wc = {sizeof wc};
    wc.lpfnWndProc = wnd_proc;
    wc.hInstance = inst;
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    wc.hIcon = LoadIconW(inst, MAKEINTRESOURCEW(IDI_CHORD));
    wc.hIconSm = wc.hIcon;
    wc.lpszClassName = L"FolioChord";
    RegisterClassExW(&wc);
    HWND h = CreateWindowExW(0, L"FolioChord", L"Folio Chord", WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT, 1180, 740,
                             nullptr, build_menu(), inst, nullptr);
    if (st.count(L"window")) {
        auto f = split(st[L"window"], L',');
        if (f.size() >= 5) {
            WINDOWPLACEMENT wp = {sizeof wp};
            wp.rcNormalPosition = {_wtoi(f[0].c_str()), _wtoi(f[1].c_str()), _wtoi(f[2].c_str()), _wtoi(f[3].c_str())};
            wp.showCmd = f[4] == L"1" ? SW_SHOWMAXIMIZED : SW_SHOWNORMAL;
            SetWindowPlacement(h, &wp);
        }
    }
    set_volume(g_vol);
    ca::apply_eq(false);
    g_player->set_balance(ca::S.balance);
    fill_sources();
    update_controls();
    if (ca::S.on) ca::switch_look(true);       // Chordamp was the look last time
    else ShowWindow(h, st.count(L"window") ? SW_SHOW : show);
    // files given on the command line (Open with Folio Chord): added and played
    std::vector<std::wstring> files;
    for (int i = 1; i < argc; i++) files.push_back(argv[i]);
    if (!files.empty()) add_paths(files, true);
    LocalFree(argv);
    HACCEL acc = build_accels();
    MSG msg;
    while (GetMessageW(&msg, nullptr, 0, 0) > 0) {
        if (ca::owns(msg.hwnd)) {               // Chordamp's windows have keys of their own
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
            continue;
        }
        // Space plays and pauses, except while typing in the search box
        if (msg.message == WM_KEYDOWN && msg.wParam == VK_SPACE && msg.hwnd != g_search && GetFocus() != g_search &&
            !(GetKeyState(VK_CONTROL) & 0x8000)) {
            if (msg.hwnd != g_list) { on_command(CMD_PLAY_PAUSE); continue; }
        }
        if (msg.hwnd == g_search || GetFocus() == g_search) {
            // keep Ctrl+A, arrows and Delete for the text being typed
            if (msg.message == WM_KEYDOWN && (msg.wParam == VK_DELETE || ((GetKeyState(VK_CONTROL) & 0x8000) && msg.wParam == 'A'))) {
                TranslateMessage(&msg);
                DispatchMessageW(&msg);
                continue;
            }
        }
        if (!TranslateAcceleratorW(h, acc, &msg)) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    }
    CoUninitialize();
    return 0;
}
