// Chordamp (C3-27..C3-38) for Windows: the classic small-player look. View > Chordamp swaps the Standard
// window for small skinned windows — the player, the equalizer and the playlist editor — that dock and
// snap together, plus a media library window. Drawn from a skin (skin.h): Chordamp's own, or a classic
// .wsz you load. Ctrl+Shift+W, or Standard Look in the options menu, brings the Standard window back.
// Included into main.cpp (it works on the play queue and the library directly).
#include "skin.h"
#include <set>
#include <tuple>

namespace ca {

void add_to_list(const std::vector<std::wstring> &paths, bool play);

const int W = 275, H = 116, SNAP = 10;

// ---------------------------------------------------------------- settings (kept in settings.tsv)
struct Settings {
    bool on = false;                 // the look: Chordamp instead of Standard
    std::wstring skin;               // file name in the Skins folder; "" Chordamp's own
    bool dbl = false, eq = true, pl = true, ontop = false, shade = false, lib = false;
    std::wstring vis = L"spectrum";
    int pl_h = 232;
    std::map<std::wstring, POINT> pos;
    bool eq_on = false, eq_auto = true;
    double preamp = 0, bands[10] = {};
    std::wstring preset = L"Flat";
    double balance = 0;
    std::map<std::wstring, std::vector<double>> custom;      // Make Preset: preamp + 10 bands
} S;

static std::wstring num(double v) {
    wchar_t b[32];
    swprintf(b, 32, L"%.2f", v);
    return b;
}

std::wstring save_lines() {
    std::wstring o;
    auto line = [&](const std::wstring &k, const std::wstring &v) { o += k + L"\t" + tsv_escape(v) + L"\n"; };
    line(L"look", S.on ? L"chordamp" : L"standard");
    line(L"skin", S.skin);
    line(L"ca_double", std::to_wstring(S.dbl));
    line(L"ca_eq", std::to_wstring(S.eq));
    line(L"ca_pl", std::to_wstring(S.pl));
    line(L"ca_ontop", std::to_wstring(S.ontop));
    line(L"ca_shade", std::to_wstring(S.shade));
    line(L"ca_lib", std::to_wstring(S.lib));
    line(L"ca_vis", S.vis);
    line(L"ca_pl_h", std::to_wstring(S.pl_h));
    std::wstring p;
    for (auto &kv : S.pos) p += kv.first + L"=" + std::to_wstring(kv.second.x) + L"," + std::to_wstring(kv.second.y) + L";";
    line(L"ca_pos", p);
    line(L"eq_on", std::to_wstring(S.eq_on));
    line(L"eq_auto", std::to_wstring(S.eq_auto));
    std::wstring b = num(S.preamp);
    for (double v : S.bands) b += L"," + num(v);
    line(L"eq_values", b);
    line(L"eq_preset", S.preset);
    line(L"balance", num(S.balance));
    std::wstring c;
    for (auto &kv : S.custom) {
        c += kv.first;
        for (double v : kv.second) c += L"," + num(v);
        c += L"|";
    }
    line(L"eq_custom", c);
    return o;
}

void load(std::map<std::wstring, std::wstring> &m) {
    auto get = [&](const wchar_t *k) { return m.count(k) ? tsv_unescape(m[k]) : std::wstring(); };
    auto flag = [&](const wchar_t *k, bool &v) { if (m.count(k)) v = get(k) == L"1"; };
    S.on = get(L"look") == L"chordamp";
    S.skin = get(L"skin");
    flag(L"ca_double", S.dbl); flag(L"ca_eq", S.eq); flag(L"ca_pl", S.pl); flag(L"ca_ontop", S.ontop);
    flag(L"ca_shade", S.shade); flag(L"ca_lib", S.lib); flag(L"eq_on", S.eq_on); flag(L"eq_auto", S.eq_auto);
    if (m.count(L"ca_vis")) S.vis = get(L"ca_vis");
    if (m.count(L"ca_pl_h")) S.pl_h = std::max(116, std::min(900, _wtoi(get(L"ca_pl_h").c_str())));
    for (auto &part : split(get(L"ca_pos"), L';')) {
        auto eq = part.find(L'=');
        if (eq == std::wstring::npos) continue;
        auto xy = split(part.substr(eq + 1), L',');
        if (xy.size() == 2) S.pos[part.substr(0, eq)] = {_wtoi(xy[0].c_str()), _wtoi(xy[1].c_str())};
    }
    auto vals = split(get(L"eq_values"), L',');
    if (vals.size() == 11) {
        S.preamp = _wtof(vals[0].c_str());
        for (int i = 0; i < 10; i++) S.bands[i] = _wtof(vals[i + 1].c_str());
    }
    if (m.count(L"eq_preset")) S.preset = get(L"eq_preset");
    if (m.count(L"balance")) S.balance = _wtof(get(L"balance").c_str());
    for (auto &p : split(get(L"eq_custom"), L'|')) {
        auto f = split(p, L',');
        if (f.size() == 12 && !f[0].empty()) {
            std::vector<double> v;
            for (int i = 1; i < 12; i++) v.push_back(_wtof(f[i].c_str()));
            S.custom[f[0]] = v;
        }
    }
}

// ---------------------------------------------------------------- drawing helpers
Skin *g_skin = nullptr;
int scale() { return S.dbl ? 2 : 1; }

struct FontKey {
    std::wstring face;
    int px;
    bool bold;
    bool operator<(const FontKey &o) const { return std::tie(face, px, bold) < std::tie(o.face, o.px, o.bold); }
};
std::map<FontKey, HFONT> g_fonts;
HFONT font(const std::wstring &face, double size, bool bold) {
    FontKey k{face, (int)std::lround(size * scale()), bold};
    auto it = g_fonts.find(k);
    if (it != g_fonts.end()) return it->second;
    HFONT f = CreateFontW(-k.px, 0, 0, 0, bold ? FW_BOLD : FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
                          scale() == 1 ? NONANTIALIASED_QUALITY : ANTIALIASED_QUALITY, DEFAULT_PITCH, face.c_str());
    g_fonts[k] = f;
    return f;
}

// text in skin pixels at (x, y) top-left; returns its width in skin pixels
int plain_text(HDC dc, const std::wstring &s, double x, double y, COLORREF col, double size, bool bold = false,
               const std::wstring &face = L"Segoe UI") {
    HGDIOBJ old = SelectObject(dc, font(face, size, bold));
    SetBkMode(dc, TRANSPARENT);
    SetTextColor(dc, col);
    int sc = scale();
    TextOutW(dc, (int)std::lround(x * sc), (int)std::lround(y * sc), s.c_str(), (int)s.size());
    SIZE sz{};
    GetTextExtentPoint32W(dc, s.c_str(), (int)s.size(), &sz);
    SelectObject(dc, old);
    return (sz.cx + sc - 1) / sc;
}

int text_width(HDC dc, const std::wstring &s, double size, bool bold = false, const std::wstring &face = L"Segoe UI") {
    HGDIOBJ old = SelectObject(dc, font(face, size, bold));
    SIZE sz{};
    GetTextExtentPoint32W(dc, s.c_str(), (int)s.size(), &sz);
    SelectObject(dc, old);
    return (sz.cx + scale() - 1) / scale();
}

// text.bmp: 5x6 letters
std::map<wchar_t, POINT> text_map() {
    static std::map<wchar_t, POINT> m;
    if (!m.empty()) return m;
    const wchar_t *rows[3] = {L"abcdefghijklmnopqrstuvwxyz\"@   ", L"0123456789….:()-'!_+\\/[]^&%,=$#", L"ÅÖÄ?*"};
    for (int r = 0; r < 3; r++)
        for (int c = 0; rows[r][c]; c++)
            if (rows[r][c] != L' ' || (r == 0 && c == 30)) m.emplace(rows[r][c], POINT{c * 5, r * 6});
    return m;
}

int bitmap_text(HDC dc, const std::wstring &s, int x, int y, int maxw = -1) {
    auto m = text_map();
    int cx = x;
    for (wchar_t ch : s) {
        if (maxw >= 0 && cx - x >= maxw) break;
        wchar_t c = (wchar_t)towlower(ch);
        auto it = m.find(c);
        POINT p = it != m.end() ? it->second : m[L' '];
        g_skin->blit(dc, L"text", p.x, p.y, 5, 6, cx, y, scale());
        cx += 5;
    }
    return cx - x;
}

void fill(HDC dc, int x, int y, int w, int h, COLORREF c) {
    int s = scale();
    RECT r{x * s, y * s, (x + w) * s, (y + h) * s};
    HBRUSH b = CreateSolidBrush(c);
    FillRect(dc, &r, b);
    DeleteObject(b);
}

void clip(HDC dc, int x, int y, int w, int h) {
    int s = scale();
    IntersectClipRect(dc, x * s, y * s, (x + w) * s, (y + h) * s);
}

bool blit(HDC dc, const wchar_t *sheet, int sx, int sy, int w, int h, int dx, int dy) {
    return g_skin->blit(dc, sheet, sx, sy, w, h, dx, dy, scale());
}

// ---------------------------------------------------------------- what's playing
std::wstring item_name(const QItem &q) {
    if (q.kind == 1) {
        Track *t = g_lib.find(q.id);
        if (t) return t->artist.empty() ? t->title : t->artist + L" - " + t->title;
    }
    return q.artist.empty() ? q.title : q.artist + L" - " + q.title;
}

int current_index() {             // the playing entry's place in the list (not a station)
    if (!g_has_now || g_now.kind == 3 || g_pos < 0 || g_pos >= (int)g_order.size()) return -1;
    return g_order[g_pos];
}

std::wstring title_text() {
    if (!g_has_now) return L"Chordamp";
    if (g_now.kind == 3) return g_now.title;
    int i = current_index();
    double dur = g_now.duration > 0 ? g_now.duration : g_player->duration();
    return (i >= 0 ? std::to_wstring(i + 1) + L". " : L"") + item_name(g_now) + L" (" + fmt_time(dur) + L")";
}

struct Info { std::wstring kbps, khz; int channels; int rate; };
Info stream_info() {
    Info in{L"", L"", 0, 44100};
    if (!g_has_now) return in;
    int rate = g_player->processing() ? g_player->sample_rate() : 44100;
    int ch = g_player->processing() ? g_player->channels() : 2;
    if (g_now.kind == 1) {
        Track *t = g_lib.find(g_now.id);
        if (t && t->bitrate) { wchar_t b[8]; swprintf(b, 8, L"%3d", std::min(999, t->bitrate)); in.kbps = b; }
    }
    in.khz = std::to_wstring((int)std::lround(rate / 1000.0));
    in.channels = ch;
    in.rate = rate;
    return in;
}

int engine_state() { return g_player->playing() ? 1 : (g_player->paused() ? 2 : 0); }

// ---------------------------------------------------------------- the parts
struct Part;
Part *g_main_part = nullptr, *g_eq_part = nullptr, *g_pl_part = nullptr;
HWND g_lib_wnd = nullptr;
bool g_visible = false;

void apply_eq(bool save = true);
void options_menu(Part *p, int x, int y);
void presets_menu(Part *p);
void pl_menu(const std::wstring &which, Part *p);
void row_menu(int x, int y);
void toggle_window(const std::wstring &name, int on = -1);
void toggle_shade();
void transport(const std::wstring &name);
void set_vis(const std::wstring &v);
void play_file();
void key(WPARAM vk, bool ctrl, bool alt, bool shift, Part *from);
void begin_move(Part *p);
void move_motion(Part *p);
void end_move(Part *p);
void show_library(int on);
void save_positions();
void switch_look(bool chordamp);
bool pl_active();

struct Region { std::wstring name; int x, y, w, h; };
struct Sz { int cx, cy; };

struct Part {
    std::wstring name;
    HWND hwnd = nullptr;
    std::wstring pressed;            // the region held down
    std::wstring slider;             // a slider being dragged
    std::wstring cur_cursor;
    virtual ~Part() {}
    virtual Sz size() { return {W, H}; }
    virtual void paint(HDC dc) = 0;
    virtual std::vector<Region> regions() { return {}; }
    virtual bool title_hit(int x, int y) { (void)x; return y < 14; }
    virtual bool drag_anywhere(int x, int y) { (void)x; (void)y; return false; }
    virtual bool is_slider(const std::wstring &n) { (void)n; return false; }
    virtual void slide(const std::wstring &n, int x, int y) { (void)n; (void)x; (void)y; }
    virtual void slide_done(const std::wstring &n, int x, int y) { (void)n; (void)x; (void)y; }
    virtual void click(const std::wstring &n) { (void)n; }
    virtual void dbl(int x, int y) { (void)x; (void)y; }
    virtual std::wstring shape_key() { return L""; }
    virtual std::wstring cursor_name(int x, int y) { (void)x; (void)y; return L"normal"; }
    virtual bool press(int x, int y, bool dblclick, bool ctrl, bool shift) { (void)x; (void)y; (void)dblclick; (void)ctrl; (void)shift; return false; }
    virtual bool motion(int x, int y) { (void)x; (void)y; return false; }
    virtual bool release() { return false; }
    virtual void scrolled(int d, int x, int y) {
        (void)x; (void)y;
        set_volume(g_vol + d * 0.04);
        update_controls();
    }
    std::wstring hit(int x, int y) {
        for (auto &r : regions())
            if (r.x <= x && x < r.x + r.w && r.y <= y && y < r.y + r.h) return r.name;
        return L"";
    }
    bool focused() {
        HWND fg = GetForegroundWindow();
        return fg == hwnd;
    }
    RECT rect() {
        RECT r{};
        GetWindowRect(hwnd, &r);
        return r;
    }
    void redraw() { if (hwnd) InvalidateRect(hwnd, nullptr, FALSE); }
    void resize_to() {
        Sz s = size();
        SetWindowPos(hwnd, nullptr, 0, 0, s.cx * scale(), s.cy * scale(), SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE);
        apply_shape();
        redraw();
    }
    void apply_shape() {
        auto it = g_skin->regions.find(shape_key());
        if (shape_key().empty() || it == g_skin->regions.end()) { SetWindowRgn(hwnd, nullptr, TRUE); return; }
        std::vector<POINT> pts;
        std::vector<INT> counts;
        for (auto &poly : it->second) {
            for (auto p : poly) pts.push_back({p.x * scale(), p.y * scale()});
            counts.push_back((INT)poly.size());
        }
        HRGN r = CreatePolyPolygonRgn(pts.data(), counts.data(), (int)counts.size(), WINDING);
        SetWindowRgn(hwnd, r, TRUE);          // the window owns the region now
    }
};

// ======================================================================== the player window
struct MainPart : Part {
    int marquee = 0;
    std::wstring marquee_text;
    double peaks[19] = {}, bars[19] = {};
    bool show_left = false;
    double seek_to = -1;
    std::vector<short> wave;

    MainPart() { name = L"main"; }
    Sz size() override { return S.shade ? Sz{W, 14} : Sz{W, H}; }
    bool title_hit(int x, int y) override { return y < 14 && !(x >= 244 || x < 16); }
    std::wstring shape_key() override { return S.shade ? L"windowshade" : L"normal"; }
    bool drag_anywhere(int x, int y) override { (void)x; return !S.shade && y < 116; }
    std::wstring cursor_name(int x, int y) override {
        std::wstring n = hit(x, y), ws = S.shade ? L"ws" : L"";
        if (n == L"close") return ws + L"close";
        if (n == L"min") return ws + L"min";
        if (n == L"menu") return L"mainmenu";
        if (n == L"shade") return ws + L"winbut";
        if (n == L"pos") return L"posbar";
        if (n == L"volume" || n == L"balance") return L"volbal";
        if (S.shade) return L"wsnormal";
        if (111 <= x && x < 265 && 24 <= y && y < 36) return L"songname";
        if (y < 14) return L"titlebar";
        return L"normal";
    }
    std::vector<Region> regions() override {
        std::vector<Region> r = {{L"menu", 6, 3, 9, 9}, {L"min", 244, 3, 9, 9}, {L"shade", 254, 3, 9, 9}, {L"close", 264, 3, 9, 9}};
        if (S.shade) {
            for (auto x : std::vector<Region>{{L"prev", 169, 2, 7, 10}, {L"play", 177, 2, 9, 10}, {L"pause", 187, 2, 9, 10},
                                              {L"stop", 196, 2, 9, 10}, {L"next", 205, 2, 9, 10}, {L"eject", 215, 2, 9, 10}})
                r.push_back(x);
            return r;
        }
        for (auto x : std::vector<Region>{
                 {L"prev", 16, 88, 23, 18}, {L"play", 39, 88, 23, 18}, {L"pause", 62, 88, 23, 18}, {L"stop", 85, 88, 23, 18},
                 {L"next", 108, 88, 22, 18}, {L"eject", 136, 89, 22, 16}, {L"shuffle", 164, 89, 47, 15}, {L"repeat", 210, 89, 28, 15},
                 {L"eqbtn", 219, 58, 23, 12}, {L"plbtn", 242, 58, 23, 12}, {L"pos", 16, 72, 248, 10}, {L"volume", 107, 57, 68, 13},
                 {L"balance", 177, 57, 38, 13}, {L"time", 36, 26, 63, 13}, {L"vis", 24, 43, 76, 16}, {L"about", 253, 91, 13, 15}})
            r.push_back(x);
        return r;
    }
    bool is_slider(const std::wstring &n) override { return n == L"pos" || n == L"volume" || n == L"balance"; }
    void slide(const std::wstring &n, int x, int y) override {
        (void)y;
        if (n == L"volume") { set_volume((x - 107 - 7) / 54.0); update_controls(); }
        else if (n == L"balance") {
            double b = std::max(-1.0, std::min(1.0, (x - 177 - 7 - 12) / 12.0));
            if (std::fabs(b) < 0.15) b = 0;
            S.balance = b;
            g_player->set_balance(b);
        } else if (n == L"pos") {
            double dur = g_player->duration();
            if (dur > 0) seek_to = std::max(0.0, std::min(1.0, (x - 16 - 14) / 219.0)) * dur;
        }
        redraw();
    }
    void slide_done(const std::wstring &n, int x, int y) override {
        (void)x; (void)y;
        if (n == L"pos" && seek_to >= 0) { g_player->seek(seek_to); seek_to = -1; }
        save_settings();
    }
    void click(const std::wstring &n) override;
    void dbl(int x, int y) override { (void)x; if (y < 14) toggle_shade(); }

    void title_buttons(HDC dc, bool shade) {
        blit(dc, L"titlebar", 0, pressed == L"menu" ? 9 : 0, 9, 9, 6, 3);
        blit(dc, L"titlebar", 9, pressed == L"min" ? 9 : 0, 9, 9, 244, 3);
        if (shade) blit(dc, L"titlebar", 0, pressed == L"shade" ? 27 : 18, 9, 9, 254, 3);
        else blit(dc, L"titlebar", pressed != L"shade" ? 0 : 9, 18, 9, 9, 254, 3);
        blit(dc, L"titlebar", 18, pressed == L"close" ? 9 : 0, 9, 9, 264, 3);
    }
    void small(HDC dc, const std::wstring &s, int x, int y, int w) {
        if (s.empty()) return;
        if (g_skin->text_bitmap) { bitmap_text(dc, s, x, y, w); return; }
        int sv = SaveDC(dc);
        clip(dc, x - 1, y - 3, w + 6, 12);
        plain_text(dc, s, x - 1, y - 3, g_skin->lcd, 8);
        RestoreDC(dc, sv);
    }
    void title_text_draw(HDC dc) {
        std::wstring text = title_text();
        if (text != marquee_text) { marquee_text = text; marquee = 0; }
        if (text.empty()) return;
        int sv = SaveDC(dc);
        if (g_skin->text_bitmap) {
            clip(dc, 111, 27, 154, 6);
            std::wstring full = text + L"  ***  ";
            int tw = (int)full.size() * 5;
            if ((int)text.size() * 5 <= 154) bitmap_text(dc, text, 111, 27);
            else bitmap_text(dc, full + full, 111 - marquee % tw, 27);
        } else {
            clip(dc, 111, 24, 154, 12);
            int tw0 = text_width(dc, text, 8.5);
            if (tw0 <= 152) plain_text(dc, text, 112, 24, g_skin->lcd, 8.5);
            else {
                std::wstring full = text + L"   ***   ";
                int tw = std::max(1, text_width(dc, full, 8.5));
                plain_text(dc, full + full, 112 - marquee % tw, 24, g_skin->lcd, 8.5);
            }
        }
        RestoreDC(dc, sv);
    }
    void tick() {
        // a song whose tags didn't give its length: take it from the player once it plays
        if (g_has_now && g_now.kind == 1 && g_now.duration <= 0 && g_player->duration() > 0) {
            g_now.duration = g_player->duration();
            int ci = current_index();
            if (ci >= 0 && g_queue[ci].id == g_now.id) g_queue[ci].duration = g_now.duration;
            if (Track *t = g_lib.find(g_now.id)) if (t->duration <= 0) t->duration = g_now.duration;
            if (g_pl_part) g_pl_part->redraw();
        }
        marquee += g_skin->text_bitmap ? 5 : 2;
        for (int i = 0; i < 19; i++) {
            bars[i] = std::max(0.0, bars[i] - 1.2);
            if (bars[i] > peaks[i]) peaks[i] = bars[i];
            else peaks[i] = std::max(0.0, peaks[i] - 0.35);
        }
        if (S.vis == L"spectrum") {
            std::vector<float> mags;
            if (g_player->spectrum(mags)) feed(mags);
        } else if (S.vis == L"oscilloscope") {
            if (!g_player->scope(wave)) wave.clear();
        }
    }
    void feed(const std::vector<float> &mags) {
        int n = (int)mags.size();
        if (!n) return;
        double rate = stream_info().rate / 2.0;
        double edges[20];
        for (int i = 0; i < 20; i++) edges[i] = 40 * std::pow(16000 / 40.0, i / 19.0);
        for (int i = 0; i < 19; i++) {
            int a = std::min(n - 1, (int)(edges[i] / rate * n));
            int b = std::min(n, std::max(a + 1, (int)(edges[i + 1] / rate * n)));
            float v = -70;
            for (int k = a; k < b; k++) v = std::max(v, mags[k]);
            double h = std::max(0.0, std::min(16.0, (v + 70) / 52.0 * 16));
            if (h > bars[i]) bars[i] = h;
        }
    }
    void vis(HDC dc) {
        int sv = SaveDC(dc);
        clip(dc, 24, 43, 76, 16);
        fill(dc, 24, 43, 76, 16, g_skin->vis[0]);
        for (int y = 43; y < 59; y += 2)
            for (int x = 24; x < 100; x += 2) fill(dc, x, y + 1, 1, 1, g_skin->vis[1]);
        bool playing = engine_state() == 1;
        if (S.vis == L"spectrum" && playing) {
            for (int i = 0; i < 19; i++) {
                int h = (int)bars[i], x = 24 + i * 4;
                for (int yy = 0; yy < h; yy++) {
                    int row = 15 - yy;
                    fill(dc, x, 43 + row, 3, 1, g_skin->vis[2 + std::min(15, row)]);
                }
                int p = (int)peaks[i];
                if (p > 0) fill(dc, x, 43 + 15 - p, 3, 1, g_skin->vis[23]);
            }
        } else if (S.vis == L"oscilloscope" && playing && !wave.empty()) {
            int n = (int)wave.size(), step = std::max(1, n / 152), start = std::max(0, n - 76 * step), prev = -1;
            for (int x = 0; x < 76; x++) {
                double v = wave[std::min(n - 1, start + x * step)] / 32768.0;
                int y = (int)std::max(0.0, std::min(15.0, std::round(7.5 - v * 7.5 * 1.6)));
                COLORREF col = g_skin->vis[18 + std::min(4, std::abs(y - 8) / 2)];
                if (prev >= 0 && std::abs(prev - y) > 1) {
                    int lo = std::min(prev, y), hi = std::max(prev, y);
                    fill(dc, 24 + x, 43 + lo, 1, hi - lo + 1, col);
                } else fill(dc, 24 + x, 43 + y, 1, 1, col);
                prev = y;
            }
        }
        RestoreDC(dc, sv);
    }
    void paint(HDC dc) override {
        bool foc = focused();
        int st = engine_state();
        if (S.shade) {
            if (!blit(dc, L"titlebar", 27, foc ? 29 : 42, W, 14, 0, 0)) fill(dc, 0, 0, W, 14, RGB(51, 51, 61));
            title_buttons(dc, true);
            double pos = g_player->position(), dur = g_player->duration();
            if (st != 0) {
                plain_text(dc, fmt_time(pos), 127, 1.5, g_skin->text_bitmap ? g_skin->pl_normal : g_skin->lcd, 8);
                if (dur > 0) fill(dc, 226, 5, std::max(1, (int)(17 * pos / dur)), 3, g_skin->pl_normal);
            }
            return;
        }
        if (!blit(dc, L"main", 0, 0, W, H, 0, 0)) fill(dc, 0, 0, W, H, RGB(38, 38, 46));
        blit(dc, L"titlebar", 27, foc ? 0 : 15, W, 14, 0, 0);
        title_buttons(dc, false);
        blit(dc, L"playpaus", st == 1 ? 0 : (st == 2 ? 9 : 18), 0, 9, 9, 26, 28);
        double pos = g_player->position(), dur = g_player->duration();
        if (seek_to >= 0) pos = seek_to;
        if (st != 0 && !(st == 2 && (GetTickCount() / 500) % 2)) {
            double t = std::max(0.0, (show_left && dur > 0) ? dur - pos : pos);
            int mm = (int)(t / 60) % 100, ss = (int)t % 60;
            int xs[4] = {48, 60, 78, 90}, ds[4] = {mm / 10, mm % 10, ss / 10, ss % 10};
            for (int i = 0; i < 4; i++) blit(dc, L"numbers", ds[i] * 9, 0, 9, 13, xs[i], 26);
            if (show_left && dur > 0) fill(dc, 38, 32, 6, 1, g_skin->text_bitmap ? g_skin->pl_normal : g_skin->lcd);
        }
        vis(dc);
        title_text_draw(dc);
        Info in = stream_info();
        small(dc, in.kbps, 111, 43, 15);
        small(dc, in.khz, 156, 43, 10);
        if (in.channels == 1) {
            blit(dc, L"monoster", 29, 0, 27, 12, 212, 41);
            blit(dc, L"monoster", 0, 12, 29, 12, 239, 41);
        } else if (in.channels >= 2) {
            blit(dc, L"monoster", 29, 12, 27, 12, 212, 41);
            blit(dc, L"monoster", 0, 0, 29, 12, 239, 41);
        } else {
            blit(dc, L"monoster", 29, 12, 27, 12, 212, 41);
            blit(dc, L"monoster", 0, 12, 29, 12, 239, 41);
        }
        double v = g_vol;
        blit(dc, L"volume", 0, (int)std::lround(v * 27) * 15, 68, 13, 107, 57);
        blit(dc, L"volume", pressed == L"volume" ? 0 : 15, 422, 14, 11, 107 + (int)std::lround(v * 54), 58);
        double b = S.balance;
        blit(dc, L"balance", 9, (int)std::lround(std::fabs(b) * 27) * 15, 38, 13, 177, 57);
        blit(dc, L"balance", pressed == L"balance" ? 0 : 15, 422, 14, 11, 177 + 12 + (int)std::lround(b * 12), 58);
        blit(dc, L"shufrep", 0 + (pressed == L"eqbtn" ? 46 : 0), S.eq ? 73 : 61, 23, 12, 219, 58);
        blit(dc, L"shufrep", 23 + (pressed == L"plbtn" ? 46 : 0), S.pl ? 73 : 61, 23, 12, 242, 58);
        if (dur > 0 && st != 0) {
            blit(dc, L"posbar", 0, 0, 248, 10, 16, 72);
            blit(dc, L"posbar", pressed == L"pos" ? 278 : 248, 0, 29, 10, 16 + (int)(219 * std::min(1.0, pos / dur)), 72);
        }
        const wchar_t *names[5] = {L"prev", L"play", L"pause", L"stop", L"next"};
        int sxs[5] = {0, 23, 46, 69, 92}, xs2[5] = {16, 39, 62, 85, 108}, ws[5] = {23, 23, 23, 23, 22};
        for (int i = 0; i < 5; i++) blit(dc, L"cbuttons", sxs[i], pressed == names[i] ? 18 : 0, ws[i], 18, xs2[i], 88);
        blit(dc, L"cbuttons", 114, pressed == L"eject" ? 16 : 0, 22, 16, 136, 89);
        blit(dc, L"shufrep", 28, (g_shuffle ? 30 : 0) + (pressed == L"shuffle" ? 15 : 0), 47, 15, 164, 89);
        blit(dc, L"shufrep", 0, (g_repeat ? 30 : 0) + (pressed == L"repeat" ? 15 : 0), 28, 15, 210, 89);
    }
};

void MainPart::click(const std::wstring &n) {
    if (n == L"menu") {
        RECT r = rect();
        options_menu(this, r.left + 6 * scale(), r.top + 12 * scale());
    } else if (n == L"min") {
        ShowWindow(hwnd, SW_MINIMIZE);
    } else if (n == L"shade") toggle_shade();
    else if (n == L"close") PostMessageW(g_wnd, WM_CLOSE, 0, 0);
    else if (n == L"eject") play_file();
    else if (n == L"shuffle") on_command(CMD_SHUFFLE);
    else if (n == L"repeat") on_command(g_repeat ? CMD_REPEAT_OFF : CMD_REPEAT_ALL);
    else if (n == L"eqbtn") toggle_window(L"eq");
    else if (n == L"plbtn") toggle_window(L"pl");
    else if (n == L"time") show_left = !show_left;
    else if (n == L"vis") {
        const wchar_t *order[3] = {L"spectrum", L"oscilloscope", L"off"};
        int i = 0;
        for (int k = 0; k < 3; k++) if (S.vis == order[k]) i = k;
        set_vis(order[(i + 1) % 3]);
    } else if (n == L"about") on_command(CMD_ABOUT);
    else transport(n);
    redraw();
}

// ======================================================================== the equalizer
struct EqPart : Part {
    EqPart() { name = L"eq"; }
    std::wstring shape_key() override { return L"equalizer"; }
    bool drag_anywhere(int, int) override { return true; }
    std::wstring cursor_name(int x, int y) override {
        std::wstring n = hit(x, y);
        if (n == L"close") return L"eqclose";
        if (!n.empty() && is_slider(n)) return L"eqslid";
        if (y < 14) return L"eqtitle";
        return L"eqnormal";
    }
    std::vector<Region> regions() override {
        std::vector<Region> r = {{L"close", 264, 3, 9, 9}, {L"on", 14, 18, 26, 12}, {L"auto", 40, 18, 32, 12},
                                 {L"presets", 217, 18, 44, 12}, {L"preamp", 21, 38, 14, 63}};
        for (int i = 0; i < 10; i++) r.push_back({L"band" + std::to_wstring(i), 78 + i * 18, 38, 14, 63});
        return r;
    }
    bool is_slider(const std::wstring &n) override { return n == L"preamp" || n.compare(0, 4, L"band") == 0; }
    void slide(const std::wstring &n, int x, int y) override {
        (void)x;
        double v = std::max(-12.0, std::min(12.0, (38 + 25 - y) / 25.0 * 12.0));
        if (std::fabs(v) < 0.6) v = 0;
        v = std::round(v * 10) / 10;
        if (n == L"preamp") S.preamp = v;
        else S.bands[_wtoi(n.c_str() + 4)] = v;
        S.preset = L"Manual";
        apply_eq(false);
        redraw();
    }
    void slide_done(const std::wstring &, int, int) override { apply_eq(); }
    void click(const std::wstring &n) override {
        if (n == L"close") toggle_window(L"eq");
        else if (n == L"on") { S.eq_on = !S.eq_on; apply_eq(); }
        else if (n == L"auto") { S.eq_auto = !S.eq_auto; apply_eq(); }
        else if (n == L"presets") presets_menu(this);
        redraw();
    }
    void dbl(int x, int y) override {
        std::wstring n = hit(x, y);
        if (!n.empty() && is_slider(n)) { slide(n, x, 38 + 25); apply_eq(); }
    }
    void paint(HDC dc) override {
        if (!blit(dc, L"eqmain", 0, 0, W, H, 0, 0)) fill(dc, 0, 0, W, H, RGB(38, 38, 46));
        blit(dc, L"eqmain", 0, focused() ? 134 : 149, W, 14, 0, 0);
        blit(dc, L"titlebar", 18, pressed == L"close" ? 9 : 0, 9, 9, 264, 3);
        blit(dc, L"eqmain", (S.eq_on ? 69 : 10) + (pressed == L"on" ? 118 : 0), 119, 26, 12, 14, 18);
        blit(dc, L"eqmain", (S.eq_auto ? 95 : 36) + (pressed == L"auto" ? 118 : 0), 119, 32, 12, 40, 18);
        blit(dc, L"eqmain", 224, pressed == L"presets" ? 176 : 164, 44, 12, 217, 18);
        for (int i = 0; i < 11; i++) {
            double v = i == 0 ? S.preamp : S.bands[i - 1];
            int x = i == 0 ? 21 : 78 + (i - 1) * 18;
            int n = std::max(0, std::min(27, (int)std::lround((v + 12) / 24.0 * 27)));
            blit(dc, L"eqmain", 13 + (n % 14) * 15, 164 + (n / 14) * 65, 14, 63, x, 38);
            int ty = 38 + (int)std::lround((12 - v) / 24.0 * 51);
            std::wstring nm = i == 0 ? L"preamp" : L"band" + std::to_wstring(i - 1);
            blit(dc, L"eqmain", 0, pressed == nm ? 176 : 164, 11, 11, x + 1, ty);
        }
        // the curve
        blit(dc, L"eqmain", 0, 294, 113, 19, 86, 17);
        int sv = SaveDC(dc);
        clip(dc, 86, 17, 113, 19);
        int s = scale();
        std::vector<POINT> pts;
        double px[10], py[10];
        for (int i = 0; i < 10; i++) { px[i] = 86 + 2 + i * 12; py[i] = 17 + 9 - S.bands[i] / 12.0 * 8; }
        pts.push_back({(LONG)std::lround(px[0] * s), (LONG)std::lround(py[0] * s)});
        for (int i = 1; i < 10; i++)
            for (int k = 1; k <= 8; k++) {
                double t = k / 8.0, u = 1 - t;
                double x = u * u * u * px[i - 1] + 3 * u * u * t * (px[i - 1] + 6) + 3 * u * t * t * (px[i] - 6) + t * t * t * px[i];
                double y = u * u * u * py[i - 1] + 3 * u * u * t * py[i - 1] + 3 * u * t * t * py[i] + t * t * t * py[i];
                pts.push_back({(LONG)std::lround(x * s), (LONG)std::lround(y * s)});
            }
        HPEN pen = CreatePen(PS_SOLID, s, S.eq_on ? g_skin->vis[2] : g_skin->vis[4]);
        HGDIOBJ op = SelectObject(dc, pen);
        Polyline(dc, pts.data(), (int)pts.size());
        SelectObject(dc, op);
        DeleteObject(pen);
        RestoreDC(dc, sv);
    }
};

// ======================================================================== the playlist editor
struct PlPart : Part {
    static const int ROW = 14;
    int top = 0, anchor = -1, focus_row = 0;
    std::set<int> sel;
    int drag_row = -1;

    PlPart() { name = L"pl"; }
    Sz size() override { return {W, S.pl_h}; }
    int visible_rows() { return std::max(1, (size().cy - 20 - 38 - 4) / ROW); }
    bool title_hit(int, int y) override { return y < 20; }
    std::vector<Region> regions() override {
        int w = size().cx, h = size().cy;
        return {{L"close", w - 11, 3, 9, 9}, {L"add", 14, h - 30, 22, 18}, {L"rem", 43, h - 30, 22, 18},
                {L"sel", 72, h - 30, 22, 18}, {L"misc", 101, h - 30, 22, 18}, {L"list", w - 44, h - 30, 22, 18},
                {L"grip", w - 20, h - 20, 20, 20}, {L"scroll", w - 15, 20, 8, h - 58}, {L"rows", 12, 20, w - 32, h - 58}};
    }
    bool is_slider(const std::wstring &n) override { return n == L"grip" || n == L"scroll"; }
    std::wstring cursor_name(int x, int y) override {
        std::wstring n = hit(x, y);
        if (n == L"close") return L"pclose";
        if (n == L"grip") return L"psize";
        if (n == L"scroll") return L"pvscroll";
        if (n == L"add" || n == L"rem" || n == L"sel" || n == L"misc" || n == L"list") return L"pwinbut";
        return y < 20 ? L"ptbar" : L"pnormal";
    }
    void slide(const std::wstring &n, int x, int y) override {
        (void)x;
        if (n == L"grip") {
            int h = std::max(116, std::min(900, (int)std::lround((y + 10) / 29.0) * 29));
            if (h != S.pl_h) { S.pl_h = h; resize_to(); }
        } else if (n == L"scroll") {
            int nr = (int)g_queue.size(), span = size().cy - 58 - 18;
            double f = std::max(0.0, std::min(1.0, (y - 20 - 9) / (double)std::max(1, span)));
            top = (int)std::lround(f * std::max(0, nr - visible_rows()));
        }
        redraw();
    }
    void slide_done(const std::wstring &, int, int) override { save_settings(); }
    bool press(int x, int y, bool dblclick, bool ctrl, bool shift) override {
        if (hit(x, y) != L"rows") return false;
        int i = top + (y - 22) / ROW;
        int n = (int)g_queue.size();
        if (dblclick) {
            if (0 <= i && i < n) play_index(i);
            return true;
        }
        if (0 <= i && i < n) {
            if (shift && anchor >= 0) {
                sel.clear();
                for (int k = std::min(anchor, i); k <= std::max(anchor, i); k++) sel.insert(k);
            } else if (ctrl) {
                if (sel.count(i)) sel.erase(i); else sel.insert(i);
                anchor = i;
            } else {
                if (!sel.count(i)) sel = {i};
                anchor = i;
                drag_row = i;
            }
            focus_row = i;
        } else sel.clear();
        redraw();
        return true;
    }
    bool motion(int x, int y) override {
        (void)x;
        if (drag_row < 0) return false;
        int n = (int)g_queue.size();
        int i = std::max(0, std::min(n - 1, top + (y - 22) / ROW));
        int d = i - drag_row;
        if (d && !sel.empty() && move_rows(d)) drag_row += d;
        return true;
    }
    bool release() override {
        if (drag_row < 0) return false;
        drag_row = -1;
        return true;
    }
    void scrolled(int d, int, int) override {
        top = std::max(0, std::min(std::max(0, (int)g_queue.size() - visible_rows()), top - d * 3));
        redraw();
    }
    void click(const std::wstring &n) override {
        if (n == L"close") toggle_window(L"pl");
        else if (n == L"add" || n == L"rem" || n == L"sel" || n == L"misc" || n == L"list") pl_menu(n, this);
    }
    void show_row(int i) {
        int vr = visible_rows();
        if (i < top) top = i;
        else if (i >= top + vr) top = i - vr + 1;
    }
    void play_index(int i) {
        if (i < 0 || i >= (int)g_queue.size()) return;
        make_order(i);
        g_pos = (int)(std::find(g_order.begin(), g_order.end(), i) - g_order.begin());
        start(g_queue[i]);
        redraw();
    }
    bool move_rows(int d) {
        std::vector<int> rows(sel.begin(), sel.end());
        int n = (int)g_queue.size();
        if (rows.empty() || rows.front() + d < 0 || rows.back() + d >= n) return false;
        int cur = current_index();
        std::vector<int> mark(n);
        for (int k = 0; k < n; k++) mark[k] = k;
        std::vector<int> moving, rest;
        for (int k : rows) moving.push_back(k);
        for (int k = 0; k < n; k++) if (!sel.count(k)) rest.push_back(k);
        int ins = rows.front() + d;
        std::vector<int> neu(rest.begin(), rest.begin() + ins);
        neu.insert(neu.end(), moving.begin(), moving.end());
        neu.insert(neu.end(), rest.begin() + ins, rest.end());
        set_order(neu, cur);
        sel.clear();
        for (int m : moving) sel.insert((int)(std::find(neu.begin(), neu.end(), m) - neu.begin()));
        focus_row = anchor = *sel.begin();
        show_row(focus_row);
        redraw();
        return true;
    }
    // the list in a new order (indexes into the old one); the song playing keeps playing
    static void set_order(const std::vector<int> &neu, int cur) {
        std::vector<QItem> q;
        for (int k : neu) q.push_back(g_queue[k]);
        g_queue = q;
        int now = -1;
        for (int k = 0; k < (int)neu.size(); k++) if (neu[k] == cur) now = k;
        make_order(now >= 0 ? now : 0);
        g_pos = now >= 0 ? (int)(std::find(g_order.begin(), g_order.end(), now) - g_order.begin()) : -1;
    }
    void paint(HDC dc) override {
        int w = size().cx, h = size().cy, foc = focused() ? 0 : 21;
        blit(dc, L"pledit", 0, foc, 25, 20, 0, 0);
        for (int x = 25; x < w - 25; x += 25) blit(dc, L"pledit", 127, foc, 25, 20, x, 0);
        blit(dc, L"pledit", 26, foc, 100, 20, (w - 100) / 2, 0);
        blit(dc, L"pledit", 153, foc, 25, 20, w - 25, 0);
        for (int y = 20; y < h - 38; y += 29) {
            blit(dc, L"pledit", 0, 42, 12, 29, 0, y);
            blit(dc, L"pledit", 31, 42, 20, 29, w - 20, y);
        }
        blit(dc, L"pledit", 0, 72, 125, 38, 0, h - 38);
        for (int x = 125; x < w - 150; x += 25) blit(dc, L"pledit", 179, 0, 25, 38, x, h - 38);
        blit(dc, L"pledit", 126, 72, 150, 38, w - 150, h - 38);
        if (pressed == L"close") blit(dc, L"pledit", 52, 42, 9, 9, w - 11, 3);
        int sv = SaveDC(dc);
        clip(dc, 12, 20, w - 32, h - 58);
        fill(dc, 12, 20, w - 32, h - 58, g_skin->pl_normalbg);
        int n = (int)g_queue.size(), cur = current_index();
        top = std::max(0, std::min(top, std::max(0, n - visible_rows())));
        for (int r = 0; r < visible_rows(); r++) {
            int i = top + r;
            if (i >= n) break;
            int yy = 22 + r * ROW;
            if (sel.count(i)) fill(dc, 12, yy, w - 32, ROW, g_skin->pl_selectedbg);
            COLORREF col = i == cur ? g_skin->pl_current : g_skin->pl_normal;
            std::wstring nm = std::to_wstring(i + 1) + L". " + item_name(g_queue[i]);
            std::wstring len = g_queue[i].duration > 0 ? fmt_time(g_queue[i].duration) : L"";
            int lw = text_width(dc, len, 9, false, g_skin->pl_font);
            int s2 = SaveDC(dc);
            clip(dc, 12, yy, w - 32 - lw - 8, ROW);
            plain_text(dc, nm, 14, yy, col, 9, false, g_skin->pl_font);
            RestoreDC(dc, s2);
            plain_text(dc, len, w - 22 - lw, yy, col, 9, false, g_skin->pl_font);
        }
        if (!n && g_has_now && g_now.kind == 3) plain_text(dc, L"1. " + g_now.title, 14, 22, g_skin->pl_current, 9, false, g_skin->pl_font);
        RestoreDC(dc, sv);
        int span = h - 58 - 18;
        double f = n <= visible_rows() ? 0 : top / (double)std::max(1, n - visible_rows());
        blit(dc, L"pledit", pressed == L"scroll" ? 61 : 52, 53, 8, 18, w - 15, 20 + (int)(f * span));
        double total = 0, sel_total = 0;
        for (int i = 0; i < n && i < 2000; i++) {
            total += g_queue[i].duration;
            if (sel.count(i)) sel_total += g_queue[i].duration;
        }
        int s3 = SaveDC(dc);
        clip(dc, w - 143, h - 29, 90, 12);
        plain_text(dc, fmt_time(sel_total) + L"/" + fmt_time(total), w - 141, h - 29.5, g_skin->pl_normal, 8.5, false, g_skin->pl_font);
        RestoreDC(dc, s3);
    }
};

MainPart *mainp() { return (MainPart *)g_main_part; }
PlPart *plp() { return (PlPart *)g_pl_part; }
std::vector<Part *> all_parts() { return {g_main_part, g_eq_part, g_pl_part}; }
std::vector<Part *> shown_parts() {
    std::vector<Part *> out{g_main_part};
    if (S.eq) out.push_back(g_eq_part);
    if (S.pl) out.push_back(g_pl_part);
    return out;
}

bool owns(HWND h) {
    for (auto *p : all_parts()) if (p && (p->hwnd == h || IsChild(p->hwnd, h))) return true;
    return h && (h == g_lib_wnd || (g_lib_wnd && IsChild(g_lib_wnd, h)));
}

void redraw_all() { for (auto *p : all_parts()) if (p) p->redraw(); }

// ---------------------------------------------------------------- moving, snapping and docking
struct Move {
    Part *part = nullptr;
    POINT start{};
    RECT r0{};
    std::vector<std::pair<Part *, RECT>> docked;
} g_move;

bool touching(const RECT &a, const RECT &b) {
    bool ho = a.left < b.right && b.left < a.right, vo = a.top < b.bottom && b.top < a.bottom;
    return (ho && (std::abs(a.bottom - b.top) <= 1 || std::abs(b.bottom - a.top) <= 1)) ||
           (vo && (std::abs(a.right - b.left) <= 1 || std::abs(b.right - a.left) <= 1));
}

std::vector<Part *> docked_to(Part *w) {
    std::vector<Part *> shown;
    for (auto *p : shown_parts()) if (IsWindowVisible(p->hwnd)) shown.push_back(p);
    std::set<Part *> found{w};
    std::vector<Part *> todo{w};
    while (!todo.empty()) {
        Part *a = todo.back();
        todo.pop_back();
        for (auto *b : shown)
            if (!found.count(b) && touching(a->rect(), b->rect())) { found.insert(b); todo.push_back(b); }
    }
    std::vector<Part *> out;
    for (auto *p : found) if (p != w) out.push_back(p);
    return out;
}

POINT snap(Part *w, int x, int y, const std::vector<Part *> &ignore) {
    RECT wr = w->rect();
    int ww = wr.right - wr.left, hh = wr.bottom - wr.top;
    struct T { RECT r; bool outside; };
    std::vector<T> targets;
    for (auto *o : shown_parts()) {
        if (o == w || std::find(ignore.begin(), ignore.end(), o) != ignore.end() || !IsWindowVisible(o->hwnd)) continue;
        targets.push_back({o->rect(), true});
    }
    MONITORINFO mi{sizeof mi};
    GetMonitorInfoW(MonitorFromWindow(w->hwnd, MONITOR_DEFAULTTONEAREST), &mi);
    targets.push_back({mi.rcWork, false});
    int bx = x, by = y, best_x = SNAP + 1, best_y = SNAP + 1;
    for (auto &t : targets) {
        int ox = t.r.left, oy = t.r.top, ow = t.r.right - t.r.left, oh = t.r.bottom - t.r.top;
        std::vector<int> xs{ox, ox + ow - ww}, ys{oy, oy + oh - hh};
        if (t.outside) { xs.push_back(ox + ow); xs.push_back(ox - ww); ys.push_back(oy + oh); ys.push_back(oy - hh); }
        bool near_v = !t.outside || (y < oy + oh + SNAP && oy < y + hh + SNAP);
        bool near_h = !t.outside || (x < ox + ow + SNAP && ox < x + ww + SNAP);
        if (near_v) for (int c : xs) if (std::abs(c - x) < best_x) { best_x = std::abs(c - x); bx = c; }
        if (near_h) for (int c : ys) if (std::abs(c - y) < best_y) { best_y = std::abs(c - y); by = c; }
    }
    return {bx, by};
}

void begin_move(Part *p) {
    g_move = Move();
    g_move.part = p;
    GetCursorPos(&g_move.start);
    g_move.r0 = p->rect();
    if (p == g_main_part)
        for (auto *d : docked_to(p)) g_move.docked.push_back({d, d->rect()});
    SetCapture(p->hwnd);
}

void move_motion(Part *p) {
    if (g_move.part != p) return;
    POINT c;
    GetCursorPos(&c);
    int nx = g_move.r0.left + c.x - g_move.start.x, ny = g_move.r0.top + c.y - g_move.start.y;
    std::vector<Part *> ign;
    for (auto &d : g_move.docked) ign.push_back(d.first);
    POINT s = snap(p, nx, ny, ign);
    int dx = s.x - g_move.r0.left, dy = s.y - g_move.r0.top;
    SetWindowPos(p->hwnd, nullptr, s.x, s.y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
    for (auto &d : g_move.docked)
        SetWindowPos(d.first->hwnd, nullptr, d.second.left + dx, d.second.top + dy, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
}

void end_move(Part *p) {
    if (g_move.part != p) return;
    g_move = Move();
    ReleaseCapture();
    save_positions();
}

void save_positions() {
    for (auto *p : all_parts()) {
        RECT r = p->rect();
        S.pos[p->name] = {r.left, r.top};
    }
    save_settings();
}

void place() {
    int s = scale();
    POINT m = S.pos.count(L"main") ? S.pos[L"main"] : POINT{120, 120};
    std::map<std::wstring, POINT> def = {{L"main", m}, {L"eq", {m.x, m.y + H * s}}, {L"pl", {m.x, m.y + 2 * H * s}}};
    for (auto *p : all_parts()) {
        POINT pt = S.pos.count(p->name) ? S.pos[p->name] : def[p->name];
        // a position on a screen that's gone comes back to the main screen
        RECT test{pt.x, pt.y, pt.x + 40, pt.y + 14};
        if (!MonitorFromRect(&test, MONITOR_DEFAULTTONULL)) pt = def[p->name];
        SetWindowPos(p->hwnd, nullptr, pt.x, pt.y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
    }
}

// ---------------------------------------------------------------- the window procedure shared by the parts
LRESULT CALLBACK part_proc(HWND h, UINT m, WPARAM w, LPARAM l) {
    Part *p = (Part *)GetWindowLongPtrW(h, GWLP_USERDATA);
    if (m == WM_NCCREATE) {
        p = (Part *)((CREATESTRUCTW *)l)->lpCreateParams;
        SetWindowLongPtrW(h, GWLP_USERDATA, (LONG_PTR)p);
        p->hwnd = h;
    }
    if (!p) return DefWindowProcW(h, m, w, l);
    int s = scale();
    switch (m) {
        case WM_PAINT: {
            PAINTSTRUCT ps;
            HDC dc = BeginPaint(h, &ps);
            RECT rc;
            GetClientRect(h, &rc);
            HDC mem = CreateCompatibleDC(dc);
            HBITMAP bmp = CreateCompatibleBitmap(dc, rc.right, rc.bottom);
            HGDIOBJ old = SelectObject(mem, bmp);
            HBRUSH bg = CreateSolidBrush(RGB(0, 0, 0));
            FillRect(mem, &rc, bg);
            DeleteObject(bg);
            p->paint(mem);
            BitBlt(dc, 0, 0, rc.right, rc.bottom, mem, 0, 0, SRCCOPY);
            SelectObject(mem, old);
            DeleteObject(bmp);
            DeleteDC(mem);
            EndPaint(h, &ps);
            return 0;
        }
        case WM_ERASEBKGND: return 1;
        case WM_ACTIVATE: redraw_all(); return 0;
        case WM_MOUSEACTIVATE: return MA_ACTIVATE;
        case WM_LBUTTONDOWN:
        case WM_LBUTTONDBLCLK: {
            SetFocus(h);
            int x = GET_X_LPARAM(l) / s, y = GET_Y_LPARAM(l) / s;
            bool dbl = m == WM_LBUTTONDBLCLK;
            if (p->press(x, y, dbl, w & MK_CONTROL, w & MK_SHIFT)) { if (!dbl) SetCapture(h); return 0; }
            if (dbl) { p->dbl(x, y); return 0; }
            std::wstring n = p->hit(x, y);
            if (!n.empty()) {
                p->pressed = n;
                SetCapture(h);
                if (p->is_slider(n)) { p->slider = n; p->slide(n, x, y); }
                p->redraw();
                return 0;
            }
            if (p->title_hit(x, y) || p->drag_anywhere(x, y)) begin_move(p);
            return 0;
        }
        case WM_MOUSEMOVE: {
            int x = GET_X_LPARAM(l) / s, y = GET_Y_LPARAM(l) / s;
            if (!p->slider.empty()) { p->slide(p->slider, x, y); return 0; }
            if (p->motion(x, y)) return 0;
            if (g_move.part == p) move_motion(p);
            return 0;
        }
        case WM_LBUTTONUP: {
            int x = GET_X_LPARAM(l) / s, y = GET_Y_LPARAM(l) / s;
            if (p->release()) { ReleaseCapture(); return 0; }
            std::wstring was = p->pressed;
            p->pressed.clear();
            if (!p->slider.empty()) {
                std::wstring sl = p->slider;
                p->slider.clear();
                ReleaseCapture();
                p->slide_done(sl, x, y);
                p->redraw();
                return 0;
            }
            if (g_move.part == p) end_move(p);
            else ReleaseCapture();
            if (!was.empty() && p->hit(x, y) == was) p->click(was);
            p->redraw();
            return 0;
        }
        case WM_CAPTURECHANGED:
            if (g_move.part == p && (HWND)l != h) g_move = Move();
            return 0;
        case WM_RBUTTONUP: {
            int x = GET_X_LPARAM(l) / s, y = GET_Y_LPARAM(l) / s;
            POINT pt{GET_X_LPARAM(l), GET_Y_LPARAM(l)};
            ClientToScreen(h, &pt);
            if (p == g_pl_part && p->hit(x, y) == L"rows") {
                PlPart *pl = plp();
                int i = pl->top + (y - 22) / PlPart::ROW;
                if (i >= 0 && i < (int)g_queue.size() && !pl->sel.count(i)) pl->sel = {i};
                pl->redraw();
                row_menu(pt.x, pt.y);
            } else options_menu(p, pt.x, pt.y);
            return 0;
        }
        case WM_MOUSEWHEEL: {
            POINT pt{GET_X_LPARAM(l), GET_Y_LPARAM(l)};
            ScreenToClient(h, &pt);
            p->scrolled(GET_WHEEL_DELTA_WPARAM(w) > 0 ? 1 : -1, pt.x / s, pt.y / s);
            p->redraw();
            return 0;
        }
        case WM_SETCURSOR:
            if (LOWORD(l) == HTCLIENT && !g_skin->cursors.empty()) {
                POINT pt;
                GetCursorPos(&pt);
                ScreenToClient(h, &pt);
                HCURSOR c = g_skin->cursor(p->cursor_name(pt.x / s, pt.y / s), s);
                if (c) { SetCursor(c); return TRUE; }
            }
            break;
        case WM_KEYDOWN:
        case WM_SYSKEYDOWN:
            key(w, GetKeyState(VK_CONTROL) & 0x8000, GetKeyState(VK_MENU) & 0x8000, GetKeyState(VK_SHIFT) & 0x8000, p);
            return 0;
        case WM_SYSCHAR:
            return 0;       // Alt+letters are Chordamp's own keys (no menu bar here)
        case WM_TIMER:
            if (p == g_main_part && w == 1) {
                mainp()->tick();
                p->redraw();
                static int ticks;
                static size_t sig;
                if (++ticks % 10 == 0 && S.pl) {
                    size_t ns = g_queue.size() * 131 + (size_t)(current_index() + 1) * 7 + (size_t)g_has_now;
                    if (ns != sig) { sig = ns; g_pl_part->redraw(); }
                }
            }
            return 0;
        case WM_CLOSE:
            if (p == g_main_part) PostMessageW(g_wnd, WM_CLOSE, 0, 0);
            else toggle_window(p->name, 0);
            return 0;
        case WM_DROPFILES: {
            HDROP d = (HDROP)w;
            UINT n = DragQueryFileW(d, 0xFFFFFFFF, nullptr, 0);
            std::vector<std::wstring> paths;
            for (UINT i = 0; i < n; i++) {
                wchar_t f[MAX_PATH * 4];
                DragQueryFileW(d, i, f, MAX_PATH * 4);
                paths.push_back(f);
            }
            DragFinish(d);
            add_to_list(paths, false);
            return 0;
        }
    }
    return DefWindowProcW(h, m, w, l);
}

// ---------------------------------------------------------------- building, showing, hiding
void make_parts() {
    if (g_main_part) return;
    if (!g_skin) {
        if (!S.skin.empty()) {
            std::wstring err;
            g_skin = skin_load(skins_dir() + L"\\" + S.skin, err);
        }
        if (!g_skin) { g_skin = skin_own(); S.skin.clear(); }
    }
    WNDCLASSW wc{};
    wc.style = CS_DBLCLKS;
    wc.lpfnWndProc = part_proc;
    wc.hInstance = g_inst;
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    wc.hIcon = LoadIconW(g_inst, MAKEINTRESOURCEW(IDI_CHORD));
    wc.lpszClassName = L"Chordamp";
    RegisterClassW(&wc);
    g_main_part = new MainPart();
    g_eq_part = new EqPart();
    g_pl_part = new PlPart();
    int s = scale();
    HWND mh = CreateWindowExW(WS_EX_APPWINDOW | WS_EX_ACCEPTFILES, L"Chordamp", L"Chordamp", WS_POPUP | WS_SYSMENU | WS_MINIMIZEBOX,
                              120, 120, W * s, H * s, nullptr, nullptr, g_inst, g_main_part);
    CreateWindowExW(WS_EX_TOOLWINDOW, L"Chordamp", L"Chordamp Equalizer", WS_POPUP, 120, 236, W * s, H * s, mh, nullptr, g_inst, g_eq_part);
    CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_ACCEPTFILES, L"Chordamp", L"Chordamp Playlist", WS_POPUP, 120, 352, W * s, S.pl_h * s, mh,
                    nullptr, g_inst, g_pl_part);
    for (auto *p : all_parts()) p->resize_to();
}

DWORD g_ontop_error = 0;
void apply_ontop() {
    g_ontop_error = 0;
    for (auto *p : all_parts())
        if (!SetWindowPos(p->hwnd, S.ontop ? HWND_TOPMOST : HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE))
            g_ontop_error = GetLastError();
}

void show() {
    make_parts();
    g_visible = true;
    place();
    for (auto *p : all_parts()) { p->resize_to(); p->apply_shape(); }
    for (auto *p : shown_parts()) ShowWindow(p->hwnd, SW_SHOWNOACTIVATE);
    for (auto *p : all_parts()) if (std::find(shown_parts().begin(), shown_parts().end(), p) == shown_parts().end()) ShowWindow(p->hwnd, SW_HIDE);
    ShowWindow(g_main_part->hwnd, SW_SHOW);
    SetForegroundWindow(g_main_part->hwnd);
    apply_ontop();
    SetTimer(g_main_part->hwnd, 1, 50, nullptr);
    if (S.lib) show_library(1);
}

void hide() {
    if (!g_main_part) return;
    if (g_visible) save_positions();
    g_visible = false;
    KillTimer(g_main_part->hwnd, 1);
    for (auto *p : all_parts()) ShowWindow(p->hwnd, SW_HIDE);
    if (g_lib_wnd) ShowWindow(g_lib_wnd, SW_HIDE);
}

void switch_look(bool chordamp) {
    S.on = chordamp;
    if (chordamp) {
        show();
        ShowWindow(g_wnd, SW_HIDE);
    } else {
        hide();
        ShowWindow(g_wnd, SW_SHOW);
        SetForegroundWindow(g_wnd);
    }
    save_settings();
}

void toggle_window(const std::wstring &name, int on) {
    bool &flag = name == L"eq" ? S.eq : S.pl;
    Part *p = name == L"eq" ? g_eq_part : g_pl_part;
    flag = on < 0 ? !flag : on != 0;
    if (g_visible) ShowWindow(p->hwnd, flag ? SW_SHOWNOACTIVATE : SW_HIDE);
    g_main_part->redraw();
    save_settings();
}

void toggle_shade() {
    RECT old = g_main_part->rect();
    S.shade = !S.shade;
    g_main_part->resize_to();
    RECT neu = g_main_part->rect();
    int dh = (neu.bottom - neu.top) - (old.bottom - old.top);
    // windows docked under the player follow its new height
    for (Part *p : {g_eq_part, g_pl_part}) {
        RECT r = p->rect();
        if (r.top >= old.bottom - 1)
            SetWindowPos(p->hwnd, nullptr, r.left, r.top + dh, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
    }
    save_settings();
}

void set_double(bool on) {
    int old = scale();
    RECT m = g_main_part->rect();
    std::vector<RECT> rs;
    for (auto *p : all_parts()) rs.push_back(p->rect());
    S.dbl = on;
    int s = scale();
    for (auto &kv : g_fonts) DeleteObject(kv.second);
    g_fonts.clear();
    int k = 0;
    for (auto *p : all_parts()) {
        RECT r = rs[k++];
        p->resize_to();
        SetWindowPos(p->hwnd, nullptr, m.left + (r.left - m.left) * s / old, m.top + (r.top - m.top) * s / old, 0, 0,
                     SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
    }
    save_positions();
}

void set_ontop(bool on) { S.ontop = on; apply_ontop(); save_settings(); }

void set_vis(const std::wstring &v) { S.vis = v; g_main_part->redraw(); save_settings(); }

void set_skin(const std::wstring &file) {
    Skin *sk = nullptr;
    if (!file.empty()) {
        std::wstring err;
        sk = skin_load(skins_dir() + L"\\" + file, err);
        if (!sk) { info(L"“" + file + L"” isn't a skin Chordamp can read: " + err); return; }
    } else sk = skin_own();
    delete g_skin;
    g_skin = sk;
    S.skin = file;
    for (auto *p : all_parts()) { p->apply_shape(); p->redraw(); }
    save_settings();
}

void apply_eq(bool save) {
    g_player->set_eq(S.eq_on, S.preamp, S.bands);
    if (g_eq_part) g_eq_part->redraw();
    if (save) save_settings();
}

void load_preset(const std::wstring &name) {
    for (int i = 0; i < EQ_PRESET_COUNT; i++)
        if (name == EQ_PRESETS[i].name) {
            S.preamp = EQ_PRESETS[i].preamp;
            for (int b = 0; b < 10; b++) S.bands[b] = EQ_PRESETS[i].bands[b];
        }
    if (S.custom.count(name)) {
        auto &v = S.custom[name];
        S.preamp = v[0];
        for (int b = 0; b < 10; b++) S.bands[b] = v[b + 1];
    }
    S.preset = name;
    S.eq_on = true;
    apply_eq();
}

// ---------------------------------------------------------------- transport and the list
void transport(const std::wstring &n) {
    if (n == L"prev") on_command(CMD_PREV);
    else if (n == L"play") {
        if (g_player->paused()) g_player->play();
        else if (g_player->playing()) g_player->seek(0);
        else if (!g_queue.empty()) {
            int i = current_index() >= 0 ? current_index() : std::max(0, *(plp()->sel.empty() ? &plp()->focus_row : &*plp()->sel.begin()));
            plp()->play_index(std::min(i, (int)g_queue.size() - 1));
        } else if (g_has_now) start(g_now);
    } else if (n == L"pause") {
        if (g_player->playing() || g_player->paused()) g_player->toggle();
    } else if (n == L"stop") on_command(CMD_STOP);
    else if (n == L"next") on_command(CMD_NEXT);
    update_controls();
    redraw_all();
}

void seek_by(double secs) {
    double d = g_player->duration();
    if ((g_player->playing() || g_player->paused()) && d > 0) g_player->seek(std::max(0.0, std::min(d - 1, g_player->position() + secs)));
}

void play_file() {
    auto f = choose_files();
    if (!f.empty()) add_to_list(f, true);
}

void select(const std::wstring &how) {
    PlPart *pl = plp();
    int n = (int)g_queue.size();
    if (how == L"all") { pl->sel.clear(); for (int i = 0; i < n; i++) pl->sel.insert(i); }
    else if (how == L"none") pl->sel.clear();
    else {
        std::set<int> inv;
        for (int i = 0; i < n; i++) if (!pl->sel.count(i)) inv.insert(i);
        pl->sel = inv;
    }
    pl->redraw();
}

void keep_rows(const std::vector<int> &keep) {
    int cur = current_index();
    bool cur_kept = std::find(keep.begin(), keep.end(), cur) != keep.end();
    PlPart::set_order(keep, cur_kept ? cur : -1);
    if (!cur_kept) g_pos = -1;
    plp()->sel.clear();
    plp()->redraw();
}

void remove_selected() {
    std::vector<int> keep;
    for (int i = 0; i < (int)g_queue.size(); i++) if (!plp()->sel.count(i)) keep.push_back(i);
    keep_rows(keep);
}

void crop() {
    std::vector<int> keep(plp()->sel.begin(), plp()->sel.end());
    keep_rows(keep);
}

void remove_all() { keep_rows({}); }

void remove_missing() {
    std::vector<int> keep;
    for (int i = 0; i < (int)g_queue.size(); i++) {
        const QItem &q = g_queue[i];
        if (q.kind != 1 || GetFileAttributesW(q.url.c_str()) != INVALID_FILE_ATTRIBUTES) keep.push_back(i);
    }
    keep_rows(keep);
}

void sort(const std::wstring &how) {
    int n = (int)g_queue.size(), cur = current_index();
    std::vector<int> idx(n);
    for (int i = 0; i < n; i++) idx[i] = i;
    if (how == L"reverse") std::reverse(idx.begin(), idx.end());
    else if (how == L"random") {
        static std::mt19937 rng((unsigned)time(nullptr));
        std::shuffle(idx.begin(), idx.end(), rng);
    } else {
        auto keyf = [&](int i) -> std::wstring {
            const QItem &q = g_queue[i];
            Track *t = q.kind == 1 ? g_lib.find(q.id) : nullptr;
            if (how == L"path") return lower(q.url.substr(q.url.find_last_of(L"\\/") + 1));
            if (how == L"artist") {
                wchar_t b[16];
                swprintf(b, 16, L"%06d", t ? t->track_no : 0);
                return lower(q.artist) + L"\x01" + lower(t ? t->album : L"") + L"\x01" + b;
            }
            return lower(q.title);
        };
        std::stable_sort(idx.begin(), idx.end(), [&](int a, int b) { return keyf(a) < keyf(b); });
    }
    PlPart::set_order(idx, cur);
    plp()->sel.clear();
    plp()->redraw();
}

// songs (and folders) into the playlist editor; play: the first of them plays
void add_to_list(const std::vector<std::wstring> &paths, bool play) {
    auto *ids = new std::vector<int>;
    g_busy = L"Adding to the library…";
    background(
        [paths, ids]() {
            for (auto &p : paths) {
                DWORD a = GetFileAttributesW(p.c_str());
                if (a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY)) {
                    auto got = g_lib.add_folder(p);
                    ids->insert(ids->end(), got.begin(), got.end());
                } else if (int id = g_lib.add_file(p)) ids->push_back(id);
            }
            g_lib.save();
        },
        [ids, play]() {
            g_busy.clear();
            fill_list();
            int first = (int)g_queue.size();
            int cur = current_index();
            for (int id : *ids) if (Track *t = g_lib.find(id)) g_queue.push_back(song_item(*t));
            if (play && (int)g_queue.size() > first) {
                std::vector<QItem> items(g_queue.begin() + first, g_queue.end());
                play_queue(items, 0);
            } else {
                make_order(cur >= 0 ? cur : 0);
                g_pos = cur >= 0 ? (int)(std::find(g_order.begin(), g_order.end(), cur) - g_order.begin()) : -1;
            }
            if (g_pl_part) g_pl_part->redraw();
            delete ids;
        });
}

std::wstring save_file_dialog(const wchar_t *title, const wchar_t *filter, const wchar_t *def, const wchar_t *ext) {
    wchar_t buf[MAX_PATH * 4];
    wcscpy(buf, def);
    OPENFILENAMEW o = {sizeof o};
    o.hwndOwner = g_main_part->hwnd;
    o.lpstrFilter = filter;
    o.lpstrFile = buf;
    o.nMaxFile = MAX_PATH * 4;
    o.lpstrTitle = title;
    o.lpstrDefExt = ext;
    o.Flags = OFN_OVERWRITEPROMPT | OFN_EXPLORER;
    return GetSaveFileNameW(&o) ? buf : L"";
}

std::wstring open_file_dialog(const wchar_t *title, const wchar_t *filter) {
    wchar_t buf[MAX_PATH * 4] = L"";
    OPENFILENAMEW o = {sizeof o};
    o.hwndOwner = g_main_part->hwnd;
    o.lpstrFilter = filter;
    o.lpstrFile = buf;
    o.nMaxFile = MAX_PATH * 4;
    o.lpstrTitle = title;
    o.Flags = OFN_EXPLORER | OFN_FILEMUSTEXIST;
    return GetOpenFileNameW(&o) ? buf : L"";
}

bool save_list(std::wstring path = L"") {
    if (path.empty()) path = save_file_dialog(L"Save Playlist", L"Playlists (*.m3u)\0*.m3u;*.m3u8\0", L"Playlist.m3u", L"m3u");
    if (path.empty()) return false;
    std::wstring o = L"#EXTM3U\n";
    for (auto &q : g_queue) {
        if (q.kind == 3) continue;
        o += L"#EXTINF:" + std::to_wstring((int)q.duration) + L"," + item_name(q) + L"\n" + q.url + L"\n";
    }
    return write_file(path, narrow(o));
}

bool load_list(std::wstring path = L"") {
    if (path.empty()) path = open_file_dialog(L"Open Playlist", L"Playlists (*.m3u, *.m3u8, *.pls)\0*.m3u;*.m3u8;*.pls\0");
    if (path.empty()) return false;
    std::string data;
    if (!read_file(path, data)) return false;
    std::wstring base = path.substr(0, path.find_last_of(L"\\/"));
    std::vector<std::wstring> paths;
    for (auto &l : lines_of(data)) {
        std::wstring e = trim(l);
        if (e.empty() || e[0] == L'#') continue;
        if (lower(e).compare(0, 4, L"file") == 0 && e.find(L'=') != std::wstring::npos && e.find(L"://") == std::wstring::npos)
            e = trim(e.substr(e.find(L'=') + 1));
        if (e.find(L"://") != std::wstring::npos) continue;
        std::wstring p = (e.size() > 1 && (e[1] == L':' || e[0] == L'\\')) ? e : base + L"\\" + e;
        if (GetFileAttributesW(p.c_str()) != INVALID_FILE_ATTRIBUTES) paths.push_back(p);
    }
    g_queue.clear();
    g_order.clear();
    g_pos = -1;
    if (!paths.empty()) add_to_list(paths, false);
    plp()->sel.clear();
    plp()->redraw();
    return true;
}

void load_skin_dialog() {
    std::wstring path = open_file_dialog(L"Load Skin", L"Skins (*.wsz, *.zip)\0*.wsz;*.zip\0");
    if (path.empty()) return;
    std::wstring err;
    Skin *test = skin_load(path, err);
    if (!test) { info(L"That file isn't a skin Chordamp can read: " + err); return; }
    delete test;
    std::wstring name = path.substr(path.find_last_of(L"\\/") + 1), dest = skins_dir() + L"\\" + name;
    if (lower(path) != lower(dest)) CopyFileW(path.c_str(), dest.c_str(), FALSE);
    set_skin(name);
}

// ---------------------------------------------------------------- Jump to File
struct Jump { HWND dlg, edit, list; std::vector<int> shown; int pick = -1; bool done = false; };
Jump *g_jump;

void jump_fill() {
    wchar_t q[256];
    GetWindowTextW(g_jump->edit, q, 256);
    auto words = split(lower(trim(q)), L' ');
    SendMessageW(g_jump->list, LB_RESETCONTENT, 0, 0);
    g_jump->shown.clear();
    for (int i = 0; i < (int)g_queue.size(); i++) {
        std::wstring n = item_name(g_queue[i]), ln = lower(n);
        bool all = true;
        for (auto &w : words) if (!w.empty() && ln.find(w) == std::wstring::npos) all = false;
        if (!all) continue;
        SendMessageW(g_jump->list, LB_ADDSTRING, 0, (LPARAM)(std::to_wstring(i + 1) + L". " + n).c_str());
        g_jump->shown.push_back(i);
    }
    SendMessageW(g_jump->list, LB_SETCURSEL, 0, 0);
}

LRESULT CALLBACK jump_proc(HWND h, UINT m, WPARAM w, LPARAM l) {
    switch (m) {
        case WM_COMMAND:
            if ((HWND)l == g_jump->edit && HIWORD(w) == EN_CHANGE) { jump_fill(); return 0; }
            if ((HWND)l == g_jump->list && HIWORD(w) == LBN_DBLCLK) { PostMessageW(h, WM_COMMAND, IDOK, 0); return 0; }
            if (LOWORD(w) == IDOK) {
                int s = (int)SendMessageW(g_jump->list, LB_GETCURSEL, 0, 0);
                if (s >= 0 && s < (int)g_jump->shown.size()) g_jump->pick = g_jump->shown[s];
                g_jump->done = true;
                return 0;
            }
            if (LOWORD(w) == IDCANCEL) { g_jump->done = true; return 0; }
            break;
        case WM_CLOSE: g_jump->done = true; return 0;
    }
    return DefWindowProcW(h, m, w, l);
}

int jump(const std::wstring &typed = L"", bool auto_ok = false) {
    WNDCLASSW wc{};
    wc.lpfnWndProc = jump_proc;
    wc.hInstance = g_inst;
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.lpszClassName = L"ChordampJump";
    RegisterClassW(&wc);
    Jump j{};
    g_jump = &j;
    HWND owner = g_main_part->hwnd;
    RECT r = g_main_part->rect();
    j.dlg = CreateWindowExW(WS_EX_DLGMODALFRAME, L"ChordampJump", L"Jump to File", WS_POPUP | WS_CAPTION | WS_SYSMENU,
                            r.left, r.bottom, 420, 360, owner, nullptr, g_inst, nullptr);
    j.edit = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", typed.c_str(), WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL, 8, 8, 396, 24, j.dlg, nullptr, g_inst, nullptr);
    j.list = CreateWindowExW(WS_EX_CLIENTEDGE, L"LISTBOX", L"", WS_CHILD | WS_VISIBLE | WS_VSCROLL | LBS_NOTIFY | LBS_NOINTEGRALHEIGHT,
                             8, 40, 396, 240, j.dlg, nullptr, g_inst, nullptr);
    HWND ok = CreateWindowW(L"BUTTON", L"Jump to File", WS_CHILD | WS_VISIBLE | BS_DEFPUSHBUTTON, 216, 288, 100, 28, j.dlg, (HMENU)IDOK, g_inst, nullptr);
    HWND cancel = CreateWindowW(L"BUTTON", L"Close", WS_CHILD | WS_VISIBLE, 324, 288, 80, 28, j.dlg, (HMENU)IDCANCEL, g_inst, nullptr);
    for (HWND c : {j.edit, j.list, ok, cancel}) SendMessageW(c, WM_SETFONT, (WPARAM)g_font, TRUE);
    jump_fill();
    ShowWindow(j.dlg, SW_SHOW);
    SetFocus(j.edit);
    for (auto *p : all_parts()) EnableWindow(p->hwnd, FALSE);
    MSG msg;
    if (auto_ok) PostMessageW(j.dlg, WM_COMMAND, IDOK, 0);
    while (!j.done && GetMessageW(&msg, nullptr, 0, 0) > 0) {
        if (msg.message == WM_KEYDOWN && msg.wParam == VK_RETURN) { SendMessageW(j.dlg, WM_COMMAND, IDOK, 0); continue; }
        if (msg.message == WM_KEYDOWN && msg.wParam == VK_ESCAPE) { j.done = true; continue; }
        if (msg.message == WM_KEYDOWN && (msg.wParam == VK_DOWN || msg.wParam == VK_UP) && msg.hwnd == j.edit) {
            int s = (int)SendMessageW(j.list, LB_GETCURSEL, 0, 0) + (msg.wParam == VK_DOWN ? 1 : -1);
            SendMessageW(j.list, LB_SETCURSEL, std::max(0, s), 0);
            continue;
        }
        if (!IsDialogMessageW(j.dlg, &msg)) { TranslateMessage(&msg); DispatchMessageW(&msg); }
    }
    for (auto *p : all_parts()) EnableWindow(p->hwnd, TRUE);
    DestroyWindow(j.dlg);
    g_jump = nullptr;
    if (j.pick >= 0) plp()->play_index(j.pick);
    SetForegroundWindow(owner);
    return j.pick;
}

// ---------------------------------------------------------------- the media library window
struct LibState { HWND src, search, list, count; std::vector<int> ids; std::vector<Station> stations; } g_libs;

void lib_fill() {
    int s = (int)SendMessageW(g_libs.src, LB_GETCURSEL, 0, 0);
    wchar_t q[256];
    GetWindowTextW(g_libs.search, q, 256);
    std::wstring ql = lower(trim(q));
    ListView_DeleteAllItems(g_libs.list);
    g_libs.ids.clear();
    g_libs.stations.clear();
    auto add_row = [&](const std::wstring &a, const std::wstring &b, const std::wstring &c, const std::wstring &d) {
        if (!ql.empty() && lower(a + L" " + b + L" " + c).find(ql) == std::wstring::npos) return false;
        LVITEMW it{};
        it.mask = LVIF_TEXT;
        it.iItem = ListView_GetItemCount(g_libs.list);
        it.pszText = (LPWSTR)a.c_str();
        ListView_InsertItem(g_libs.list, &it);
        ListView_SetItemText(g_libs.list, it.iItem, 1, (LPWSTR)b.c_str());
        ListView_SetItemText(g_libs.list, it.iItem, 2, (LPWSTR)c.c_str());
        ListView_SetItemText(g_libs.list, it.iItem, 3, (LPWSTR)d.c_str());
        return true;
    };
    if (s <= 0 || s > 1 + (int)g_lib.playlists.size()) {
        if (s == 1 + (int)g_lib.playlists.size() + 1) {
            for (auto &st : g_online.favourites)
                if (add_row(st.name, st.tags.substr(0, st.tags.find(L',')), st.country, L"")) g_libs.stations.push_back(st);
        } else
            for (auto &t : g_lib.tracks)
                if (add_row(t.title, t.artist, t.album, fmt_time(t.duration))) g_libs.ids.push_back(t.id);
    } else {
        Playlist &p = g_lib.playlists[s - 1];
        for (int id : p.tracks)
            if (Track *t = g_lib.find(id))
                if (add_row(t->title, t->artist, t->album, fmt_time(t->duration))) g_libs.ids.push_back(t->id);
    }
    SetWindowTextW(g_libs.count, (std::to_wstring(ListView_GetItemCount(g_libs.list)) + L" items").c_str());
}

std::vector<int> lib_selected(bool all_if_none) {
    std::vector<int> out;
    int i = -1;
    while ((i = ListView_GetNextItem(g_libs.list, i, LVNI_SELECTED)) >= 0) out.push_back(i);
    if (out.empty() && all_if_none) for (int k = 0; k < ListView_GetItemCount(g_libs.list); k++) out.push_back(k);
    return out;
}

void lib_play(bool enqueue) {
    auto rows = lib_selected(false);
    if (rows.empty()) return;
    if (!g_libs.stations.empty()) {
        if (!enqueue && rows[0] < (int)g_libs.stations.size()) play_queue({station_item(g_libs.stations[rows[0]])}, 0);
        return;
    }
    std::vector<QItem> items;
    if (enqueue) {
        for (int r : rows) if (Track *t = g_lib.find(g_libs.ids[r])) g_queue.push_back(song_item(*t));
        int cur = current_index();
        make_order(cur >= 0 ? cur : 0);
        g_pos = cur >= 0 ? (int)(std::find(g_order.begin(), g_order.end(), cur) - g_order.begin()) : -1;
        plp()->redraw();
        return;
    }
    int first = rows[0];
    std::vector<int> use = rows.size() == 1 ? lib_selected(true) : rows;
    int idx = 0;
    for (int r : use) {
        if (r == first) idx = (int)items.size();
        if (Track *t = g_lib.find(g_libs.ids[r])) items.push_back(song_item(*t));
    }
    play_queue(items, idx);
    plp()->redraw();
}

LRESULT CALLBACK lib_proc(HWND h, UINT m, WPARAM w, LPARAM l) {
    switch (m) {
        case WM_SIZE: {
            int cw = LOWORD(l), ch = HIWORD(l);
            MoveWindow(g_libs.src, 6, 6, 150, ch - 12, TRUE);
            MoveWindow(g_libs.search, 162, 6, cw - 168, 24, TRUE);
            MoveWindow(g_libs.list, 162, 36, cw - 168, ch - 78, TRUE);
            MoveWindow(GetDlgItem(h, 1), 162, ch - 36, 80, 28, TRUE);
            MoveWindow(GetDlgItem(h, 2), 248, ch - 36, 80, 28, TRUE);
            MoveWindow(g_libs.count, cw - 160, ch - 32, 154, 22, TRUE);
            return 0;
        }
        case WM_COMMAND:
            if ((HWND)l == g_libs.src && HIWORD(w) == LBN_SELCHANGE) { lib_fill(); return 0; }
            if ((HWND)l == g_libs.search && HIWORD(w) == EN_CHANGE) { lib_fill(); return 0; }
            if (LOWORD(w) == 1) { lib_play(false); return 0; }
            if (LOWORD(w) == 2) { lib_play(true); return 0; }
            break;
        case WM_NOTIFY: {
            NMHDR *n = (NMHDR *)l;
            if (n->hwndFrom == g_libs.list && n->code == NM_DBLCLK) { lib_play(false); return 0; }
            break;
        }
        case WM_CLOSE: show_library(0); return 0;
    }
    return DefWindowProcW(h, m, w, l);
}

void lib_sources() {
    SendMessageW(g_libs.src, LB_RESETCONTENT, 0, 0);
    SendMessageW(g_libs.src, LB_ADDSTRING, 0, (LPARAM)L"Music");
    for (auto &p : g_lib.playlists) SendMessageW(g_libs.src, LB_ADDSTRING, 0, (LPARAM)p.name.c_str());
    SendMessageW(g_libs.src, LB_ADDSTRING, 0, (LPARAM)L"Radio Favourites");
    SendMessageW(g_libs.src, LB_SETCURSEL, 0, 0);
}

void show_library(int on) {
    S.lib = on != 0;
    if (!g_lib_wnd && on) {
        WNDCLASSW wc{};
        wc.lpfnWndProc = lib_proc;
        wc.hInstance = g_inst;
        wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
        wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
        wc.hIcon = LoadIconW(g_inst, MAKEINTRESOURCEW(IDI_CHORD));
        wc.lpszClassName = L"ChordampLibrary";
        RegisterClassW(&wc);
        RECT r = g_main_part->rect();
        g_lib_wnd = CreateWindowExW(0, L"ChordampLibrary", L"Chordamp Library", WS_OVERLAPPEDWINDOW, r.right + 8, r.top, 640, 420,
                                    g_main_part->hwnd, nullptr, g_inst, nullptr);
        g_libs.src = CreateWindowExW(WS_EX_CLIENTEDGE, L"LISTBOX", L"", WS_CHILD | WS_VISIBLE | WS_VSCROLL | LBS_NOTIFY | LBS_NOINTEGRALHEIGHT,
                                     0, 0, 10, 10, g_lib_wnd, nullptr, g_inst, nullptr);
        g_libs.search = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"", WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL, 0, 0, 10, 10, g_lib_wnd, nullptr, g_inst, nullptr);
        SendMessageW(g_libs.search, EM_SETCUEBANNER, TRUE, (LPARAM)L"Search");
        g_libs.list = CreateWindowExW(0, WC_LISTVIEWW, L"", WS_CHILD | WS_VISIBLE | WS_BORDER | LVS_REPORT | LVS_SHOWSELALWAYS, 0, 0, 10, 10,
                                      g_lib_wnd, nullptr, g_inst, nullptr);
        ListView_SetExtendedListViewStyle(g_libs.list, LVS_EX_FULLROWSELECT | LVS_EX_DOUBLEBUFFER);
        const wchar_t *cols[4] = {L"Title", L"Artist", L"Album", L"Time"};
        int widths[4] = {200, 130, 130, 50};
        for (int i = 0; i < 4; i++) {
            LVCOLUMNW c{};
            c.mask = LVCF_TEXT | LVCF_WIDTH;
            c.pszText = (LPWSTR)cols[i];
            c.cx = widths[i];
            ListView_InsertColumn(g_libs.list, i, &c);
        }
        HWND play = CreateWindowW(L"BUTTON", L"Play", WS_CHILD | WS_VISIBLE, 0, 0, 10, 10, g_lib_wnd, (HMENU)1, g_inst, nullptr);
        HWND enq = CreateWindowW(L"BUTTON", L"Enqueue", WS_CHILD | WS_VISIBLE, 0, 0, 10, 10, g_lib_wnd, (HMENU)2, g_inst, nullptr);
        g_libs.count = CreateWindowW(L"STATIC", L"", WS_CHILD | WS_VISIBLE | SS_RIGHT, 0, 0, 10, 10, g_lib_wnd, nullptr, g_inst, nullptr);
        for (HWND c : {g_libs.src, g_libs.search, g_libs.list, play, enq, g_libs.count}) SendMessageW(c, WM_SETFONT, (WPARAM)g_font, TRUE);
        RECT cr;
        GetClientRect(g_lib_wnd, &cr);
        SendMessageW(g_lib_wnd, WM_SIZE, 0, MAKELPARAM(cr.right, cr.bottom));
    }
    if (g_lib_wnd) {
        if (on) { lib_sources(); lib_fill(); ShowWindow(g_lib_wnd, SW_SHOW); SetForegroundWindow(g_lib_wnd); }
        else ShowWindow(g_lib_wnd, SW_HIDE);
    }
    save_settings();
}

// ---------------------------------------------------------------- menus
struct MenuItem {
    std::wstring label;
    std::function<void()> fn;
    int check = -1;                         // -1 none, 0 unchecked, 1 checked
    std::vector<MenuItem> sub;
    bool sep = false;
};
MenuItem sep() { MenuItem m; m.sep = true; return m; }
MenuItem item(const std::wstring &l, std::function<void()> f, int check = -1) { MenuItem m; m.label = l; m.fn = f; m.check = check; return m; }
MenuItem submenu(const std::wstring &l, std::vector<MenuItem> s) { MenuItem m; m.label = l; m.sub = s; return m; }

std::vector<std::function<void()>> g_menu_fns;
std::vector<MenuItem> g_last_menu;          // the last menu shown (the self test reads it)

HMENU build(const std::vector<MenuItem> &items) {
    HMENU m = CreatePopupMenu();
    for (auto &it : items) {
        if (it.sep) { AppendMenuW(m, MF_SEPARATOR, 0, nullptr); continue; }
        if (!it.sub.empty()) { AppendMenuW(m, MF_POPUP, (UINT_PTR)build(it.sub), it.label.c_str()); continue; }
        g_menu_fns.push_back(it.fn);
        AppendMenuW(m, MF_STRING | (it.check == 1 ? MF_CHECKED : 0), (UINT_PTR)g_menu_fns.size(), it.label.c_str());
    }
    return m;
}

// a test can answer the next menu instead of a person (the label of the entry to pick)
std::wstring g_menu_answer;
bool pick_in(const std::vector<MenuItem> &items, const std::wstring &label) {
    for (auto &it : items) {
        if (it.label == label && it.fn) { it.fn(); return true; }
        if (!it.sub.empty() && pick_in(it.sub, label)) return true;
    }
    return false;
}

void popup(const std::vector<MenuItem> &items, HWND owner, int x, int y) {
    g_last_menu = items;
    if (!g_menu_answer.empty()) {
        std::wstring a = g_menu_answer;
        g_menu_answer.clear();
        pick_in(items, a);
        return;
    }
    g_menu_fns.clear();
    HMENU m = build(items);
    SetForegroundWindow(owner);
    UINT cmd = TrackPopupMenu(m, TPM_RETURNCMD | TPM_RIGHTBUTTON, x, y, 0, owner, nullptr);
    DestroyMenu(m);
    if (cmd >= 1 && cmd <= g_menu_fns.size()) {
        auto fn = g_menu_fns[cmd - 1];
        if (fn) fn();
    }
}

std::vector<MenuItem> options_entries() {
    std::vector<MenuItem> skins = {item(L"Chordamp", [] { set_skin(L""); }, S.skin.empty())};
    for (auto &f : skins_installed()) skins.push_back(item(f.substr(0, f.find_last_of(L'.')), [f] { set_skin(f); }, S.skin == f));
    skins.push_back(sep());
    skins.push_back(item(L"Load Skin…", [] { load_skin_dialog(); }));
    skins.push_back(item(L"Save Chordamp Skin As…", [] {
        std::wstring p = save_file_dialog(L"Save Chordamp Skin", L"Skins (*.wsz)\0*.wsz\0", L"Chordamp.wsz", L"wsz");
        if (!p.empty()) skin_export_own(p);
    }));
    return {
        item(L"Standard Look", [] { switch_look(false); }),
        sep(),
        item(L"Play File…", [] { play_file(); }),
        item(L"Play Stream…", [] { on_command(CMD_OPEN_STREAM); }),
        item(L"Jump to File…", [] { jump(); }),
        sep(),
        item(L"Equalizer", [] { toggle_window(L"eq"); }, S.eq),
        item(L"Playlist Editor", [] { toggle_window(L"pl"); }, S.pl),
        item(L"Library", [] { show_library(!(g_lib_wnd && IsWindowVisible(g_lib_wnd))); }, g_lib_wnd && IsWindowVisible(g_lib_wnd)),
        sep(),
        submenu(L"Skins", skins),
        submenu(L"Visualization", {item(L"Spectrum", [] { set_vis(L"spectrum"); }, S.vis == L"spectrum"),
                                   item(L"Oscilloscope", [] { set_vis(L"oscilloscope"); }, S.vis == L"oscilloscope"),
                                   item(L"Off", [] { set_vis(L"off"); }, S.vis == L"off")}),
        item(L"Double Size", [] { set_double(!S.dbl); }, S.dbl),
        item(L"Always on Top", [] { set_ontop(!S.ontop); }, S.ontop),
        item(L"Shade Player", [] { toggle_shade(); }, S.shade),
        sep(),
        submenu(L"Playback", {item(L"Previous", [] { transport(L"prev"); }), item(L"Play", [] { transport(L"play"); }),
                              item(L"Pause", [] { transport(L"pause"); }), item(L"Stop", [] { transport(L"stop"); }),
                              item(L"Next", [] { transport(L"next"); }), sep(),
                              item(L"Back 5 Seconds", [] { seek_by(-5); }), item(L"Forward 5 Seconds", [] { seek_by(5); }), sep(),
                              item(L"Shuffle", [] { on_command(CMD_SHUFFLE); }, g_shuffle),
                              item(L"Repeat", [] { on_command(g_repeat ? CMD_REPEAT_OFF : CMD_REPEAT_ALL); }, g_repeat != 0)}),
        item(L"About Folio Chord", [] { on_command(CMD_ABOUT); }),
        sep(),
        item(L"Quit", [] { PostMessageW(g_wnd, WM_CLOSE, 0, 0); }),
    };
}

void options_menu(Part *p, int x, int y) { popup(options_entries(), p->hwnd, x, y); }

void presets_menu(Part *p) {
    std::vector<MenuItem> e;
    std::vector<std::wstring> names;
    for (int i = 0; i < EQ_PRESET_COUNT; i++) names.push_back(EQ_PRESETS[i].name);
    for (auto &kv : S.custom) if (std::find(names.begin(), names.end(), kv.first) == names.end()) names.push_back(kv.first);
    for (auto &n : names) e.push_back(item(n, [n] { load_preset(n); }, S.preset == n));
    e.push_back(sep());
    e.push_back(item(L"Reset to Flat", [] { load_preset(L"Flat"); }));
    e.push_back(item(L"Make Preset…", [] {
        std::wstring name;
        if (ask_text(L"Make Preset", L"Name of the preset:", name) && !name.empty()) {
            std::vector<double> v{S.preamp};
            for (double b : S.bands) v.push_back(b);
            S.custom[name] = v;
            S.preset = name;
            save_settings();
        }
    }));
    RECT r = p->rect();
    popup(e, p->hwnd, r.left + 217 * scale(), r.top + 30 * scale());
}

std::vector<MenuItem> pl_entries(const std::wstring &which) {
    if (which == L"add")
        return {item(L"Add File…", [] { auto f = choose_files(); if (!f.empty()) add_to_list(f, false); }),
                item(L"Add Folder…", [] { auto d = choose_folder(); if (!d.empty()) add_to_list({d}, false); }),
                item(L"Add Stream…", [] { on_command(CMD_OPEN_STREAM); })};
    if (which == L"rem")
        return {item(L"Remove Selected", [] { remove_selected(); }), item(L"Crop", [] { crop(); }),
                item(L"Remove All", [] { remove_all(); }), item(L"Remove Missing Files", [] { remove_missing(); })};
    if (which == L"sel")
        return {item(L"Select All", [] { select(L"all"); }), item(L"Select None", [] { select(L"none"); }),
                item(L"Invert Selection", [] { select(L"invert"); })};
    if (which == L"misc")
        return {item(L"Sort by Title", [] { sort(L"title"); }), item(L"Sort by Artist", [] { sort(L"artist"); }),
                item(L"Sort by File Name", [] { sort(L"path"); }), item(L"Reverse List", [] { sort(L"reverse"); }),
                item(L"Randomize List", [] { sort(L"random"); })};
    return {item(L"New List", [] { remove_all(); }), item(L"Open List…", [] { load_list(); }), item(L"Save List…", [] { save_list(); })};
}

void pl_menu(const std::wstring &which, Part *p) {
    RECT r = p->rect();
    int h = p->size().cy;
    std::map<std::wstring, int> xs = {{L"add", 14}, {L"rem", 43}, {L"sel", 72}, {L"misc", 101}, {L"list", W - 44}};
    popup(pl_entries(which), p->hwnd, r.left + xs[which] * scale(), r.top + (h - 30) * scale());
}

void row_menu(int x, int y) {
    std::vector<MenuItem> e = {item(L"Play", [] { if (!plp()->sel.empty()) plp()->play_index(*plp()->sel.begin()); }), sep()};
    auto rem = pl_entries(L"rem");
    e.push_back(rem[0]);
    e.push_back(rem[1]);
    popup(e, g_pl_part->hwnd, x, y);
}

bool pl_active() { return g_pl_part && GetForegroundWindow() == g_pl_part->hwnd; }

// ---------------------------------------------------------------- keys (as on Linux)
void key(WPARAM vk, bool ctrl, bool alt, bool shift, Part *from) {
    (void)from;
    if (ctrl && shift && vk == 'W') switch_look(false);
    else if (ctrl && vk == 'D') set_double(!S.dbl);
    else if (ctrl && vk == 'T') set_ontop(!S.ontop);
    else if (ctrl && vk == 'W') toggle_shade();
    else if (ctrl && vk == 'Q') PostMessageW(g_wnd, WM_CLOSE, 0, 0);
    else if (alt && vk == 'G') toggle_window(L"eq");
    else if (alt && vk == 'E') toggle_window(L"pl");
    else if (alt && vk == 'L') show_library(!(g_lib_wnd && IsWindowVisible(g_lib_wnd)));
    else if (ctrl && vk == 'A' && pl_active()) select(L"all");
    else if (alt && (vk == VK_UP || vk == VK_DOWN) && pl_active()) plp()->move_rows(vk == VK_UP ? -1 : 1);
    else if (ctrl || alt) return;
    else if (vk == 'Z') transport(L"prev");
    else if (vk == 'X') transport(L"play");
    else if (vk == 'C') transport(L"pause");
    else if (vk == 'V') transport(L"stop");
    else if (vk == 'B') transport(L"next");
    else if (vk == 'J') jump();
    else if (vk == 'L') play_file();
    else if (vk == 'S') on_command(CMD_SHUFFLE);
    else if (vk == 'R') on_command(g_repeat ? CMD_REPEAT_OFF : CMD_REPEAT_ALL);
    else if ((vk == VK_LEFT || vk == VK_RIGHT) && !pl_active()) seek_by(vk == VK_LEFT ? -5 : 5);
    else if ((vk == VK_UP || vk == VK_DOWN) && !pl_active()) { set_volume(g_vol + (vk == VK_UP ? 0.04 : -0.04)); update_controls(); }
    else if ((vk == VK_UP || vk == VK_DOWN) && pl_active()) {
        int n = (int)g_queue.size();
        if (n) {
            PlPart *pl = plp();
            pl->focus_row = std::max(0, std::min(n - 1, pl->focus_row + (vk == VK_UP ? -1 : 1)));
            pl->sel = {pl->focus_row};
            pl->anchor = pl->focus_row;
            pl->show_row(pl->focus_row);
            pl->redraw();
        }
    } else if (vk == VK_RETURN && pl_active()) { if (!plp()->sel.empty()) plp()->play_index(*plp()->sel.begin()); }
    else if (vk == VK_DELETE && pl_active()) remove_selected();
    else return;
    redraw_all();
}

// ---------------------------------------------------------------- the Standard look's Equalizer window
struct EqWin { HWND wnd = nullptr, on = nullptr, presets = nullptr, bal = nullptr, sliders[11] = {}; bool quiet = false; } g_eqw;

void eqw_sync() {
    if (!g_eqw.wnd) return;
    g_eqw.quiet = true;
    SendMessageW(g_eqw.on, BM_SETCHECK, S.eq_on ? BST_CHECKED : BST_UNCHECKED, 0);
    for (int i = 0; i < 11; i++)
        SendMessageW(g_eqw.sliders[i], TBM_SETPOS, TRUE, (LPARAM)std::lround(-(i == 0 ? S.preamp : S.bands[i - 1]) * 10));
    SendMessageW(g_eqw.bal, TBM_SETPOS, TRUE, (LPARAM)std::lround(S.balance * 100));
    int sel = (int)SendMessageW(g_eqw.presets, CB_FINDSTRINGEXACT, (WPARAM)-1, (LPARAM)S.preset.c_str());
    SendMessageW(g_eqw.presets, CB_SETCURSEL, sel, 0);
    g_eqw.quiet = false;
}

LRESULT CALLBACK eqw_proc(HWND h, UINT m, WPARAM w, LPARAM l) {
    switch (m) {
        case WM_VSCROLL:
        case WM_HSCROLL:
            if (g_eqw.quiet) return 0;
            if ((HWND)l == g_eqw.bal) {
                S.balance = SendMessageW(g_eqw.bal, TBM_GETPOS, 0, 0) / 100.0;
                if (std::fabs(S.balance) < 0.06) S.balance = 0;
                g_player->set_balance(S.balance);
                if (g_main_part) g_main_part->redraw();
                save_settings();
                return 0;
            }
            for (int i = 0; i < 11; i++)
                if ((HWND)l == g_eqw.sliders[i]) {
                    double v = -SendMessageW(g_eqw.sliders[i], TBM_GETPOS, 0, 0) / 10.0;
                    if (i == 0) S.preamp = v; else S.bands[i - 1] = v;
                    S.preset = L"Manual";
                    apply_eq(LOWORD(w) == TB_ENDTRACK || LOWORD(w) == TB_THUMBPOSITION);
                    g_eqw.quiet = true;
                    SendMessageW(g_eqw.presets, CB_SETCURSEL, (WPARAM)-1, 0);
                    g_eqw.quiet = false;
                }
            return 0;
        case WM_COMMAND:
            if ((HWND)l == g_eqw.on && HIWORD(w) == BN_CLICKED) {
                S.eq_on = SendMessageW(g_eqw.on, BM_GETCHECK, 0, 0) == BST_CHECKED;
                apply_eq();
                return 0;
            }
            if ((HWND)l == g_eqw.presets && HIWORD(w) == CBN_SELCHANGE && !g_eqw.quiet) {
                wchar_t b[128];
                int i = (int)SendMessageW(g_eqw.presets, CB_GETCURSEL, 0, 0);
                SendMessageW(g_eqw.presets, CB_GETLBTEXT, i, (LPARAM)b);
                load_preset(b);
                eqw_sync();
                return 0;
            }
            break;
        case WM_CLOSE: ShowWindow(h, SW_HIDE); return 0;
    }
    return DefWindowProcW(h, m, w, l);
}

void standard_equalizer() {
    if (!g_eqw.wnd) {
        WNDCLASSW wc{};
        wc.lpfnWndProc = eqw_proc;
        wc.hInstance = g_inst;
        wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
        wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
        wc.hIcon = LoadIconW(g_inst, MAKEINTRESOURCEW(IDI_CHORD));
        wc.lpszClassName = L"ChordEqualizer";
        RegisterClassW(&wc);
        RECT wr{0, 0, 560, 300};
        AdjustWindowRect(&wr, WS_CAPTION | WS_SYSMENU, FALSE);
        g_eqw.wnd = CreateWindowExW(WS_EX_TOOLWINDOW, L"ChordEqualizer", L"Equalizer", WS_POPUP | WS_CAPTION | WS_SYSMENU, CW_USEDEFAULT, CW_USEDEFAULT,
                                    wr.right - wr.left, wr.bottom - wr.top, g_wnd, nullptr, g_inst, nullptr);
        auto mk = [&](const wchar_t *cls, const wchar_t *text, DWORD style, int x, int y, int w, int h) {
            HWND c = CreateWindowExW(0, cls, text, WS_CHILD | WS_VISIBLE | style, x, y, w, h, g_eqw.wnd, nullptr, g_inst, nullptr);
            SendMessageW(c, WM_SETFONT, (WPARAM)g_font, TRUE);
            return c;
        };
        g_eqw.on = mk(L"BUTTON", L"On", BS_AUTOCHECKBOX, 16, 12, 60, 24);
        g_eqw.presets = mk(L"COMBOBOX", L"", CBS_DROPDOWNLIST | WS_VSCROLL, 300, 10, 244, 400);
        for (int i = 0; i < EQ_PRESET_COUNT; i++) SendMessageW(g_eqw.presets, CB_ADDSTRING, 0, (LPARAM)EQ_PRESETS[i].name);
        for (auto &kv : S.custom) SendMessageW(g_eqw.presets, CB_ADDSTRING, 0, (LPARAM)kv.first.c_str());
        const wchar_t *labels[11] = {L"Preamp", L"32", L"64", L"125", L"250", L"500", L"1K", L"2K", L"4K", L"8K", L"16K"};
        for (int i = 0; i < 11; i++) {
            int x = i == 0 ? 16 : 80 + (i - 1) * 46;
            g_eqw.sliders[i] = mk(TRACKBAR_CLASSW, L"", TBS_VERT | TBS_BOTH | TBS_NOTICKS, x, 46, 36, 170);
            SendMessageW(g_eqw.sliders[i], TBM_SETRANGE, TRUE, MAKELPARAM(-120, 120));
            mk(L"STATIC", labels[i], SS_CENTER, x - 8, 220, 52, 18);
        }
        mk(L"STATIC", L"+12 dB", 0, 520 - 6, 46, 46, 18);
        mk(L"STATIC", L"Balance", 0, 16, 256, 60, 20);
        g_eqw.bal = mk(TRACKBAR_CLASSW, L"", TBS_HORZ | TBS_BOTH | TBS_NOTICKS, 80, 250, 220, 30);
        SendMessageW(g_eqw.bal, TBM_SETRANGE, TRUE, MAKELPARAM(-100, 100));
    }
    eqw_sync();
    ShowWindow(g_eqw.wnd, SW_SHOW);
    SetForegroundWindow(g_eqw.wnd);
}

}  // namespace ca
