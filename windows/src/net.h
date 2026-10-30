// Fetching from the internet (WinHTTP, part of Windows): the radio and podcast directories, feeds.
#pragma once
#include "common.h"
#include <winhttp.h>

inline std::wstring url_encode(const std::wstring &s) {
    std::string u = narrow(s), o;
    const char *hex = "0123456789ABCDEF";
    for (unsigned char c : u) {
        if (isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') o += (char)c;
        else { o += '%'; o += hex[c >> 4]; o += hex[c & 15]; }
    }
    return widen(o);
}

// GET url; follows redirects; returns false (and err) on failure. Body is raw bytes.
inline bool http_get(const std::wstring &url, std::string &body, std::wstring *err = nullptr, int timeout_ms = 20000) {
    body.clear();
    URL_COMPONENTS uc = {};
    uc.dwStructSize = sizeof uc;
    wchar_t host[512] = {}, path[4096] = {};
    uc.lpszHostName = host;
    uc.dwHostNameLength = 512;
    uc.lpszUrlPath = path;
    uc.dwUrlPathLength = 4096;
    wchar_t extra[4096] = {};
    uc.lpszExtraInfo = extra;
    uc.dwExtraInfoLength = 4096;
    if (!WinHttpCrackUrl(url.c_str(), 0, 0, &uc)) {
        if (err) *err = L"not a web address";
        return false;
    }
    HINTERNET s = WinHttpOpen(L"FolioChord/" CHORD_VERSION, WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
                              WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!s) s = WinHttpOpen(L"FolioChord/" CHORD_VERSION, WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                            WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!s) { if (err) *err = L"the network isn't available"; return false; }
    WinHttpSetTimeouts(s, timeout_ms, timeout_ms, timeout_ms, timeout_ms);
    HINTERNET c = WinHttpConnect(s, host, uc.nPort, 0);
    std::wstring full = std::wstring(path) + extra;
    HINTERNET r = c ? WinHttpOpenRequest(c, L"GET", full.c_str(), nullptr, WINHTTP_NO_REFERER,
                                         WINHTTP_DEFAULT_ACCEPT_TYPES,
                                         uc.nScheme == INTERNET_SCHEME_HTTPS ? WINHTTP_FLAG_SECURE : 0) : nullptr;
    bool ok = false;
    if (r && WinHttpSendRequest(r, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0) &&
        WinHttpReceiveResponse(r, nullptr)) {
        DWORD status = 0, len = sizeof status;
        WinHttpQueryHeaders(r, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, nullptr, &status, &len, nullptr);
        for (;;) {
            DWORD avail = 0;
            if (!WinHttpQueryDataAvailable(r, &avail) || avail == 0) break;
            size_t at = body.size();
            body.resize(at + avail);
            DWORD got = 0;
            if (!WinHttpReadData(r, &body[at], avail, &got)) break;
            body.resize(at + got);
            if (body.size() > 64u * 1024 * 1024) break;
        }
        ok = status >= 200 && status < 300;
        if (!ok && err) *err = L"the server answered " + std::to_wstring(status);
    } else if (err) {
        *err = L"couldn't connect (error " + std::to_wstring(GetLastError()) + L")";
    }
    if (r) WinHttpCloseHandle(r);
    if (c) WinHttpCloseHandle(c);
    WinHttpCloseHandle(s);
    return ok;
}
