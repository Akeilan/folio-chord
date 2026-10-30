# Folio Chord

A music player in the manner of the classic iTunes, for Zorin OS and Ubuntu: your music library,
internet radio and podcasts. Part of Folio Studio.

- **Library**: watches your music folders (MP3, AAC/M4A, Apple Lossless, FLAC, Ogg Vorbis, Opus,
  WAV, AIFF). The column browser (Genres, Artists, Albums), list, album list and grid views, search,
  ratings, play counts, Get Info (tags and artwork written into the files).
- **Playlists**: playlists and folders, Smart Playlists with rules, limits and live updating
  (iTunes' own six to start with), M3U import and export.
- **Playback**: gapless, crossfade, Sound Check (ReplayGain), the 10-band equalizer with iTunes'
  presets, shuffle by songs or albums, repeat, Up Next, the status display, Mini Player,
  visualizer, media keys and the desktop's player controls (MPRIS).
- **Internet radio**: the community directory radio-browser.info (the one MusicPod uses): most
  popular, by genre, country and language, search, favourites, the song playing on the station.
- **Podcasts**: Apple's public podcast directory (no sign-in; search, and the charts by country and
  category), or Podcast Index with your own free API key. Subscriptions, automatic downloads,
  played marks, resume, show notes, OPML import and export.
- **CDs**: import as AAC, Apple Lossless, MP3, FLAC or WAV with track names from MusicBrainz; burn
  a playlist to an audio or data CD (wodim). Album covers from the Cover Art Archive.

The Store, sign-in, Match and device sync aren't part of it; their menu items say so. Nothing is
sent anywhere except the requests to the directories above when you use them.

## Running and testing

    cd app && python3 -m folio_chord
    python3 tests/test_engine.py; python3 tests/test_net.py        # engine, radio and podcasts
    sh tests/run_ui.sh ui_library.py                               # UI tests, on an X display
    sh tests/theme_run.sh                                          # desktop themes (X2-01)
    sh build-deb.sh out/                                           # the package
    XD=95 tools/release.sh                                         # everything, on the three test machines

Needs python3-gi, GTK 3, GStreamer (base, good, libav) and python3-mutagen.
