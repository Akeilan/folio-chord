// Folio Chord for Windows: shared helpers (strings, paths, files).
#pragma once
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <shlobj.h>
#include <string>
#include <vector>
#include <map>
#include <functional>
#include <algorithm>
#include <cstdint>

#define CHORD_VERSION L"0.3.0"

// window messages the background work posts back to the window
#define WM_CHORD_PLAYER   (WM_APP + 1)   // wParam: player event
#define WM_CHORD_TASK     (WM_APP + 2)   // lParam: Task* finished in the background

inline std::wstring widen(const std::string &s) {
    if (s.empty()) return L"";
    int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), nullptr, 0);
    std::wstring w(n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), &w[0], n);
    return w;
}

inline std::string narrow(const std::wstring &w) {
    if (w.empty()) return "";
    int n = WideCharToMultiByte(CP_UTF8, 0, w.data(), (int)w.size(), nullptr, 0, nullptr, nullptr);
    std::string s(n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, w.data(), (int)w.size(), &s[0], n, nullptr, nullptr);
    return s;
}

inline std::wstring lower(std::wstring s) {
    CharLowerBuffW(&s[0], (DWORD)s.size());
    return s;
}

inline std::wstring trim(const std::wstring &s) {
    size_t a = s.find_first_not_of(L" \t\r\n"), b = s.find_last_not_of(L" \t\r\n");
    return a == std::wstring::npos ? L"" : s.substr(a, b - a + 1);
}

inline std::wstring fmt_time(double secs) {
    if (secs < 0) secs = 0;
    long t = (long)(secs + 0.5);
    wchar_t buf[32];
    if (t >= 3600) swprintf(buf, 32, L"%ld:%02ld:%02ld", t / 3600, (t / 60) % 60, t % 60);
    else swprintf(buf, 32, L"%ld:%02ld", t / 60, t % 60);
    return buf;
}

// %APPDATA%\Folio Chord (FOLIO_CHORD_DATA overrides, for tests)
inline std::wstring data_dir() {
    wchar_t env[MAX_PATH];
    std::wstring d;
    if (GetEnvironmentVariableW(L"FOLIO_CHORD_DATA", env, MAX_PATH)) d = env;
    else {
        PWSTR p = nullptr;
        if (SUCCEEDED(SHGetKnownFolderPath(FOLDERID_RoamingAppData, 0, nullptr, &p))) { d = p; CoTaskMemFree(p); }
        d += L"\\Folio Chord";
    }
    SHCreateDirectoryExW(nullptr, d.c_str(), nullptr);
    return d;
}

inline std::wstring known_folder(REFKNOWNFOLDERID id) {
    PWSTR p = nullptr;
    std::wstring d;
    if (SUCCEEDED(SHGetKnownFolderPath(id, 0, nullptr, &p))) { d = p; CoTaskMemFree(p); }
    return d;
}

inline bool read_file(const std::wstring &path, std::string &out) {
    HANDLE h = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, 0, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;
    LARGE_INTEGER sz;
    GetFileSizeEx(h, &sz);
    out.resize((size_t)sz.QuadPart);
    DWORD got = 0;
    BOOL ok = out.empty() || ReadFile(h, &out[0], (DWORD)out.size(), &got, nullptr);
    CloseHandle(h);
    return ok && got == out.size();
}

// written to a temporary file and moved into place, so a crash never leaves half a file
inline bool write_file(const std::wstring &path, const std::string &data) {
    std::wstring tmp = path + L".tmp";
    HANDLE h = CreateFileW(tmp.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, 0, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;
    DWORD put = 0;
    BOOL ok = data.empty() || WriteFile(h, data.data(), (DWORD)data.size(), &put, nullptr);
    CloseHandle(h);
    if (!ok) return false;
    return MoveFileExW(tmp.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING) != 0;
}

inline bool file_exists(const std::wstring &p) {
    DWORD a = GetFileAttributesW(p.c_str());
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

// tab-separated records: tabs, newlines and backslashes escaped
inline std::wstring tsv_escape(const std::wstring &s) {
    std::wstring o;
    for (wchar_t c : s) {
        if (c == L'\\') o += L"\\\\";
        else if (c == L'\t') o += L"\\t";
        else if (c == L'\n') o += L"\\n";
        else if (c == L'\r') o += L"\\r";
        else o += c;
    }
    return o;
}

inline std::wstring tsv_unescape(const std::wstring &s) {
    std::wstring o;
    for (size_t i = 0; i < s.size(); i++) {
        if (s[i] == L'\\' && i + 1 < s.size()) {
            wchar_t c = s[++i];
            o += c == L't' ? L'\t' : c == L'n' ? L'\n' : c == L'r' ? L'\r' : c;
        } else o += s[i];
    }
    return o;
}

inline std::vector<std::wstring> split(const std::wstring &s, wchar_t sep) {
    std::vector<std::wstring> out;
    size_t a = 0;
    for (;;) {
        size_t b = s.find(sep, a);
        out.push_back(s.substr(a, b == std::wstring::npos ? std::wstring::npos : b - a));
        if (b == std::wstring::npos) break;
        a = b + 1;
    }
    return out;
}

inline std::vector<std::wstring> lines_of(const std::string &utf8) {
    std::vector<std::wstring> out;
    for (auto &l : split(widen(utf8), L'\n')) {
        std::wstring x = l;
        if (!x.empty() && x.back() == L'\r') x.pop_back();
        if (!x.empty()) out.push_back(x);
    }
    return out;
}
