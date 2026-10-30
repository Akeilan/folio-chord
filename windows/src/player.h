// Playing sound through Windows' Media Foundation (MFPlay): files on disk, internet radio, podcasts.
#pragma once
#include "common.h"
#include <mfplay.h>

enum PlayerEvent { PE_STARTED = 1, PE_ENDED, PE_ERROR, PE_STATE };

class Player : public IMFPMediaPlayerCallback {
public:
    explicit Player(HWND notify);
    virtual ~Player();
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
    bool active() { return item_loaded; }
    std::wstring last_error;

    // IUnknown / IMFPMediaPlayerCallback
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
