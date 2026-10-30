# Folio Chord for Windows

Chord written natively for Windows: C++ and Win32, Media Foundation for sound, WinHTTP and XmlLite
for radio and podcasts, the Windows property system for tags. One small program, nothing else to
install. The Linux version (`app/`) remains the reference for features; see the backlog (N3-xx).

    sh windows/build.sh [out dir]      # FolioChord.exe and FolioChord-<version>-x64.msi

Needs the MinGW-w64 cross compiler and msitools from the Ubuntu archive
(`g++-mingw-w64-x86-64-posix`, `msitools`).

Checks: `FolioChord.exe --selftest <report.txt> <music folder>` runs the library, feed and window
checks and saves pictures of the window next to the report (the release runs it under Wine).

## 0.4.0

- Chordamp: View > Look: Chordamp (Ctrl+Shift+W). The classic small player, equalizer and playlist editor, docking and
  snapping together, with Chordamp's own skin built in and classic .wsz skins (shapes, pointers, bitmap text) loaded
  from the options menu. Shade, Double Size, Always on Top, spectrum and oscilloscope, Jump to File, the library window.
- A new sound engine: Media Foundation decodes, Folio Chord shapes the sound (10-band equalizer with presets, preamp,
  balance) and plays it through WASAPI. Window > Equalizer in the Standard look.
