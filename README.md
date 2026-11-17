# Folio Chord

A music player in the manner of the classic iTunes, for Zorin OS and Ubuntu: your music library,
internet radio and podcasts. Part of Folio Studio.

- **Library**: watches your music folders (MP3, AAC/M4A, Apple Lossless, FLAC, Ogg Vorbis, Opus,
  WAV, AIFF, WMA, WavPack, MP2 and Matroska audio), following songs that are renamed
  or moved and linked folders. The column browser (Genres, Artists, Albums), list, album list and grid views, search,
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
- **Home Sharing**: share your library with the other Folio Chords on your own network, under a
  name and an optional passcode, and play from theirs — their playlists included. No account, and
  nothing leaves your network. A shared library can be listened to, not changed.
- **Network speakers**: play to a UPnP/DLNA speaker or receiver on your own network. The speakers
  that answer are listed under the volume control; the song is served from this computer and the
  play, pause, seek and volume controls drive the speaker. "This computer" brings the sound back.
- **CDs**: import as AAC, Apple Lossless, MP3, FLAC or WAV with track names from MusicBrainz; burn
  a playlist to an audio or data CD (wodim). Album covers from the Cover Art Archive.

The Store, sign-in, Match and device sync aren't part of it; their menu items say so. Nothing is
sent anywhere except the requests to the directories above when you use them.

## What's new in 0.3.1

- Folio Chord is now under the MIT License, like the rest of Folio Studio.
- Monkey's Audio is left out.

## What's new in 0.3

- Menus can be read again when opened from the menu bar.
- Songs renamed or moved in Files keep their ratings, plays and playlists; a damaged library file
  is replaced by the copy kept each time Chord starts.
- Big libraries: ratings and plays redraw one row, and 40,000 songs show in about a second and a half.
- WMA, WavPack, MP2 and Matroska audio. Changing Matroska details needs mkvtoolnix.
- Up Next songs can be reordered and taken out.
- Remove Duplicate Items moves files to the Trash and offers exact duplicates first.
- Files, folders and playlists can be dragged in from Files; stations that drop out are tried
  again; passcodes go in the desktop's keyring.

## Running and testing

    cd app && python3 -m folio_chord
    python3 tests/test_engine.py; python3 tests/test_net.py        # engine, radio and podcasts
    python3 tests/test_sharing.py                                  # Home Sharing
    python3 tests/test_cast.py                                     # network speakers
    python3 tests/test_backlog8.py                                 # Backlog 8 (files, feeds, formats)
    sh tests/run_ui.sh ui_library.py                               # UI tests, on an X display
    sh tests/theme_run.sh                                          # desktop themes (X2-01)
    sh build-deb.sh out/                                           # the package
    XD=95 tools/release.sh                                         # everything, on the three test machines

Needs python3-gi, GTK 3, GStreamer (base, good, libav) and python3-mutagen.
