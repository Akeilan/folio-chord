#include "online.h"
#include "json.h"
#include "net.h"
#include <xmllite.h>
#include <shlwapi.h>
#include <ctime>

// ---------------------------------------------------------------- radio
static const wchar_t *RADIO_SERVERS[] = {L"https://de1.api.radio-browser.info", L"https://de2.api.radio-browser.info",
                                          L"https://fi1.api.radio-browser.info", L"https://at1.api.radio-browser.info"};

static std::wstring radio_base() {
    wchar_t env[512];
    if (GetEnvironmentVariableW(L"FOLIO_CHORD_RADIO_API", env, 512)) return env;
    return L"";
}

static bool radio_get(const std::wstring &path, Json &j, std::wstring &err) {
    std::wstring env = radio_base();
    std::vector<std::wstring> servers;
    if (!env.empty()) servers.push_back(env);
    else {
        int start = GetTickCount() % 4;           // spread the load over the directory's servers
        for (int i = 0; i < 4; i++) servers.push_back(RADIO_SERVERS[(start + i) % 4]);
    }
    for (auto &s : servers) {
        std::string body;
        if (http_get(s + path, body, &err) && JsonParser::parse(body, j)) return true;
    }
    if (err.empty()) err = L"the radio directory didn't answer";
    return false;
}

static void stations_from(const Json &j, std::vector<Station> &out) {
    for (size_t i = 0; i < j.size(); i++) {
        const Json &d = j[i];
        Station s;
        s.uuid = widen(d["stationuuid"].s());
        s.name = trim(widen(d["name"].s()));
        s.url = widen(d["url_resolved"].s());
        if (s.url.empty()) s.url = widen(d["url"].s());
        s.tags = widen(d["tags"].s());
        s.country = widen(d["country"].s());
        s.codec = widen(d["codec"].s());
        s.bitrate = (int)d["bitrate"].n();
        s.votes = (int)d["votes"].n();
        if (!s.name.empty() && !s.url.empty()) out.push_back(s);
    }
}

bool radio_top(std::vector<Station> &out, std::wstring &err) {
    Json j;
    if (!radio_get(L"/json/stations/topvote/100?hidebroken=true", j, err)) return false;
    stations_from(j, out);
    return true;
}

bool radio_search(const std::wstring &q, std::vector<Station> &out, std::wstring &err) {
    Json j;
    if (!radio_get(L"/json/stations/search?name=" + url_encode(q) + L"&order=votes&reverse=true&limit=100&hidebroken=true",
                   j, err))
        return false;
    stations_from(j, out);
    return true;
}

std::wstring radio_resolve(const std::wstring &url) {
    std::wstring l = lower(url);
    size_t q = l.find(L'?');
    std::wstring path = q == std::wstring::npos ? l : l.substr(0, q);
    auto ends = [&](const wchar_t *e) { size_t n = wcslen(e); return path.size() >= n && path.compare(path.size() - n, n, e) == 0; };
    if (!(ends(L".pls") || ends(L".m3u") || ends(L".asx"))) return url;
    std::string body;
    if (!http_get(url, body)) return url;
    for (auto &line : lines_of(body.substr(0, 200000))) {
        std::wstring x = trim(line);
        size_t eq = x.find(L'=');
        if (lower(x).rfind(L"file", 0) == 0 && eq != std::wstring::npos) x = trim(x.substr(eq + 1));
        size_t href = lower(x).find(L"href=\"");
        if (href != std::wstring::npos) {
            x = x.substr(href + 6);
            x = x.substr(0, x.find(L'"'));
        }
        if (x.rfind(L"http://", 0) == 0 || x.rfind(L"https://", 0) == 0) return x;
    }
    return url;
}

void radio_clicked(const Station &s) {
    if (s.uuid.empty()) return;
    Json j;
    std::wstring err;
    radio_get(L"/json/url/" + s.uuid, j, err);
}

// ---------------------------------------------------------------- podcasts
static std::wstring apple_base() {
    wchar_t env[512];
    if (GetEnvironmentVariableW(L"FOLIO_CHORD_APPLE_API", env, 512)) return env;
    return L"https://itunes.apple.com";
}

bool podcast_search(const std::wstring &q, std::vector<Show> &out, std::wstring &err) {
    std::string body;
    if (!http_get(apple_base() + L"/search?media=podcast&entity=podcast&limit=50&term=" + url_encode(q), body, &err))
        return false;
    Json j;
    if (!JsonParser::parse(body, j)) { err = L"the podcast directory's answer couldn't be read"; return false; }
    const Json &r = j["results"];
    for (size_t i = 0; i < r.size(); i++) {
        Show s;
        s.title = widen(r[i]["collectionName"].s());
        s.author = widen(r[i]["artistName"].s());
        s.feed = widen(r[i]["feedUrl"].s());
        s.artwork = widen(r[i]["artworkUrl600"].s());
        if (!s.feed.empty()) out.push_back(s);
    }
    return true;
}

static double parse_duration(const std::wstring &d) {
    // "3600", "59:30" or "1:02:03"
    double total = 0;
    for (auto &part : split(trim(d), L':')) total = total * 60 + _wtof(part.c_str());
    return total;
}

static long long parse_rfc822(const std::wstring &s) {
    // "Mon, 07 Sep 2026 10:00:00 +0000": day, month name, year, time
    static const wchar_t *M[] = {L"jan", L"feb", L"mar", L"apr", L"may", L"jun", L"jul", L"aug", L"sep", L"oct", L"nov", L"dec"};
    int day = 0, year = 0, hh = 0, mm = 0, ss = 0, mon = -1;
    wchar_t mname[16] = {};
    std::wstring x = s;
    size_t comma = x.find(L',');
    if (comma != std::wstring::npos) x = x.substr(comma + 1);
    if (swscanf(x.c_str(), L" %d %15ls %d %d:%d:%d", &day, mname, &year, &hh, &mm, &ss) < 3) return 0;
    std::wstring mn = lower(mname).substr(0, 3);
    for (int i = 0; i < 12; i++) if (mn == M[i]) mon = i;
    if (mon < 0) return 0;
    struct tm t = {};
    t.tm_year = year - 1900;
    t.tm_mon = mon;
    t.tm_mday = day;
    t.tm_hour = hh;
    t.tm_min = mm;
    t.tm_sec = ss;
    return (long long)_mkgmtime(&t);
}

bool podcast_fetch(const std::wstring &feed, Show &show, std::vector<Episode> &eps, std::wstring &err) {
    std::string body;
    if (!http_get(feed, body, &err, 30000)) return false;
    show.feed = feed;
    return podcast_parse(body, show, eps, err);
}

bool podcast_parse(const std::string &body, Show &show, std::vector<Episode> &eps, std::wstring &err) {
    IStream *st = SHCreateMemStream((const BYTE *)body.data(), (UINT)body.size());
    IXmlReader *xr = nullptr;
    if (!st || FAILED(CreateXmlReader(__uuidof(IXmlReader), (void **)&xr, nullptr))) {
        if (st) st->Release();
        err = L"the feed couldn't be read";
        return false;
    }
    xr->SetProperty(XmlReaderProperty_DtdProcessing, DtdProcessing_Prohibit);
    xr->SetInput(st);
    std::vector<std::wstring> stack;
    Episode cur;
    bool in_item = false;
    std::wstring text;
    XmlNodeType nt;
    while (xr->Read(&nt) == S_OK) {
        if (nt == XmlNodeType_Element) {
            const wchar_t *local = nullptr, *prefix = nullptr;
            xr->GetLocalName(&local, nullptr);
            xr->GetPrefix(&prefix, nullptr);
            std::wstring name = local ? local : L"";
            std::wstring pre = prefix ? prefix : L"";
            BOOL empty = xr->IsEmptyElement();
            if (name == L"item") { in_item = true; cur = Episode(); }
            if (in_item && name == L"enclosure") {
                if (xr->MoveToAttributeByName(L"url", nullptr) == S_OK) {
                    const wchar_t *v = nullptr;
                    xr->GetValue(&v, nullptr);
                    if (v) cur.url = v;
                }
                xr->MoveToElement();
            }
            if (!in_item && pre == L"itunes" && name == L"image" && show.artwork.empty()) {
                if (xr->MoveToAttributeByName(L"href", nullptr) == S_OK) {
                    const wchar_t *v = nullptr;
                    xr->GetValue(&v, nullptr);
                    if (v) show.artwork = v;
                }
                xr->MoveToElement();
            }
            if (!empty) stack.push_back(pre.empty() ? name : pre + L":" + name);
            text.clear();
        } else if (nt == XmlNodeType_Text || nt == XmlNodeType_CDATA) {
            const wchar_t *v = nullptr;
            xr->GetValue(&v, nullptr);
            if (v) text += v;
        } else if (nt == XmlNodeType_EndElement) {
            std::wstring name = stack.empty() ? L"" : stack.back();
            if (!stack.empty()) stack.pop_back();
            std::wstring t = trim(text);
            if (in_item) {
                if (name == L"title") cur.title = t;
                else if (name == L"guid") cur.guid = t;
                else if (name == L"pubDate") { cur.date = t; cur.published = parse_rfc822(t); }
                else if (name == L"itunes:duration") cur.duration = parse_duration(t);
                else if (name == L"item") {
                    in_item = false;
                    if (!cur.url.empty()) {
                        if (cur.guid.empty()) cur.guid = cur.url;
                        eps.push_back(cur);
                    }
                }
            } else if (stack.size() == 2 && name == L"title" && show.title.empty()) show.title = t;
            else if (stack.size() == 2 && name == L"itunes:author" && show.author.empty()) show.author = t;
            text.clear();
        }
    }
    xr->Release();
    st->Release();
    if (show.title.empty() && eps.empty()) { err = L"that isn't a podcast feed"; return false; }
    return true;
}

// ---------------------------------------------------------------- what you keep
static std::wstring station_line(const wchar_t *kind, const Station &s) {
    return std::wstring(kind) + L"\t" + tsv_escape(s.uuid) + L"\t" + tsv_escape(s.name) + L"\t" + tsv_escape(s.url) + L"\t" +
           tsv_escape(s.tags) + L"\t" + tsv_escape(s.country) + L"\t" + tsv_escape(s.codec) + L"\t" +
           std::to_wstring(s.bitrate) + L"\n";
}

void OnlineStore::load() {
    favourites.clear();
    recent.clear();
    shows.clear();
    episodes.clear();
    std::string data;
    if (!read_file(data_dir() + L"\\online.tsv", data)) return;
    for (auto &l : lines_of(data)) {
        auto f = split(l, L'\t');
        if ((f[0] == L"fav" || f[0] == L"recent") && f.size() >= 8) {
            Station s;
            s.uuid = tsv_unescape(f[1]);
            s.name = tsv_unescape(f[2]);
            s.url = tsv_unescape(f[3]);
            s.tags = tsv_unescape(f[4]);
            s.country = tsv_unescape(f[5]);
            s.codec = tsv_unescape(f[6]);
            s.bitrate = _wtoi(f[7].c_str());
            (f[0] == L"fav" ? favourites : recent).push_back(s);
        } else if (f[0] == L"show" && f.size() >= 6) {
            Show s;
            s.id = _wtoi(f[1].c_str());
            s.title = tsv_unescape(f[2]);
            s.author = tsv_unescape(f[3]);
            s.feed = tsv_unescape(f[4]);
            s.artwork = tsv_unescape(f[5]);
            shows.push_back(s);
            next_show = std::max(next_show, s.id + 1);
        } else if (f[0] == L"ep" && f.size() >= 10) {
            Episode e;
            e.show = _wtoi(f[1].c_str());
            e.guid = tsv_unescape(f[2]);
            e.title = tsv_unescape(f[3]);
            e.url = tsv_unescape(f[4]);
            e.date = tsv_unescape(f[5]);
            e.duration = _wtof(f[6].c_str());
            e.position = _wtof(f[7].c_str());
            e.played = f[8] == L"1";
            e.published = _wtoi64(f[9].c_str());
            episodes.push_back(e);
        }
    }
}

void OnlineStore::save() {
    std::wstring o;
    for (auto &s : favourites) o += station_line(L"fav", s);
    for (auto &s : recent) o += station_line(L"recent", s);
    for (auto &s : shows)
        o += L"show\t" + std::to_wstring(s.id) + L"\t" + tsv_escape(s.title) + L"\t" + tsv_escape(s.author) + L"\t" +
             tsv_escape(s.feed) + L"\t" + tsv_escape(s.artwork) + L"\n";
    for (auto &e : episodes) {
        wchar_t d[64], p[64];
        swprintf(d, 64, L"%.1f", e.duration);
        swprintf(p, 64, L"%.1f", e.position);
        o += L"ep\t" + std::to_wstring(e.show) + L"\t" + tsv_escape(e.guid) + L"\t" + tsv_escape(e.title) + L"\t" +
             tsv_escape(e.url) + L"\t" + tsv_escape(e.date) + L"\t" + d + L"\t" + p + L"\t" + (e.played ? L"1" : L"0") +
             L"\t" + std::to_wstring(e.published) + L"\n";
    }
    write_file(data_dir() + L"\\online.tsv", narrow(o));
}

bool OnlineStore::is_favourite(const std::wstring &uuid) {
    for (auto &s : favourites) if (s.uuid == uuid) return true;
    return false;
}

void OnlineStore::set_favourite(const Station &s, bool on) {
    favourites.erase(std::remove_if(favourites.begin(), favourites.end(), [&](const Station &x) { return x.uuid == s.uuid; }),
                     favourites.end());
    if (on) favourites.push_back(s);
    save();
}

void OnlineStore::played_station(const Station &s) {
    recent.erase(std::remove_if(recent.begin(), recent.end(), [&](const Station &x) { return x.uuid == s.uuid; }), recent.end());
    recent.insert(recent.begin(), s);
    if (recent.size() > 30) recent.resize(30);
    save();
}

int OnlineStore::subscribe(const Show &s, const std::vector<Episode> &eps) {
    for (auto &x : shows)
        if (x.feed == s.feed) { merge(x.id, eps); return x.id; }
    Show n = s;
    n.id = next_show++;
    shows.push_back(n);
    merge(n.id, eps);
    save();
    return n.id;
}

int OnlineStore::merge(int show, const std::vector<Episode> &eps) {
    int added = 0;
    for (auto e : eps) {
        bool have = false;
        for (auto &x : episodes)
            if (x.show == show && x.guid == e.guid) { x.title = e.title; x.url = e.url; have = true; break; }
        if (!have) { e.show = show; episodes.push_back(e); added++; }
    }
    save();
    return added;
}

void OnlineStore::unsubscribe(int show) {
    shows.erase(std::remove_if(shows.begin(), shows.end(), [&](const Show &s) { return s.id == show; }), shows.end());
    episodes.erase(std::remove_if(episodes.begin(), episodes.end(), [&](const Episode &e) { return e.show == show; }),
                   episodes.end());
    save();
}

Show *OnlineStore::show(int id) {
    for (auto &s : shows) if (s.id == id) return &s;
    return nullptr;
}

std::vector<Episode *> OnlineStore::episodes_of(int show) {
    std::vector<Episode *> out;
    for (auto &e : episodes) if (e.show == show) out.push_back(&e);
    std::sort(out.begin(), out.end(), [](Episode *a, Episode *b) { return a->published > b->published; });
    return out;
}
