#include "player.h"

// ---- MfPlayer: the plain Media Foundation player, kept for streams the decoder below can't open
#include <mfapi.h>
#include <propvarutil.h>

MfPlayer::MfPlayer(HWND notify) : hwnd(notify) {}

MfPlayer::~MfPlayer() {
    if (mp) { mp->Shutdown(); mp->Release(); }
}

STDMETHODIMP MfPlayer::QueryInterface(REFIID riid, void **ppv) {
    if (riid == IID_IUnknown || riid == __uuidof(IMFPMediaPlayerCallback)) {
        *ppv = static_cast<IMFPMediaPlayerCallback *>(this);
        AddRef();
        return S_OK;
    }
    *ppv = nullptr;
    return E_NOINTERFACE;
}

STDMETHODIMP_(ULONG) MfPlayer::Release() {
    ULONG r = InterlockedDecrement(&refs);
    return r;     // owned by the window; never deleted through COM
}

bool MfPlayer::ensure() {
    if (mp) return true;
    HRESULT hr = MFPCreateMediaPlayer(nullptr, FALSE, MFP_OPTION_NONE, this, nullptr, &mp);
    if (FAILED(hr)) {
        wchar_t b[64];
        swprintf(b, 64, L"Media Foundation couldn't start (0x%08lX)", (unsigned long)hr);
        last_error = b;
        return false;
    }
    mp->SetVolume((float)(vol * vol));
    return true;
}

bool MfPlayer::open(const std::wstring &url) {
    if (!ensure()) return false;
    item_loaded = false;
    mp->Stop();
    mp->ClearMediaItem();
    HRESULT hr = mp->CreateMediaItemFromURL(url.c_str(), FALSE, 0, nullptr);   // async: MEDIAITEM_CREATED follows
    if (FAILED(hr)) {
        wchar_t b[64];
        swprintf(b, 64, L"couldn't be opened (0x%08lX)", (unsigned long)hr);
        last_error = b;
        return false;
    }
    return true;
}

static std::wstring hr_text(HRESULT hr) {
    switch (hr) {
        case (HRESULT)0xC00D36C4: return L"this kind of file isn't supported by Windows";
        case (HRESULT)0xC00D36B4: return L"the file's format isn't supported";
        case (HRESULT)0x80070002: return L"the file is missing";
        case (HRESULT)0x80072EE7: case (HRESULT)0x80072EFD: return L"the station couldn't be reached";
        default: {
            wchar_t b[64];
            swprintf(b, 64, L"error 0x%08lX", (unsigned long)hr);
            return b;
        }
    }
}

void STDMETHODCALLTYPE MfPlayer::OnMediaPlayerEvent(MFP_EVENT_HEADER *ev) {
    if (!ev) return;
    if (FAILED(ev->hrEvent)) {
        last_error = hr_text(ev->hrEvent);
        item_loaded = false;
        PostMessageW(hwnd, WM_CHORD_PLAYER, PE_ERROR, 0);
        return;
    }
    switch (ev->eEventType) {
        case MFP_EVENT_TYPE_MEDIAITEM_CREATED: {
            auto *e = MFP_GET_MEDIAITEM_CREATED_EVENT(ev);
            if (e && e->pMediaItem) mp->SetMediaItem(e->pMediaItem);
            break;
        }
        case MFP_EVENT_TYPE_MEDIAITEM_SET:
            item_loaded = true;
            mp->SetVolume((float)(vol * vol));
            mp->Play();
            PostMessageW(hwnd, WM_CHORD_PLAYER, PE_STARTED, 0);
            break;
        case MFP_EVENT_TYPE_PLAYBACK_ENDED:
            PostMessageW(hwnd, WM_CHORD_PLAYER, PE_ENDED, 0);
            break;
        case MFP_EVENT_TYPE_PLAY:
        case MFP_EVENT_TYPE_PAUSE:
        case MFP_EVENT_TYPE_STOP:
            PostMessageW(hwnd, WM_CHORD_PLAYER, PE_STATE, 0);
            break;
        default:
            break;
    }
}

void MfPlayer::play() { if (mp && item_loaded) mp->Play(); }
void MfPlayer::pause() { if (mp && item_loaded) mp->Pause(); }
void MfPlayer::toggle() { playing() ? pause() : play(); }

void MfPlayer::stop() {
    if (!mp) return;
    mp->Stop();
    mp->ClearMediaItem();
    item_loaded = false;
    PostMessageW(hwnd, WM_CHORD_PLAYER, PE_STATE, 0);
}

void MfPlayer::seek(double secs) {
    if (!mp || !item_loaded) return;
    PROPVARIANT v;
    InitPropVariantFromInt64((LONGLONG)(secs * 10000000.0), &v);
    mp->SetPosition(MFP_POSITIONTYPE_100NS, &v);
    PropVariantClear(&v);
}

double MfPlayer::position() {
    if (!mp || !item_loaded) return 0;
    PROPVARIANT v;
    PropVariantInit(&v);
    double s = 0;
    if (SUCCEEDED(mp->GetPosition(MFP_POSITIONTYPE_100NS, &v))) s = v.uhVal.QuadPart / 10000000.0;
    PropVariantClear(&v);
    return s;
}

double MfPlayer::duration() {
    if (!mp || !item_loaded) return 0;
    PROPVARIANT v;
    PropVariantInit(&v);
    double s = 0;
    if (SUCCEEDED(mp->GetDuration(MFP_POSITIONTYPE_100NS, &v))) s = v.uhVal.QuadPart / 10000000.0;
    PropVariantClear(&v);
    return s;
}

void MfPlayer::set_volume(double v) {
    vol = std::max(0.0, std::min(1.0, v));
    if (mp) mp->SetVolume((float)(vol * vol));        // a curve that sounds even across the slider
}

bool MfPlayer::playing() {
    MFP_MEDIAPLAYER_STATE st = MFP_MEDIAPLAYER_STATE_EMPTY;
    return mp && item_loaded && SUCCEEDED(mp->GetState(&st)) && st == MFP_MEDIAPLAYER_STATE_PLAYING;
}

bool MfPlayer::paused() {
    MFP_MEDIAPLAYER_STATE st = MFP_MEDIAPLAYER_STATE_EMPTY;
    return mp && SUCCEEDED(mp->GetState(&st)) && st == MFP_MEDIAPLAYER_STATE_PAUSED;
}

// =====================================================================================================
// ---- Player: Source Reader -> Folio Chord's own sound shaping -> WASAPI
#include <mfidl.h>
#include <mfreadwrite.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <cmath>
#include <complex>

static const double PI = 3.14159265358979323846;

const double EQ_FREQS[10] = {32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000};
// the same presets as Folio Chord on Linux: preamp, then the ten bands in dB
const EqPreset EQ_PRESETS[] = {
    {L"Acoustic", 0, {5, 4.9, 4, 1, 1.5, 1.5, 3.5, 4, 3.5, 2}},
    {L"Bass Booster", 0, {5.5, 4.3, 3.5, 2.5, 1.3, 0, 0, 0, 0, 0}},
    {L"Bass Reducer", 0, {-5.5, -4.3, -3.5, -2.5, -1.3, 0, 0, 0, 0, 0}},
    {L"Classical", 0, {4.8, 3.8, 3, 2.5, -1.5, -1.5, 0, 2.3, 3.3, 3.8}},
    {L"Dance", 0, {3.6, 6.6, 5, 0, 2, 3.5, 5, 4.5, 3.5, 0}},
    {L"Deep", 0, {5, 3.5, 1.8, 1, 3, 2.5, 1.5, -2, -3.5, -4.5}},
    {L"Electronic", 0, {4.3, 3.8, 1.3, 0, -2, 2.3, 1, 1.3, 4, 4.8}},
    {L"Flat", 0, {0, 0, 0, 0, 0, 0, 0, 0, 0, 0}},
    {L"Hip-Hop", 0, {5, 4.3, 1.5, 3, -1, -1, 1.5, -0.5, 2, 3}},
    {L"Jazz", 0, {4, 3, 1.5, 2.3, -1.5, -1.5, 0, 1.5, 3, 3.8}},
    {L"Latin", 0, {4.5, 3, 0, 0, -1.5, -1.5, -1.5, 0, 3, 4.5}},
    {L"Loudness", 0, {6, 4, 0, 0, -2, 0, -1, -5, 5, 1}},
    {L"Lounge", 0, {-3, -1.5, -0.5, 1.5, 4, 2.5, 0, -1.5, 2, 1}},
    {L"Piano", 0, {3, 2, 0, 2.5, 3, 1.5, 3.5, 4.5, 3, 3.5}},
    {L"Pop", 0, {-1.5, -1, 0, 2, 4, 4, 2, 0, -1, -1.5}},
    {L"R&B", 0, {2.6, 7, 5.7, 1.3, -2.2, -1.5, 2.3, 2.7, 3, 3.8}},
    {L"Rock", 0, {5, 4, 3, 1.5, -0.5, -1, 0.5, 2.5, 3.5, 4.5}},
    {L"Small Speakers", 0, {5.5, 4.3, 3.5, 2.5, 1.3, 0, -1.3, -2.5, -3.5, -4.3}},
    {L"Spoken Word", 0, {-3.5, -0.5, 0, 0.7, 3.5, 4.6, 4.8, 4.3, 2.5, 0}},
    {L"Treble Booster", 0, {0, 0, 0, 0, 0, 1.3, 2.5, 3.5, 4.3, 5.5}},
    {L"Treble Reducer", 0, {0, 0, 0, 0, 0, -1.3, -2.5, -3.5, -4.3, -5.5}},
    {L"Vocal Booster", 0, {-1.5, -3, -3, 1.5, 3.5, 3.5, 3, 1.5, 0, -1.5}},
};
const int EQ_PRESET_COUNT = sizeof EQ_PRESETS / sizeof EQ_PRESETS[0];

// internal: a stream the reader couldn't open goes to MFPlay, on the window's thread
static const UINT WM_PLAYER_FALLBACK = WM_APP + 40;
static std::atomic<int> g_workers{0};

static LRESULT CALLBACK player_msg_proc(HWND h, UINT m, WPARAM w, LPARAM l) {
    if (m == WM_PLAYER_FALLBACK) {
        auto *p = (Player *)GetWindowLongPtrW(h, GWLP_USERDATA);
        auto *url = (std::wstring *)l;
        if (p) p->fallback((int)w, *url);
        delete url;
        return 0;
    }
    return DefWindowProcW(h, m, w, l);
}

Player::Player(HWND notify) : hwnd(notify) {
    MFStartup(MF_VERSION, MFSTARTUP_FULL);
    mf = new MfPlayer(notify);
    WNDCLASSW wc{};
    wc.lpfnWndProc = player_msg_proc;
    wc.hInstance = GetModuleHandleW(nullptr);
    wc.lpszClassName = L"FolioChordPlayerMsg";
    RegisterClassW(&wc);
    msg_wnd = CreateWindowW(L"FolioChordPlayerMsg", L"", 0, 0, 0, 0, 0, HWND_MESSAGE, nullptr, wc.hInstance, nullptr);
    SetWindowLongPtrW(msg_wnd, GWLP_USERDATA, (LONG_PTR)this);
    ring.assign(2048, 0.0f);
}

Player::~Player() {
    stop_worker();
    for (int i = 0; i < 300 && g_workers.load() > 0; i++) Sleep(10);     // let a decoding thread let go
    if (msg_wnd) DestroyWindow(msg_wnd);
    delete mf;
    MFShutdown();
}

void Player::stop_worker() {
    generation++;                  // the running thread sees it isn't wanted any more and ends
    state = 0;
}

bool Player::open(const std::wstring &url) {
    stop_worker();
    if (use_mf) mf->stop();
    use_mf = false;
    last_error.clear();
    dur = 0;
    pos_secs = 0;
    seek_to = -1;
    {
        std::lock_guard<std::mutex> g(m);
        std::fill(ring.begin(), ring.end(), 0.0f);
        fresh = false;
    }
    state = 1;
    int gen = generation.load();
    std::thread(&Player::run, this, url, gen).detach();
    return true;
}

void Player::fallback(int gen, const std::wstring &url) {
    if (gen != generation.load()) return;
    use_mf = true;
    state = 0;
    mf->set_volume(vol);
    if (!mf->open(url)) {
        last_error = mf->last_error;
        PostMessageW(hwnd, WM_CHORD_PLAYER, PE_ERROR, 0);
    }
}

void Player::play() {
    if (use_mf) { mf->play(); return; }
    if (state == 2) { state = 1; PostMessageW(hwnd, WM_CHORD_PLAYER, PE_STATE, 0); }
}

void Player::pause() {
    if (use_mf) { mf->pause(); return; }
    if (state == 1) { state = 2; PostMessageW(hwnd, WM_CHORD_PLAYER, PE_STATE, 0); }
}

void Player::toggle() { playing() ? pause() : play(); }

void Player::stop() {
    if (use_mf) { mf->stop(); use_mf = false; }
    stop_worker();
    pos_secs = 0;
    PostMessageW(hwnd, WM_CHORD_PLAYER, PE_STATE, 0);
}

void Player::seek(double secs) {
    if (use_mf) { mf->seek(secs); return; }
    if (state == 0) return;
    secs = std::max(0.0, secs);
    seek_to = (long long)(secs * 10000000.0);
    pos_secs = secs;
}

double Player::position() { return use_mf ? mf->position() : pos_secs.load(); }
double Player::duration() { return use_mf ? mf->duration() : dur; }
bool Player::playing() { return use_mf ? mf->playing() : state == 1; }
bool Player::paused() { return use_mf ? mf->paused() : state == 2; }
bool Player::active() { return use_mf ? mf->active() : state != 0; }

void Player::set_volume(double v) {
    vol = std::max(0.0, std::min(1.0, v));
    mf->set_volume(vol);
}

void Player::set_balance(double b) { bal = std::max(-1.0, std::min(1.0, b)); }

void Player::set_eq(bool on, double preamp, const double bands[10]) {
    std::lock_guard<std::mutex> g(m);
    eq_enabled = on;
    eq_pre = preamp;
    for (int i = 0; i < 10; i++) eq_bands[i] = bands[i];
    eq_version++;
}

// ---- the filters: peaking EQ (one octave wide) at each band
static void peaking(Biquad &f, double freq, double gain_db, double rate) {
    freq = std::min(freq, rate * 0.45);
    double A = std::pow(10.0, gain_db / 40.0);
    double w0 = 2 * PI * freq / rate, alpha = std::sin(w0) / (2 * 1.41);
    double cw = std::cos(w0);
    double a0 = 1 + alpha / A;
    f.b0 = (1 + alpha * A) / a0;
    f.b1 = (-2 * cw) / a0;
    f.b2 = (1 - alpha * A) / a0;
    f.a1 = (-2 * cw) / a0;
    f.a2 = (1 - alpha / A) / a0;
}

// ---- the analysis Chordamp draws
bool Player::scope(std::vector<short> &wave) {
    std::lock_guard<std::mutex> g(m);
    if (!fresh || state != 1) return false;
    wave.resize(512);
    size_t n = ring.size();
    for (size_t i = 0; i < 512; i++) {
        float v = ring[(ring_at + n - 512 + i) % n];
        wave[i] = (short)std::max(-32767.0f, std::min(32767.0f, v * 32767.0f));
    }
    return true;
}

static void fft(std::vector<std::complex<double>> &a) {
    size_t n = a.size();
    for (size_t i = 1, j = 0; i < n; i++) {
        size_t bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) std::swap(a[i], a[j]);
    }
    for (size_t len = 2; len <= n; len <<= 1) {
        double ang = -2 * PI / len;
        std::complex<double> wl(std::cos(ang), std::sin(ang));
        for (size_t i = 0; i < n; i += len) {
            std::complex<double> w(1);
            for (size_t k = 0; k < len / 2; k++) {
                auto u = a[i + k], v = a[i + k + len / 2] * w;
                a[i + k] = u + v;
                a[i + k + len / 2] = u - v;
                w *= wl;
            }
        }
    }
}

bool Player::spectrum(std::vector<float> &mags) {
    std::vector<std::complex<double>> a(1024);
    {
        std::lock_guard<std::mutex> g(m);
        if (!fresh || state != 1) return false;
        size_t n = ring.size();
        for (size_t i = 0; i < 1024; i++) {
            double hann = 0.5 - 0.5 * std::cos(2 * PI * i / 1023.0);
            a[i] = ring[(ring_at + n - 1024 + i) % n] * hann;
        }
    }
    fft(a);
    mags.resize(512);
    for (int i = 0; i < 512; i++) {
        double mag = std::abs(a[i]) / 256.0;
        mags[i] = (float)(20.0 * std::log10(std::max(mag, 1e-6)));
    }
    return true;
}

// ---- the decoding thread
struct ComInit {
    ComInit() { CoInitializeEx(nullptr, COINIT_MULTITHREADED); }
    ~ComInit() { CoUninitialize(); }
};
template <class T> static void release(T *&p) { if (p) { p->Release(); p = nullptr; } }

void Player::run(std::wstring url, int gen) {
    g_workers++;
    ComInit com;
    auto alive = [&] { return gen == generation.load(); };
    IMFSourceReader *reader = nullptr;
    IMFMediaType *want = nullptr, *got = nullptr;
    IMMDeviceEnumerator *en = nullptr;
    IMMDevice *dev = nullptr;
    IAudioClient *ac = nullptr;
    IAudioRenderClient *rc = nullptr;
    WAVEFORMATEX *mix = nullptr;
    UINT32 rate = 0, ch = 0, out_rate = 48000, out_ch = 2, buf_frames = 0;
    bool ok = SUCCEEDED(MFCreateSourceReaderFromURL(url.c_str(), nullptr, &reader));
    if (ok) {
        reader->SetStreamSelection((DWORD)MF_SOURCE_READER_ALL_STREAMS, FALSE);
        ok = SUCCEEDED(reader->SetStreamSelection((DWORD)MF_SOURCE_READER_FIRST_AUDIO_STREAM, TRUE));
    }
    if (ok) {
        IMFMediaType *native = nullptr;
        if (SUCCEEDED(reader->GetNativeMediaType((DWORD)MF_SOURCE_READER_FIRST_AUDIO_STREAM, 0, &native))) {
            native->GetUINT32(MF_MT_AUDIO_SAMPLES_PER_SECOND, &rate);
            native->GetUINT32(MF_MT_AUDIO_NUM_CHANNELS, &ch);
            native->Release();
        }
        if (!rate) rate = 44100;
        if (!ch) ch = 2;
        MFCreateMediaType(&want);
        want->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Audio);
        want->SetGUID(MF_MT_SUBTYPE, MFAudioFormat_Float);
        want->SetUINT32(MF_MT_AUDIO_NUM_CHANNELS, ch);
        want->SetUINT32(MF_MT_AUDIO_SAMPLES_PER_SECOND, rate);
        want->SetUINT32(MF_MT_AUDIO_BITS_PER_SAMPLE, 32);
        want->SetUINT32(MF_MT_AUDIO_BLOCK_ALIGNMENT, ch * 4);
        want->SetUINT32(MF_MT_AUDIO_AVG_BYTES_PER_SECOND, rate * ch * 4);
        ok = SUCCEEDED(reader->SetCurrentMediaType((DWORD)MF_SOURCE_READER_FIRST_AUDIO_STREAM, nullptr, want));
        if (ok && SUCCEEDED(reader->GetCurrentMediaType((DWORD)MF_SOURCE_READER_FIRST_AUDIO_STREAM, &got))) {
            got->GetUINT32(MF_MT_AUDIO_SAMPLES_PER_SECOND, &rate);
            got->GetUINT32(MF_MT_AUDIO_NUM_CHANNELS, &ch);
        }
    }
    if (!ok) {
        release(want); release(got); release(reader);
        if (alive()) PostMessageW(msg_wnd, WM_PLAYER_FALLBACK, gen, (LPARAM) new std::wstring(url));
        g_workers--;
        return;
    }
    PROPVARIANT pv;
    PropVariantInit(&pv);
    if (SUCCEEDED(reader->GetPresentationAttribute((DWORD)MF_SOURCE_READER_MEDIASOURCE, MF_PD_DURATION, &pv)) && pv.vt == VT_UI8)
        dur = pv.uhVal.QuadPart / 10000000.0;
    PropVariantClear(&pv);
    src_rate = (int)rate;
    src_channels = (int)ch;
    // the sound device (none: play in time, silently)
    have_output = false;
    if (SUCCEEDED(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), (void **)&en)) &&
        SUCCEEDED(en->GetDefaultAudioEndpoint(eRender, eConsole, &dev)) &&
        SUCCEEDED(dev->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, (void **)&ac)) &&
        SUCCEEDED(ac->GetMixFormat(&mix))) {
        // ask for 32-bit float at the device's rate; the conversion from the file's rate is done here
        WAVEFORMATEXTENSIBLE fmt{};
        fmt.Format.wFormatTag = WAVE_FORMAT_EXTENSIBLE;
        fmt.Format.nChannels = mix->nChannels;
        fmt.Format.nSamplesPerSec = mix->nSamplesPerSec;
        fmt.Format.wBitsPerSample = 32;
        fmt.Format.nBlockAlign = mix->nChannels * 4;
        fmt.Format.nAvgBytesPerSec = mix->nSamplesPerSec * fmt.Format.nBlockAlign;
        fmt.Format.cbSize = 22;
        fmt.Samples.wValidBitsPerSample = 32;
        fmt.dwChannelMask = mix->nChannels == 1 ? SPEAKER_FRONT_CENTER : (SPEAKER_FRONT_LEFT | SPEAKER_FRONT_RIGHT);
        fmt.SubFormat = KSDATAFORMAT_SUBTYPE_IEEE_FLOAT;
        if (SUCCEEDED(ac->Initialize(AUDCLNT_SHAREMODE_SHARED, 0, 2000000, 0, (WAVEFORMATEX *)&fmt, nullptr)) &&
            SUCCEEDED(ac->GetBufferSize(&buf_frames)) &&
            SUCCEEDED(ac->GetService(__uuidof(IAudioRenderClient), (void **)&rc))) {
            out_rate = mix->nSamplesPerSec;
            out_ch = mix->nChannels;
            have_output = true;
        }
    }
    if (!have_output) {
        release(rc); release(ac);
        out_rate = rate;
        out_ch = 2;
        buf_frames = out_rate / 5;
    }
    if (alive()) PostMessageW(hwnd, WM_CHORD_PLAYER, PE_STARTED, 0);

    // processing state (this thread's own)
    Biquad f[10];
    int eq_ver = -1;
    bool eq_on = false;
    double pre = 1.0;
    std::vector<float> pending;          // processed frames at the file's rate, interleaved (ch)
    size_t pend_at = 0;
    double phase = 0.0;                  // resampler position between two source frames
    double step = (double)rate / out_rate;
    long long written = 0;               // output frames handed to the device since the last seek
    double base = 0.0;                   // the time playback (re)started from
    bool eos = false, started = false;
    LARGE_INTEGER qpf, t0;
    QueryPerformanceFrequency(&qpf);
    QueryPerformanceCounter(&t0);
    double paced = 0.0;                  // without a device: output frames "played" so far
    int last_state = 1;

    auto pull = [&]() -> bool {          // decode one more chunk into pending; false at the end
        DWORD flags = 0;
        IMFSample *sample = nullptr;
        if (FAILED(reader->ReadSample((DWORD)MF_SOURCE_READER_FIRST_AUDIO_STREAM, 0, nullptr, &flags, nullptr, &sample))) return false;
        if (flags & MF_SOURCE_READERF_ENDOFSTREAM) { release(sample); return false; }
        if (!sample) return true;
        IMFMediaBuffer *mb = nullptr;
        if (SUCCEEDED(sample->ConvertToContiguousBuffer(&mb))) {
            BYTE *data = nullptr;
            DWORD len = 0;
            if (SUCCEEDED(mb->Lock(&data, nullptr, &len))) {
                int frames = (int)(len / (ch * 4));
                size_t keep = pending.size() - pend_at;
                std::vector<float> nb(keep + (size_t)frames * ch);
                std::copy(pending.begin() + pend_at, pending.end(), nb.begin());
                memcpy(nb.data() + keep, data, (size_t)frames * ch * 4);
                mb->Unlock();
                // sound shaping
                {
                    std::lock_guard<std::mutex> g(m);
                    if (eq_ver != eq_version) {
                        eq_ver = eq_version;
                        eq_on = eq_enabled;
                        pre = std::pow(10.0, (eq_enabled ? eq_pre : 0.0) / 20.0);
                        for (int b = 0; b < 10; b++) {
                            double z1[8], z2[8];
                            memcpy(z1, f[b].z1, sizeof z1);
                            memcpy(z2, f[b].z2, sizeof z2);
                            peaking(f[b], EQ_FREQS[b], eq_enabled ? eq_bands[b] : 0.0, rate);
                            memcpy(f[b].z1, z1, sizeof z1);
                            memcpy(f[b].z2, z2, sizeof z2);
                        }
                    }
                }
                float *p = nb.data() + keep;
                double bl = bal, gl = bl > 0 ? 1 - bl : 1, gr = bl < 0 ? 1 + bl : 1;
                for (int i = 0; i < frames; i++) {
                    double mono = 0;
                    for (UINT32 c = 0; c < ch; c++) {
                        double x = p[i * ch + c] * pre;
                        if (eq_on) {
                            int cc = (int)std::min<UINT32>(c, 7);
                            for (int b = 0; b < 10; b++) {
                                Biquad &q = f[b];
                                double y = q.b0 * x + q.z1[cc];
                                q.z1[cc] = q.b1 * x - q.a1 * y + q.z2[cc];
                                q.z2[cc] = q.b2 * x - q.a2 * y;
                                x = y;
                            }
                        }
                        mono += x;
                        if (ch >= 2) x *= (c == 0 ? gl : (c == 1 ? gr : 1.0));
                        p[i * ch + c] = (float)x;
                    }
                    mono /= ch;
                    std::lock_guard<std::mutex> g(m);
                    ring[ring_at] = (float)mono;
                    ring_at = (ring_at + 1) % ring.size();
                }
                {
                    std::lock_guard<std::mutex> g(m);
                    fresh = true;
                }
                pending.swap(nb);
                pend_at = 0;
            }
            mb->Release();
        }
        sample->Release();
        return true;
    };

    while (alive()) {
        // seeking
        long long st = seek_to.exchange(-1);
        if (st >= 0) {
            PROPVARIANT v;
            PropVariantInit(&v);
            v.vt = VT_I8;
            v.hVal.QuadPart = st;
            reader->SetCurrentPosition(GUID_NULL, v);
            pending.clear();
            pend_at = 0;
            phase = 0;
            eos = false;
            base = st / 10000000.0;
            written = 0;
            paced = 0;
            QueryPerformanceCounter(&t0);
            if (have_output) { ac->Stop(); ac->Reset(); started = false; }
        }
        int s = state.load();
        if (s != last_state) {
            if (have_output && started) { if (s == 2) ac->Stop(); else if (s == 1) ac->Start(); }
            if (s == 1 && !have_output) {          // the silent clock carries on from where it stopped
                QueryPerformanceCounter(&t0);
                t0.QuadPart -= (LONGLONG)(paced / out_rate * qpf.QuadPart);
            }
            last_state = s;
        }
        if (s != 1) { Sleep(15); continue; }
        // how much room the device has
        UINT32 room = 0;
        double played_frames;
        if (have_output) {
            UINT32 padding = 0;
            ac->GetCurrentPadding(&padding);
            room = buf_frames - padding;
            played_frames = (double)(written - padding);
        } else {
            LARGE_INTEGER now;
            QueryPerformanceCounter(&now);
            double t = (double)(now.QuadPart - t0.QuadPart) / qpf.QuadPart;
            paced = t * out_rate;
            played_frames = std::min(paced, (double)written);
            room = (UINT32)std::max(0.0, paced + buf_frames - written);
        }
        pos_secs = base + std::max(0.0, played_frames) / out_rate;
        if (eos) {
            if (played_frames >= written - 1) {
                if (alive()) {
                    state = 0;
                    PostMessageW(hwnd, WM_CHORD_PLAYER, PE_ENDED, 0);
                }
                break;
            }
            Sleep(10);
            continue;
        }
        if (room < 256) { Sleep(8); continue; }
        // fill: convert from the file's rate and channels to the device's
        std::vector<float> out((size_t)room * out_ch, 0.0f);
        UINT32 made = 0;
        double v = vol * vol;
        while (made < room) {
            size_t avail = (pending.size() - pend_at) / ch;
            if (avail < 2) {
                if (!pull()) { eos = true; break; }
                continue;
            }
            const float *a = pending.data() + pend_at;
            const float *b = a + ch;
            for (UINT32 c = 0; c < out_ch; c++) {
                UINT32 sc = ch == 1 ? 0 : std::min(c, ch - 1);
                if (c >= 2 && ch <= 2) { out[made * out_ch + c] = 0; continue; }
                double x = a[sc] + (b[sc] - a[sc]) * phase;
                out[made * out_ch + c] = (float)std::max(-1.0, std::min(1.0, x * v));
            }
            made++;
            phase += step;
            while (phase >= 1.0 && (pending.size() - pend_at) / ch >= 2) { phase -= 1.0; pend_at += ch; }
            if (phase >= 1.0) { phase -= 1.0; pend_at += ch; }
        }
        if (made && have_output) {
            BYTE *dst = nullptr;
            if (SUCCEEDED(rc->GetBuffer(made, &dst))) {
                memcpy(dst, out.data(), (size_t)made * out_ch * 4);
                rc->ReleaseBuffer(made, 0);
                written += made;
            }
            if (!started) { ac->Start(); started = true; }
        } else if (made) {
            written += made;
        }
    }
    if (ac) ac->Stop();
    release(rc); release(ac); release(dev); release(en);
    if (mix) CoTaskMemFree(mix);
    release(want); release(got); release(reader);
    g_workers--;
}
