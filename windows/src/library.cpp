#include "library.h"
#include <propsys.h>
#include <propkey.h>
#include <propvarutil.h>
#include <ctime>

static const wchar_t *AUDIO[] = {L".mp3", L".m4a", L".m4b", L".aac", L".flac", L".wav", L".wma", L".aif", L".aiff",
                                 L".alac", L".ogg", L".opus", L".mp2", L".ac3", L".3gp"};

long long now_unix() { return (long long)time(nullptr); }

bool is_audio_file(const std::wstring &path) {
    size_t dot = path.find_last_of(L'.');
    if (dot == std::wstring::npos) return false;
    std::wstring ext = lower(path.substr(dot));
    for (auto e : AUDIO) if (ext == e) return true;
    return false;
}

static std::wstring prop_str(IPropertyStore *ps, REFPROPERTYKEY key) {
    PROPVARIANT v;
    PropVariantInit(&v);
    std::wstring out;
    if (SUCCEEDED(ps->GetValue(key, &v)) && v.vt != VT_EMPTY) {
        PWSTR s = nullptr;
        if (SUCCEEDED(PropVariantToStringAlloc(v, &s)) && s) { out = s; CoTaskMemFree(s); }
    }
    PropVariantClear(&v);
    return trim(out);
}

static unsigned long long prop_u64(IPropertyStore *ps, REFPROPERTYKEY key) {
    PROPVARIANT v;
    PropVariantInit(&v);
    unsigned long long out = 0;
    if (SUCCEEDED(ps->GetValue(key, &v)) && v.vt != VT_EMPTY) {
        ULONGLONG x = 0;
        if (SUCCEEDED(PropVariantToUInt64(v, &x))) out = x;
    }
    PropVariantClear(&v);
    return out;
}

bool read_tags(const std::wstring &path, Track &t) {
    IPropertyStore *ps = nullptr;
    HRESULT hr = SHGetPropertyStoreFromParsingName(path.c_str(), nullptr, GPS_DEFAULT, IID_PPV_ARGS(&ps));
    if (SUCCEEDED(hr) && ps) {
        t.title = prop_str(ps, PKEY_Title);
        t.artist = prop_str(ps, PKEY_Music_Artist);
        t.album = prop_str(ps, PKEY_Music_AlbumTitle);
        t.album_artist = prop_str(ps, PKEY_Music_AlbumArtist);
        t.genre = prop_str(ps, PKEY_Music_Genre);
        t.year = (int)prop_u64(ps, PKEY_Media_Year);
        t.track_no = (int)prop_u64(ps, PKEY_Music_TrackNumber);
        t.duration = prop_u64(ps, PKEY_Media_Duration) / 10000000.0;
        t.bitrate = (int)(prop_u64(ps, PKEY_Audio_EncodingBitrate) / 1000);
        ps->Release();
    }
    // a song without a title is named after its file
    if (t.title.empty()) {
        size_t s = path.find_last_of(L"\\/"), d = path.find_last_of(L'.');
        t.title = path.substr(s == std::wstring::npos ? 0 : s + 1,
                              d == std::wstring::npos || d < s ? std::wstring::npos : d - (s == std::wstring::npos ? 0 : s + 1));
    }
    // multiple artists come as "A; B"
    for (auto *f : {&t.artist, &t.album_artist, &t.genre}) {
        size_t semi = f->find(L"; ");
        if (semi != std::wstring::npos && f == &t.genre) *f = f->substr(0, semi);
    }
    return SUCCEEDED(hr);
}

// ---------------------------------------------------------------- storing
static const char *HEADER = "folio-chord-library\t1";

void Library::load() {
    std::lock_guard<std::recursive_mutex> g(lock);
    dir = data_dir();
    tracks.clear();
    playlists.clear();
    folders.clear();
    std::string data;
    if (read_file(dir + L"\\library.tsv", data)) {
        auto ls = lines_of(data);
        for (size_t i = 1; i < ls.size(); i++) {
            auto f = split(ls[i], L'\t');
            if (f.size() < 17) continue;
            Track t;
            t.id = _wtoi(f[0].c_str());
            t.path = tsv_unescape(f[1]);
            t.title = tsv_unescape(f[2]);
            t.artist = tsv_unescape(f[3]);
            t.album = tsv_unescape(f[4]);
            t.album_artist = tsv_unescape(f[5]);
            t.genre = tsv_unescape(f[6]);
            t.year = _wtoi(f[7].c_str());
            t.track_no = _wtoi(f[8].c_str());
            t.disc_no = _wtoi(f[9].c_str());
            t.bitrate = _wtoi(f[10].c_str());
            t.duration = _wtof(f[11].c_str());
            t.rating = _wtoi(f[12].c_str());
            t.plays = _wtoi(f[13].c_str());
            t.last_played = _wtoi64(f[14].c_str());
            t.added = _wtoi64(f[15].c_str());
            tracks.push_back(t);
            next_id = std::max(next_id, t.id + 1);
        }
    }
    if (read_file(dir + L"\\playlists.tsv", data)) {
        for (auto &l : lines_of(data)) {
            auto f = split(l, L'\t');
            if (f.size() >= 2 && f[0] == L"folder") { folders.push_back(tsv_unescape(f[1])); continue; }
            if (f.size() < 3 || f[0] != L"playlist") continue;
            Playlist p;
            p.id = _wtoi(f[1].c_str());
            p.name = tsv_unescape(f[2]);
            if (f.size() > 3)
                for (auto &x : split(f[3], L',')) if (!x.empty()) p.tracks.push_back(_wtoi(x.c_str()));
            playlists.push_back(p);
            next_pl = std::max(next_pl, p.id + 1);
        }
    }
}

void Library::save() {
    std::lock_guard<std::recursive_mutex> g(lock);
    std::wstring o = widen(HEADER) + L"\n";
    for (auto &t : tracks) {
        wchar_t num[64];
        swprintf(num, 64, L"%.3f", t.duration);
        o += std::to_wstring(t.id) + L"\t" + tsv_escape(t.path) + L"\t" + tsv_escape(t.title) + L"\t" +
             tsv_escape(t.artist) + L"\t" + tsv_escape(t.album) + L"\t" + tsv_escape(t.album_artist) + L"\t" +
             tsv_escape(t.genre) + L"\t" + std::to_wstring(t.year) + L"\t" + std::to_wstring(t.track_no) + L"\t" +
             std::to_wstring(t.disc_no) + L"\t" + std::to_wstring(t.bitrate) + L"\t" + num + L"\t" +
             std::to_wstring(t.rating) + L"\t" + std::to_wstring(t.plays) + L"\t" + std::to_wstring(t.last_played) +
             L"\t" + std::to_wstring(t.added) + L"\t\n";
    }
    write_file(dir + L"\\library.tsv", narrow(o));
    std::wstring p;
    for (auto &f : folders) p += L"folder\t" + tsv_escape(f) + L"\n";
    for (auto &pl : playlists) {
        p += L"playlist\t" + std::to_wstring(pl.id) + L"\t" + tsv_escape(pl.name) + L"\t";
        for (size_t i = 0; i < pl.tracks.size(); i++) p += (i ? L"," : L"") + std::to_wstring(pl.tracks[i]);
        p += L"\n";
    }
    write_file(dir + L"\\playlists.tsv", narrow(p));
}

Track *Library::find(int id) {
    for (auto &t : tracks) if (t.id == id) return &t;
    return nullptr;
}

Track *Library::find_path(const std::wstring &path) {
    std::wstring l = lower(path);
    for (auto &t : tracks) if (lower(t.path) == l) return &t;
    return nullptr;
}

int Library::add_file(const std::wstring &path) {
    if (!is_audio_file(path) || !file_exists(path)) return 0;
    Track t;
    read_tags(path, t);
    std::lock_guard<std::recursive_mutex> g(lock);
    if (Track *old = find_path(path)) {            // already there: refresh the tags, keep counts and ratings
        t.id = old->id;
        t.rating = old->rating;
        t.plays = old->plays;
        t.last_played = old->last_played;
        t.added = old->added;
        t.path = old->path;
        *old = t;
        return t.id;
    }
    t.path = path;
    t.id = next_id++;
    t.added = now_unix();
    tracks.push_back(t);
    return t.id;
}

std::vector<int> Library::add_folder(const std::wstring &root, std::function<void(int)> progress) {
    std::vector<int> ids;
    std::vector<std::wstring> todo = {root};
    {
        std::lock_guard<std::recursive_mutex> g(lock);
        if (std::find(folders.begin(), folders.end(), root) == folders.end()) folders.push_back(root);
    }
    while (!todo.empty()) {
        std::wstring d = todo.back();
        todo.pop_back();
        WIN32_FIND_DATAW fd;
        HANDLE h = FindFirstFileW((d + L"\\*").c_str(), &fd);
        if (h == INVALID_HANDLE_VALUE) continue;
        std::vector<std::wstring> files;
        do {
            std::wstring n = fd.cFileName;
            if (n == L"." || n == L"..") continue;
            if (fd.dwFileAttributes & FILE_ATTRIBUTE_HIDDEN) continue;
            if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) todo.push_back(d + L"\\" + n);
            else if (is_audio_file(n)) files.push_back(d + L"\\" + n);
        } while (FindNextFileW(h, &fd));
        FindClose(h);
        std::sort(files.begin(), files.end());
        for (auto &f : files) {
            int id = add_file(f);
            if (id) ids.push_back(id);
            if (progress && ids.size() % 25 == 0) progress((int)ids.size());
        }
    }
    return ids;
}

void Library::remove(const std::vector<int> &ids) {
    std::lock_guard<std::recursive_mutex> g(lock);
    tracks.erase(std::remove_if(tracks.begin(), tracks.end(),
                                [&](const Track &t) { return std::find(ids.begin(), ids.end(), t.id) != ids.end(); }),
                 tracks.end());
    for (auto &p : playlists)
        p.tracks.erase(std::remove_if(p.tracks.begin(), p.tracks.end(),
                                      [&](int x) { return std::find(ids.begin(), ids.end(), x) != ids.end(); }),
                       p.tracks.end());
}

void Library::played(int id) {
    std::lock_guard<std::recursive_mutex> g(lock);
    if (Track *t = find(id)) { t->plays++; t->last_played = now_unix(); }
}

Playlist *Library::playlist(int id) {
    for (auto &p : playlists) if (p.id == id) return &p;
    return nullptr;
}

int Library::new_playlist(const std::wstring &name) {
    std::lock_guard<std::recursive_mutex> g(lock);
    Playlist p;
    p.id = next_pl++;
    p.name = name;
    playlists.push_back(p);
    return p.id;
}

void Library::delete_playlist(int id) {
    std::lock_guard<std::recursive_mutex> g(lock);
    playlists.erase(std::remove_if(playlists.begin(), playlists.end(), [&](const Playlist &p) { return p.id == id; }),
                    playlists.end());
}
