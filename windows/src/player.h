// Playing sound. Files, podcasts and most streams are decoded by Media Foundation's Source Reader into
// samples Folio Chord processes itself (the 10-band equalizer, preamp, balance and volume, and the
// spectrum and waveform Chordamp shows), then played through WASAPI. A stream the reader can't open
// falls back to Media Foundation's own player (MFPlay), without the equalizer.
#pragma once
#include "common.h"
#include <mfplay.h>
#include <atomic>
#include <mutex>
#include <thread>

enum PlayerEvent { PE_STARTED = 1, PE_ENDED, PE_ERROR, PE_STATE };

// ---- the plain Media Foundation player (fallback for streams)
class MfPlayer : public IMFPMediaPlayerCallback {
public:
    explicit MfPlayer(HWND notify);
    virtual ~MfPlayer();
    bool open(const std::wstring &url);
    void play();
    void pause();
    void toggle();
    void stop();
    void seek(double secs);
    double position();
    double duration();
    void set_volume(double v);
    bool playing();
    bool paused();
    bool active() { return item_loaded; }
    std::wstring last_error;

    STDMETHODIMP QueryInterface(REFIID riid, void **ppv) override;
    STDMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&refs); }
    STDMETHODIMP_(ULONG) Release() override;
    void STDMETHODCALLTYPE OnMediaPlayerEvent(MFP_EVENT_HEADER *ev) override;

private:
    HWND hwnd;
    IMFPMediaPlayer *mp = nullptr;
    LONG refs = 1;
    double vol = 0.8;
    bool item_loaded = false;
    bool ensure();
};

// ---- the equalizer: ten peaking filters and a preamp, per channel
struct Biquad {
    double b0 = 1, b1 = 0, b2 = 0, a1 = 0, a2 = 0;
    double z1[8] = {}, z2[8] = {};
};

extern const double EQ_FREQS[10];
struct EqPreset { const wchar_t *name; double preamp; double bands[10]; };
extern const EqPreset EQ_PRESETS[];
extern const int EQ_PRESET_COUNT;

// ---- the player Folio Chord uses
class Player {
public:
    explicit Player(HWND notify);
    ~Player();
    bool open(const std::wstring &url);      // starts playing when ready (PE_STARTED), PE_ERROR if it can't
    void play();
    void pause();
    void toggle();
    void stop();
    void seek(double secs);
    double position();
    double duration();
    void set_volume(double v);               // 0..1
    double volume() const { return vol; }
    bool playing();
    bool paused();
    bool active();
    std::wstring last_error;

    // sound shaping (C3-25, C3-31): the equalizer, its preamp, balance
    void set_eq(bool on, double preamp, const double bands[10]);
    bool eq_on() const { return eq_enabled; }
    void set_balance(double b);              // -1 left .. 1 right
    double balance() const { return bal; }

    // what Chordamp draws: the spectrum (dB, 0..half the sample rate) and the last stretch of sound (mono)
    bool spectrum(std::vector<float> &mags);
    bool scope(std::vector<short> &wave);
    int sample_rate() const { return src_rate ? src_rate : 44100; }
    int channels() const { return src_channels ? src_channels : 2; }
    bool processing() const { return !use_mf; }   // false while a stream plays through MFPlay

    bool output_ok() const { return have_output; } // a sound device was found (else it plays silently, in time)

private:
    HWND hwnd;
    MfPlayer *mf = nullptr;
    bool use_mf = false;
    double vol = 0.8, bal = 0.0;
    // decoding thread
    std::thread worker;
    std::mutex m;
    std::atomic<int> state{0};               // 0 stopped, 1 playing, 2 paused
    std::atomic<bool> quit{false};
    std::atomic<long long> seek_to{-1};      // 100 ns units, -1: none
    std::atomic<int> generation{0};
    double dur = 0;
    std::atomic<double> pos_secs{0};
    int src_rate = 0, src_channels = 0;
    bool have_output = true;
    // sound shaping
    bool eq_enabled = false;
    double eq_pre = 0, eq_bands[10] = {};
    // analysis
    std::vector<float> ring;                 // the last 2048 mono samples
    size_t ring_at = 0;
    bool fresh = false;

    HWND msg_wnd = nullptr;
    int eq_version = 0;

    void run(std::wstring url, int gen);
    void stop_worker();

public:
    void fallback(int gen, const std::wstring &url);   // on the window's thread
};
