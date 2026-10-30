"""Test songs: short tones in every format Folio Chord reads, made with GStreamer and tagged with
mutagen.  make(dir) -> {name: path}"""
import os

FORMATS = {
    "flac": "flacenc",
    "mp3": "lamemp3enc target=bitrate bitrate=128 cbr=true ! id3v2mux",
    "ogg": "vorbisenc ! oggmux",
    "opus": "opusenc ! oggmux",
    "m4a": "avenc_aac ! mp4mux",
    "wav": "wavenc",
}


def tone(path, secs=2.0, freq=440, rate=44100):
    import gi
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    Gst.init(None)
    enc = FORMATS[os.path.splitext(path)[1][1:]]
    if path.endswith(".opus"):
        rate = 48000
    n = int(secs * rate / 1024) + 1
    pipe = Gst.parse_launch("audiotestsrc num-buffers=%d samplesperbuffer=1024 freq=%d wave=sine volume=0.3 ! "
                            "audio/x-raw,rate=%d,channels=2 ! audioconvert ! %s ! filesink name=out"
                            % (n, freq, rate, enc))
    pipe.get_by_name("out").set_property("location", path)
    pipe.set_state(Gst.State.PLAYING)
    msg = pipe.get_bus().timed_pop_filtered(30 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
    pipe.set_state(Gst.State.NULL)
    if msg is None or msg.type == Gst.MessageType.ERROR:
        raise RuntimeError("couldn't make %s: %s" % (path, msg.parse_error()[0].message if msg else "timeout"))


def make(d, secs=2.0):
    os.makedirs(d, exist_ok=True)
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
    from folio_chord import tags
    songs = [
        ("Blue Train", "Coltrane Quartet", "Night Sessions", "Jazz", 1957, 1, 4, "flac", 440),
        ("Moment's Notice", "Coltrane Quartet", "Night Sessions", "Jazz", 1957, 2, 4, "mp3", 494),
        ("Locomotion", "Coltrane Quartet", "Night Sessions", "Jazz", 1957, 3, 4, "ogg", 523),
        ("Lazy Bird", "Coltrane Quartet", "Night Sessions", "Jazz", 1957, 4, 4, "m4a", 587),
        ("Teen Spirit Cover", "The Garage", "Loud Nineties", "Rock", 1994, 1, 2, "opus", 330),
        ("Grunge Waltz", "The Garage", "Loud Nineties", "Rock", 1996, 2, 2, "wav", 349),
        ("Sonata in C", "Hall Ensemble", "Chamber Works", "Classical", 1985, 1, 1, "flac", 262),
    ]
    out = {}
    for title, artist, album, genre, year, tn, tc, ext, freq in songs:
        sub = os.path.join(d, artist, album)
        os.makedirs(sub, exist_ok=True)
        p = os.path.join(sub, "%02d %s.%s" % (tn, title.replace("'", ""), ext))
        tone(p, secs, freq)
        tags.write(p, {"title": title, "artist": artist, "album": album, "genre": genre, "year": year,
                       "track_no": tn, "track_count": tc})
        out[title] = p
    return out


if __name__ == "__main__":
    import sys
    print(make(sys.argv[1]))
