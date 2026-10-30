#include "skin.h"
#include "resource.h"
#include <wincodec.h>

// ===================================================================== inflate (RFC 1951), written here
namespace {
struct Bits {
    const unsigned char *p;
    size_t n, at = 0;
    unsigned buf = 0;
    int cnt = 0;
    bool bad = false;
    int need(int k) {
        while (cnt < k) {
            if (at >= n) { bad = true; return 0; }
            buf |= (unsigned)p[at++] << cnt;
            cnt += 8;
        }
        int v = (int)(buf & ((1u << k) - 1));
        buf >>= k;
        cnt -= k;
        return v;
    }
};

struct Huff {
    short count[16] = {}, symbol[320] = {};
};

int build(Huff &h, const short *lengths, int n) {
    for (int i = 0; i < 16; i++) h.count[i] = 0;
    for (int i = 0; i < n; i++) h.count[lengths[i]]++;
    if (h.count[0] == n) return 0;
    int left = 1;
    for (int len = 1; len < 16; len++) {
        left <<= 1;
        left -= h.count[len];
        if (left < 0) return -1;
    }
    short offs[16];
    offs[1] = 0;
    for (int len = 1; len < 15; len++) offs[len + 1] = offs[len] + h.count[len];
    for (int i = 0; i < n; i++)
        if (lengths[i]) h.symbol[offs[lengths[i]]++] = (short)i;
    return left;
}

int decode(Bits &b, const Huff &h) {
    int code = 0, first = 0, index = 0;
    for (int len = 1; len < 16; len++) {
        code |= b.need(1);
        if (b.bad) return -1;
        int count = h.count[len];
        if (code - count < first) return h.symbol[index + (code - first)];
        index += count;
        first += count;
        first <<= 1;
        code <<= 1;
    }
    return -1;
}

const short LBASE[29] = {3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258};
const short LEXT[29] = {0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0};
const short DBASE[30] = {1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537, 2049, 3073,
                         4097, 6145, 8193, 12289, 16385, 24577};
const short DEXT[30] = {0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13};

bool codes(Bits &b, std::string &out, const Huff &lc, const Huff &dc) {
    for (;;) {
        int sym = decode(b, lc);
        if (sym < 0) return false;
        if (sym < 256) out.push_back((char)sym);
        else if (sym == 256) return true;
        else {
            sym -= 257;
            if (sym >= 29) return false;
            int len = LBASE[sym] + b.need(LEXT[sym]);
            int ds = decode(b, dc);
            if (ds < 0 || ds >= 30) return false;
            size_t dist = DBASE[ds] + b.need(DEXT[ds]);
            if (b.bad || dist > out.size()) return false;
            size_t from = out.size() - dist;
            for (int i = 0; i < len; i++) out.push_back(out[from + i]);
        }
    }
}
}  // namespace

bool inflate_raw(const unsigned char *src, size_t n, std::string &out) {
    Bits b{src, n};
    int last;
    do {
        last = b.need(1);
        int type = b.need(2);
        if (b.bad) return false;
        if (type == 0) {
            b.buf = 0;
            b.cnt = 0;
            if (b.at + 4 > n) return false;
            unsigned len = src[b.at] | (src[b.at + 1] << 8);
            b.at += 4;
            if (b.at + len > n) return false;
            out.append((const char *)src + b.at, len);
            b.at += len;
        } else if (type == 1) {
            static Huff lc, dc;
            static bool made = false;
            if (!made) {
                short l[288];
                for (int i = 0; i < 144; i++) l[i] = 8;
                for (int i = 144; i < 256; i++) l[i] = 9;
                for (int i = 256; i < 280; i++) l[i] = 7;
                for (int i = 280; i < 288; i++) l[i] = 8;
                build(lc, l, 288);
                short d[30];
                for (int i = 0; i < 30; i++) d[i] = 5;
                build(dc, d, 30);
                made = true;
            }
            if (!codes(b, out, lc, dc)) return false;
        } else if (type == 2) {
            int nlen = b.need(5) + 257, ndist = b.need(5) + 1, ncode = b.need(4) + 4;
            static const short order[19] = {16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15};
            short lengths[320] = {};
            for (int i = 0; i < ncode; i++) lengths[order[i]] = (short)b.need(3);
            Huff lencode;
            if (build(lencode, lengths, 19) != 0) return false;
            int idx = 0;
            while (idx < nlen + ndist) {
                int sym = decode(b, lencode);
                if (sym < 0) return false;
                if (sym < 16) lengths[idx++] = (short)sym;
                else {
                    short len = 0;
                    int rep;
                    if (sym == 16) {
                        if (idx == 0) return false;
                        len = lengths[idx - 1];
                        rep = 3 + b.need(2);
                    } else if (sym == 17) rep = 3 + b.need(3);
                    else rep = 11 + b.need(7);
                    if (idx + rep > nlen + ndist) return false;
                    while (rep--) lengths[idx++] = len;
                }
            }
            Huff lc, dc;
            int e = build(lc, lengths, nlen);
            if (e < 0 || (e > 0 && nlen - lc.count[0] != 1)) return false;
            e = build(dc, lengths + nlen, ndist);
            if (e < 0 || (e > 0 && ndist - dc.count[0] != 1)) return false;
            if (!codes(b, out, lc, dc)) return false;
        } else return false;
    } while (!last);
    return true;
}

// ===================================================================== zip
static unsigned u16(const std::string &s, size_t at) { return (unsigned char)s[at] | ((unsigned char)s[at + 1] << 8); }
static unsigned u32(const std::string &s, size_t at) { return u16(s, at) | (u16(s, at + 2) << 16); }

bool zip_read(const std::string &zip, std::map<std::wstring, std::string> &files) {
    if (zip.size() < 22) return false;
    size_t end = std::string::npos;
    for (size_t i = zip.size() - 22 + 1; i-- > 0 && zip.size() - i < 70000;)
        if (u32(zip, i) == 0x06054b50) { end = i; break; }
    if (end == std::string::npos) return false;
    unsigned count = u16(zip, end + 10);
    size_t at = u32(zip, end + 16);
    for (unsigned k = 0; k < count; k++) {
        if (at + 46 > zip.size() || u32(zip, at) != 0x02014b50) return false;
        unsigned method = u16(zip, at + 10);
        size_t csize = u32(zip, at + 20), usize = u32(zip, at + 24);
        unsigned nlen = u16(zip, at + 28), elen = u16(zip, at + 30), clen = u16(zip, at + 32);
        size_t local = u32(zip, at + 42);
        std::string name = zip.substr(at + 46, nlen);
        at += 46 + nlen + elen + clen;
        if (name.empty() || name.back() == '/') continue;
        if (local + 30 > zip.size()) continue;
        size_t data = local + 30 + u16(zip, local + 26) + u16(zip, local + 28);
        if (data + csize > zip.size()) continue;
        std::string bytes;
        if (method == 0) bytes = zip.substr(data, csize);
        else if (method == 8) {
            bytes.reserve(usize);
            if (!inflate_raw((const unsigned char *)zip.data() + data, csize, bytes)) continue;
        } else continue;
        size_t slash = name.find_last_of("/\\");
        std::wstring base = lower(widen(slash == std::string::npos ? name : name.substr(slash + 1)));
        files[base] = bytes;
    }
    return !files.empty();
}

// ===================================================================== pictures
static IWICImagingFactory *wic() {
    static IWICImagingFactory *f = nullptr;
    if (!f) CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&f));
    return f;
}

static bool make_sheet(const std::string &bytes, Sheet &out) {
    IWICImagingFactory *f = wic();
    if (!f || bytes.empty()) return false;
    IWICStream *st = nullptr;
    IWICBitmapDecoder *dec = nullptr;
    IWICBitmapFrameDecode *fr = nullptr;
    IWICFormatConverter *cv = nullptr;
    bool ok = false;
    if (SUCCEEDED(f->CreateStream(&st)) && SUCCEEDED(st->InitializeFromMemory((BYTE *)bytes.data(), (DWORD)bytes.size())) &&
        SUCCEEDED(f->CreateDecoderFromStream(st, nullptr, WICDecodeMetadataCacheOnDemand, &dec)) &&
        SUCCEEDED(dec->GetFrame(0, &fr)) && SUCCEEDED(f->CreateFormatConverter(&cv)) &&
        SUCCEEDED(cv->Initialize(fr, GUID_WICPixelFormat32bppBGR, WICBitmapDitherTypeNone, nullptr, 0, WICBitmapPaletteTypeCustom))) {
        UINT w = 0, h = 0;
        cv->GetSize(&w, &h);
        BITMAPINFO bi{};
        bi.bmiHeader.biSize = sizeof bi.bmiHeader;
        bi.bmiHeader.biWidth = (LONG)w;
        bi.bmiHeader.biHeight = -(LONG)h;
        bi.bmiHeader.biPlanes = 1;
        bi.bmiHeader.biBitCount = 32;
        void *bits = nullptr;
        HBITMAP bmp = CreateDIBSection(nullptr, &bi, DIB_RGB_COLORS, &bits, nullptr, 0);
        if (bmp && SUCCEEDED(cv->CopyPixels(nullptr, w * 4, w * h * 4, (BYTE *)bits))) {
            out.bmp = bmp;
            out.dc = CreateCompatibleDC(nullptr);
            SelectObject(out.dc, bmp);
            out.w = (int)w;
            out.h = (int)h;
            ok = true;
        } else if (bmp) DeleteObject(bmp);
    }
    if (cv) cv->Release();
    if (fr) fr->Release();
    if (dec) dec->Release();
    if (st) st->Release();
    return ok;
}

Skin::~Skin() {
    for (auto &kv : sheets) {
        if (kv.second.dc) DeleteDC(kv.second.dc);
        if (kv.second.bmp) DeleteObject(kv.second.bmp);
    }
    for (auto &kv : made) if (kv.second) DestroyCursor(kv.second);
}

bool Skin::blit(HDC dc, const std::wstring &sheet, int sx, int sy, int w, int h, int dx, int dy, int s) const {
    auto it = sheets.find(sheet);
    if (it == sheets.end() || w <= 0 || h <= 0) return false;
    const Sheet &sh = it->second;
    // parts outside the sheet are left undrawn, as the original players do
    int cw = std::min(w, sh.w - sx), ch = std::min(h, sh.h - sy);
    if (cw <= 0 || ch <= 0 || sx < 0 || sy < 0) return false;
    if (s == 1) return BitBlt(dc, dx, dy, cw, ch, sh.dc, sx, sy, SRCCOPY) != 0;
    SetStretchBltMode(dc, COLORONCOLOR);
    return StretchBlt(dc, dx * s, dy * s, cw * s, ch * s, sh.dc, sx, sy, cw, ch, SRCCOPY) != 0;
}

HCURSOR Skin::cursor(const std::wstring &cname, int scale) {
    auto it = cursors.find(cname);
    if (it == cursors.end()) it = cursors.find(L"normal");
    if (it == cursors.end()) return nullptr;
    auto key = std::make_pair(it->first, scale);
    auto m = made.find(key);
    if (m != made.end()) return m->second;
    const std::string &d = it->second;
    HCURSOR c = nullptr;
    // a .cur: header, one directory entry (hot spot inside), then the image
    if (d.size() > 22 && u16(d, 2) == 2 && u16(d, 4) >= 1) {
        int w = (unsigned char)d[6] ? (unsigned char)d[6] : 256, h = (unsigned char)d[7] ? (unsigned char)d[7] : 256;
        unsigned hx = u16(d, 10), hy = u16(d, 12);
        size_t size = u32(d, 14), off = u32(d, 18);
        if (off + size <= d.size()) {
            std::string res;
            res.push_back((char)(hx & 255)); res.push_back((char)(hx >> 8));
            res.push_back((char)(hy & 255)); res.push_back((char)(hy >> 8));
            res += d.substr(off, size);
            c = (HCURSOR)CreateIconFromResourceEx((PBYTE)res.data(), (DWORD)res.size(), FALSE, 0x00030000, w * scale, h * scale, 0);
        }
    }
    made[key] = c;
    return c;
}

// ===================================================================== loading
static const wchar_t *SHEETS[] = {L"main", L"titlebar", L"cbuttons", L"numbers", L"playpaus", L"monoster", L"posbar",
                                  L"volume", L"balance", L"shufrep", L"eqmain", L"pledit", L"text"};

static COLORREF hex_colour(const std::string &v, bool &ok) {
    std::string t;
    for (char c : v) if (isxdigit((unsigned char)c)) t += c;
    ok = t.size() >= 6;
    if (!ok) return 0;
    unsigned x = std::stoul(t.substr(0, 6), nullptr, 16);
    return RGB((x >> 16) & 255, (x >> 8) & 255, x & 255);
}

static std::vector<std::string> text_lines(const std::string &s) {
    std::vector<std::string> out;
    std::string cur;
    for (char c : s) {
        if (c == '\n') { out.push_back(cur); cur.clear(); }
        else if (c != '\r') cur += c;
    }
    if (!cur.empty()) out.push_back(cur);
    return out;
}

static std::vector<int> numbers(const std::string &v) {
    std::vector<int> out;
    std::string cur;
    for (char c : v + " ") {
        if (isdigit((unsigned char)c) || (c == '-' && cur.empty())) cur += c;
        else { if (!cur.empty() && cur != "-") out.push_back(atoi(cur.c_str())); cur.clear(); }
    }
    return out;
}

static void parse_region(const std::string &text, Skin &sk) {
    std::string sec;
    std::map<std::string, std::string> vals;
    auto flush = [&] {
        if (sec.empty() || !vals.count("numpoints") || !vals.count("pointlist")) return;
        auto counts = numbers(vals["numpoints"]), pts = numbers(vals["pointlist"]);
        std::vector<std::vector<POINT>> polys;
        size_t i = 0;
        for (int c : counts) {
            if (c >= 3 && (i + c) * 2 <= pts.size()) {
                std::vector<POINT> poly;
                for (int k = 0; k < c; k++) poly.push_back({pts[(i + k) * 2], pts[(i + k) * 2 + 1]});
                polys.push_back(poly);
            }
            i += c;
        }
        if (!polys.empty()) sk.regions[widen(sec)] = polys;
    };
    for (auto line : text_lines(text)) {
        auto sc = line.find(';');
        if (sc != std::string::npos) line = line.substr(0, sc);
        while (!line.empty() && isspace((unsigned char)line.back())) line.pop_back();
        while (!line.empty() && isspace((unsigned char)line.front())) line.erase(0, 1);
        if (line.size() > 2 && line.front() == '[' && line.back() == ']') {
            flush();
            sec = line.substr(1, line.size() - 2);
            for (auto &c : sec) c = (char)tolower((unsigned char)c);
            vals.clear();
        } else if (!sec.empty() && line.find('=') != std::string::npos) {
            std::string k = line.substr(0, line.find('='));
            for (auto &c : k) c = (char)tolower((unsigned char)c);
            while (!k.empty() && isspace((unsigned char)k.back())) k.pop_back();
            vals[k] += " " + line.substr(line.find('=') + 1);
        }
    }
    flush();
}

static void fill_from(Skin &sk, std::map<std::wstring, std::string> &files, bool own) {
    for (auto *s : SHEETS) {
        std::wstring n = s;
        auto it = files.find(n + L".bmp");
        if (it == files.end()) it = files.find(n + L".png");
        if (it == files.end()) continue;
        Sheet sh;
        if (make_sheet(it->second, sh)) {
            auto old = sk.sheets.find(n);
            if (old != sk.sheets.end()) { DeleteDC(old->second.dc); DeleteObject(old->second.bmp); }
            sk.sheets[n] = sh;
            if (n == L"text") sk.text_bitmap = true;
        }
    }
    if (files.count(L"viscolor.txt")) {
        std::vector<COLORREF> cols;
        for (auto &line : text_lines(files[L"viscolor.txt"])) {
            auto l = line.substr(0, line.find("//"));
            auto v = numbers(l);
            if (v.size() >= 3) cols.push_back(RGB(std::min(255, std::max(0, v[0])), std::min(255, std::max(0, v[1])), std::min(255, std::max(0, v[2]))));
        }
        if (cols.size() >= 24) for (int i = 0; i < 24; i++) sk.vis[i] = cols[i];
    }
    if (files.count(L"region.txt")) parse_region(files[L"region.txt"], sk);
    for (auto &kv : files)
        if (kv.first.size() > 4 && kv.first.substr(kv.first.size() - 4) == L".cur") sk.cursors[kv.first.substr(0, kv.first.size() - 4)] = kv.second;
    if (files.count(L"pledit.txt")) {
        for (auto &line : text_lines(files[L"pledit.txt"])) {
            auto eq = line.find('=');
            if (eq == std::string::npos) continue;
            std::string k = line.substr(0, eq), v = line.substr(eq + 1);
            for (auto &c : k) c = (char)tolower((unsigned char)c);
            while (!k.empty() && isspace((unsigned char)k.back())) k.pop_back();
            while (!v.empty() && isspace((unsigned char)v.back())) v.pop_back();
            while (!v.empty() && isspace((unsigned char)v.front())) v.erase(0, 1);
            bool ok;
            if (k == "font") {
                if (!v.empty()) sk.pl_font = own || v == "Sans" ? L"Segoe UI" : widen(v);
            } else if (k == "normal") { COLORREF c = hex_colour(v, ok); if (ok) sk.pl_normal = c; }
            else if (k == "current") { COLORREF c = hex_colour(v, ok); if (ok) sk.pl_current = c; }
            else if (k == "normalbg") { COLORREF c = hex_colour(v, ok); if (ok) sk.pl_normalbg = c; }
            else if (k == "selectedbg") { COLORREF c = hex_colour(v, ok); if (ok) sk.pl_selectedbg = c; }
        }
    }
}

static std::string own_wsz() {
    HRSRC r = FindResourceW(nullptr, MAKEINTRESOURCEW(IDR_CHORDAMP_SKIN), RT_RCDATA);
    if (!r) return "";
    HGLOBAL g = LoadResource(nullptr, r);
    return std::string((const char *)LockResource(g), SizeofResource(nullptr, r));
}

Skin *skin_own() {
    auto *sk = new Skin();
    for (int i = 0; i < 24; i++) sk->vis[i] = RGB(0, 0, 0);
    std::map<std::wstring, std::string> files;
    if (zip_read(own_wsz(), files)) fill_from(*sk, files, true);
    sk->lcd = RGB(255, 79, 199);
    return sk;
}

Skin *skin_load(const std::wstring &path, std::wstring &error) {
    std::string data;
    if (!read_file(path, data)) { error = L"it couldn't be read"; return nullptr; }
    std::map<std::wstring, std::string> files;
    if (!zip_read(data, files)) { error = L"it isn't a skin file (.wsz)"; return nullptr; }
    bool any = false;
    for (auto *s : SHEETS) if (files.count(std::wstring(s) + L".bmp") || files.count(std::wstring(s) + L".png")) any = true;
    if (!any) { error = L"there are no skin pictures in it"; return nullptr; }
    Skin *sk = skin_own();                    // what the skin lacks comes from Chordamp's own
    size_t slash = path.find_last_of(L"\\/");
    sk->name = path.substr(slash == std::wstring::npos ? 0 : slash + 1);
    fill_from(*sk, files, false);
    return sk;
}

std::wstring skins_dir() {
    std::wstring d = data_dir() + L"\\Skins";
    CreateDirectoryW(d.c_str(), nullptr);
    return d;
}

std::vector<std::wstring> skins_installed() {
    std::vector<std::wstring> out;
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW((skins_dir() + L"\\*").c_str(), &fd);
    if (h == INVALID_HANDLE_VALUE) return out;
    do {
        std::wstring n = fd.cFileName, l = lower(n);
        if (l.size() > 4 && (l.substr(l.size() - 4) == L".wsz" || l.substr(l.size() - 4) == L".zip")) out.push_back(n);
    } while (FindNextFileW(h, &fd));
    FindClose(h);
    std::sort(out.begin(), out.end(), [](const std::wstring &a, const std::wstring &b) { return lower(a) < lower(b); });
    return out;
}

bool skin_export_own(const std::wstring &path) { return write_file(path, own_wsz()); }
