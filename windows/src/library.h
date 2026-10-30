// The music library: songs, play counts, ratings and playlists, kept in %APPDATA%\Folio Chord.
#pragma once
#include "common.h"
#include <mutex>

struct Track {
    int id = 0;
    std::wstring path, title, artist, album, album_artist, genre;
    int year = 0, track_no = 0, disc_no = 0, bitrate = 0;   // bit rate in kbps
    double duration = 0;                                    // seconds
    int rating = 0, plays = 0;                              // rating 0..100 (20 a star)
    long long last_played = 0, added = 0;                   // Unix seconds
};

struct Playlist {
    int id = 0;
    std::wstring name;
    std::vector<int> tracks;
};

bool is_audio_file(const std::wstring &path);
bool read_tags(const std::wstring &path, Track &t);      // through the Windows property system

class Library {
public:
    std::vector<Track> tracks;
    std::vector<Playlist> playlists;
    std::vector<std::wstring> folders;                  // folders added (checked again on request)
    std::recursive_mutex lock;

    void load();
    void save();
    Track *find(int id);
    Track *find_path(const std::wstring &path);
    // adds (or refreshes) a file; returns its id, 0 if it isn't music
    int add_file(const std::wstring &path);
    // every music file under a folder; progress(n) is called from this thread
    std::vector<int> add_folder(const std::wstring &dir, std::function<void(int)> progress = nullptr);
    void remove(const std::vector<int> &ids);
    void played(int id);
    Playlist *playlist(int id);
    int new_playlist(const std::wstring &name);
    void delete_playlist(int id);

private:
    int next_id = 1, next_pl = 1;
    std::wstring dir;
};

long long now_unix();
