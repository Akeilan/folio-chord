// Internet radio (radio-browser.info, as on Linux) and podcasts (Apple's public directory + the
// shows' own feeds). Fetching runs off the window's thread; the results are plain data.
#pragma once
#include "common.h"

struct Station {
    std::wstring uuid, name, url, tags, country, codec;
    int bitrate = 0, votes = 0;
};

struct Show {
    int id = 0;
    std::wstring title, author, feed, artwork;
};

struct Episode {
    int show = 0;
    std::wstring guid, title, url, date;
    double duration = 0, position = 0;
    bool played = false;
    long long published = 0;
};

// radio
bool radio_top(std::vector<Station> &out, std::wstring &err);
bool radio_search(const std::wstring &q, std::vector<Station> &out, std::wstring &err);
std::wstring radio_resolve(const std::wstring &url);   // a .pls / .m3u station gives its first stream
void radio_clicked(const Station &s);                  // tells the directory, as its rules ask

// podcasts
bool podcast_search(const std::wstring &q, std::vector<Show> &out, std::wstring &err);
bool podcast_fetch(const std::wstring &feed, Show &show, std::vector<Episode> &eps, std::wstring &err);
bool podcast_parse(const std::string &rss, Show &show, std::vector<Episode> &eps, std::wstring &err);

// what you keep: favourite stations, shows and their episodes (%APPDATA%\Folio Chord)
struct OnlineStore {
    std::vector<Station> favourites, recent;
    std::vector<Show> shows;
    std::vector<Episode> episodes;
    void load();
    void save();
    bool is_favourite(const std::wstring &uuid);
    void set_favourite(const Station &s, bool on);
    void played_station(const Station &s);
    int subscribe(const Show &s, const std::vector<Episode> &eps);   // returns the show id
    int merge(int show, const std::vector<Episode> &eps);            // new episodes added
    void unsubscribe(int show);
    Show *show(int id);
    std::vector<Episode *> episodes_of(int show);
private:
    int next_show = 1;
};
