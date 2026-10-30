#include "player.h"
#include <mfapi.h>
#include <propvarutil.h>

Player::Player(HWND notify) : hwnd(notify) { MFStartup(MF_VERSION, MFSTARTUP_FULL); }

Player::~Player() {
    if (mp) { mp->Shutdown(); mp->Release(); }
    MFShutdown();
}

STDMETHODIMP Player::QueryInterface(REFIID riid, void **ppv) {
    if (riid == IID_IUnknown || riid == __uuidof(IMFPMediaPlayerCallback)) {
        *ppv = static_cast<IMFPMediaPlayerCallback *>(this);
        AddRef();
        return S_OK;
    }
    *ppv = nullptr;
    return E_NOINTERFACE;
}

STDMETHODIMP_(ULONG) Player::Release() {
    ULONG r = InterlockedDecrement(&refs);
    return r;     // owned by the window; never deleted through COM
}

bool Player::ensure() {
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

bool Player::open(const std::wstring &url) {
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

void STDMETHODCALLTYPE Player::OnMediaPlayerEvent(MFP_EVENT_HEADER *ev) {
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

void Player::play() { if (mp && item_loaded) mp->Play(); }
void Player::pause() { if (mp && item_loaded) mp->Pause(); }
void Player::toggle() { playing() ? pause() : play(); }

void Player::stop() {
    if (!mp) return;
    mp->Stop();
    mp->ClearMediaItem();
    item_loaded = false;
    PostMessageW(hwnd, WM_CHORD_PLAYER, PE_STATE, 0);
}

void Player::seek(double secs) {
    if (!mp || !item_loaded) return;
    PROPVARIANT v;
    InitPropVariantFromInt64((LONGLONG)(secs * 10000000.0), &v);
    mp->SetPosition(MFP_POSITIONTYPE_100NS, &v);
    PropVariantClear(&v);
}

double Player::position() {
    if (!mp || !item_loaded) return 0;
    PROPVARIANT v;
    PropVariantInit(&v);
    double s = 0;
    if (SUCCEEDED(mp->GetPosition(MFP_POSITIONTYPE_100NS, &v))) s = v.uhVal.QuadPart / 10000000.0;
    PropVariantClear(&v);
    return s;
}

double Player::duration() {
    if (!mp || !item_loaded) return 0;
    PROPVARIANT v;
    PropVariantInit(&v);
    double s = 0;
    if (SUCCEEDED(mp->GetDuration(MFP_POSITIONTYPE_100NS, &v))) s = v.uhVal.QuadPart / 10000000.0;
    PropVariantClear(&v);
    return s;
}

void Player::set_volume(double v) {
    vol = std::max(0.0, std::min(1.0, v));
    if (mp) mp->SetVolume((float)(vol * vol));        // a curve that sounds even across the slider
}

bool Player::playing() {
    MFP_MEDIAPLAYER_STATE st = MFP_MEDIAPLAYER_STATE_EMPTY;
    return mp && item_loaded && SUCCEEDED(mp->GetState(&st)) && st == MFP_MEDIAPLAYER_STATE_PLAYING;
}

bool Player::paused() {
    MFP_MEDIAPLAYER_STATE st = MFP_MEDIAPLAYER_STATE_EMPTY;
    return mp && SUCCEEDED(mp->GetState(&st)) && st == MFP_MEDIAPLAYER_STATE_PAUSED;
}
