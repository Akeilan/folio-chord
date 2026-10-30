#!/bin/sh
# Run a UI test script inside the installed Folio Chord: run_installed.sh /path/to/script.py
HERE="$(cd "$(dirname "$0")" && pwd)"
export FOLIO_TEST_SCRIPT="$1" XDG_CONFIG_HOME="$(mktemp -d)" XDG_CACHE_HOME="$(mktemp -d)" FOLIO_CHORD_DATA="$(mktemp -d)" FOLIO_TEST_DELAY=1500
export UI_OUT="${UI_OUT:-/tmp/ui_out_installed}" FOLIO_CHORD_NON_UNIQUE=1 FOLIO_CHORD_NO_SCAN=1 FOLIO_CHORD_NO_AUTOSYNC=1
export FOLIO_CHORD_RADIO_API=http://127.0.0.1:9 FOLIO_CHORD_APPLE_API=http://127.0.0.1:9 FOLIO_CHORD_PODCASTINDEX_API=http://127.0.0.1:9 FOLIO_CHORD_MUSICBRAINZ=http://127.0.0.1:9 FOLIO_CHORD_COVERART=http://127.0.0.1:9
export FOLIO_CHORD_AUDIOSINK=fakesink FOLIO_TESTS="$HERE" LANG="${LANG:-C.UTF-8}"
cd /
exec timeout ${UI_TIMEOUT:-400} /usr/bin/folio-chord
