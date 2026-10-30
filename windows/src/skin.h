// Chordamp skins (C3-33): sprite sheets laid out as classic player skins (.wsz: a zip of bitmaps).
// Chordamp's own skin is built into FolioChord.exe (made by Folio Chord's own skin code on Linux);
// a downloaded skin's missing sheets come from it. Also its colours (viscolor.txt, pledit.txt),
// its window shapes (region.txt) and its pointers (.cur).
#pragma once
#include "common.h"

struct Sheet {
    HBITMAP bmp = nullptr;
    HDC dc = nullptr;
    int w = 0, h = 0;
};

class Skin {
public:
    std::wstring name;                                   // "" for Chordamp's own
    std::map<std::wstring, Sheet> sheets;                // main, titlebar, cbuttons, ...
    COLORREF vis[24];
    COLORREF pl_normal = RGB(0, 255, 0), pl_current = RGB(255, 255, 255), pl_normalbg = RGB(0, 0, 0),
             pl_selectedbg = RGB(0, 0, 200);
    std::wstring pl_font = L"Segoe UI";
    bool text_bitmap = false;                            // text.bmp: draw text from it
    COLORREF lcd = RGB(255, 79, 199);                    // text colour without text.bmp
    std::map<std::wstring, std::vector<std::vector<POINT>>> regions;   // region.txt sections
    std::map<std::wstring, std::string> cursors;         // .cur files, by name (as read)

    ~Skin();
    bool has(const std::wstring &sheet) const { return sheets.count(sheet) != 0; }
    // copies sheet pixels (sx, sy, w, h) to (dx, dy) on dc, scaled by s (nearest neighbour)
    bool blit(HDC dc, const std::wstring &sheet, int sx, int sy, int w, int h, int dx, int dy, int s) const;
    HCURSOR cursor(const std::wstring &name, int scale);

private:
    std::map<std::pair<std::wstring, int>, HCURSOR> made;
};

// zip archives (stored and deflated entries)
bool zip_read(const std::string &zip, std::map<std::wstring, std::string> &files);   // name (lower case, no folder) -> bytes
bool inflate_raw(const unsigned char *src, size_t n, std::string &out);

Skin *skin_own();                                        // Chordamp's own skin
Skin *skin_load(const std::wstring &wsz_path, std::wstring &error);
std::wstring skins_dir();
std::vector<std::wstring> skins_installed();
bool skin_export_own(const std::wstring &path);          // Chordamp's own skin written out as a .wsz
