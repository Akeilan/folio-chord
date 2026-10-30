#!/bin/sh
# Run a UI test script inside Folio Chord on an X display (Xvfb): run_ui.sh script.py
HERE="$(cd "$(dirname "$0")" && pwd)"
export FOLIO_TEST_SCRIPT="$HERE/$1" FOLIO_CHORD_SHARE="${FOLIO_CHORD_SHARE:-$HERE/../share}"
export XDG_CONFIG_HOME="$(mktemp -d)" XDG_CACHE_HOME="$(mktemp -d)" FOLIO_CHORD_DATA="$(mktemp -d)" FOLIO_TEST_DELAY=1200
export UI_OUT="${UI_OUT:-/tmp/ui_out}" FOLIO_THEME="${FOLIO_THEME:-light}" FOLIO_CHORD_NON_UNIQUE=1 FOLIO_CHORD_NO_SCAN=1
export FOLIO_CHORD_RADIO_API=http://127.0.0.1:9 FOLIO_CHORD_APPLE_API=http://127.0.0.1:9 FOLIO_CHORD_PODCASTINDEX_API=http://127.0.0.1:9 FOLIO_CHORD_MUSICBRAINZ=http://127.0.0.1:9 FOLIO_CHORD_COVERART=http://127.0.0.1:9
export FOLIO_CHORD_NO_AUTOSYNC=1 FOLIO_CHORD_AUDIOSINK=fakesink FOLIO_TESTS="$HERE" LANG="${LANG:-C.UTF-8}"
cd "$HERE/../app"
exec timeout ${UI_TIMEOUT:-300} python3 -m folio_chord
