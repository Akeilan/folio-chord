#!/bin/sh
# Builds Folio Chord for Windows (FolioChord.exe) with the MinGW-w64 cross compiler from the
# Ubuntu archive, and the MSI with msitools (wixl).   sh windows/build.sh [out dir]
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$HERE/out}"
mkdir -p "$OUT"
VER="$(sed -n 's/^#define CHORD_VERSION L"\(.*\)"/\1/p' "$HERE/src/common.h")"
CXX=x86_64-w64-mingw32-g++-posix
x86_64-w64-mingw32-windres "$HERE/res/chord.rc" -O coff -o "$OUT/chord.res"
$CXX -std=c++17 -O2 -municode -mwindows -static -s -Wall -Wno-unknown-pragmas -Wno-missing-field-initializers \
  -DUNICODE -D_UNICODE -D_WIN32_WINNT=0x0A00 \
  "$HERE/src/main.cpp" "$HERE/src/library.cpp" "$HERE/src/player.cpp" "$HERE/src/online.cpp" "$OUT/chord.res" \
  -o "$OUT/FolioChord.exe" \
  -lcomctl32 -lcomdlg32 -lshell32 -lshlwapi -lole32 -loleaut32 -luuid -ldwmapi -lwinhttp -lxmllite -lpropsys \
  -lmfplay -lmfplat -lmfuuid -lgdi32 -lmsimg32 -luxtheme -luser32
sed "s/@VERSION@/$VER/g" "$HERE/msi/chord.wxs" > "$OUT/chord.wxs"
cp "$HERE/res/folio-chord.ico" "$OUT/folio-chord.ico"
(cd "$OUT" && wixl -a x64 -o "FolioChord-$VER-x64.msi" chord.wxs 2>&1 | grep -v CRITICAL || true)
ls -la "$OUT/FolioChord.exe" "$OUT/FolioChord-$VER-x64.msi"
