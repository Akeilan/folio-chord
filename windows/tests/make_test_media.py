"""Test files for Folio Chord for Windows' self test: a music folder of tones (WAV) and testskin.wsz,
a classic skin with window shapes (region.txt), a pointer (.cur) and bitmap text (text.bmp).
   python3 make_test_media.py <folder> <Chordamp.wsz>"""
import math
import os
import struct
import sys
import wave
import zipfile

out, own = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
for i, (name, f) in enumerate((("Alpha Tone", 440), ("Bravo Tone", 660), ("Charlie Tone", 330), ("Delta Tone", 550))):
    with wave.open(os.path.join(out, "%02d %s.wav" % (i + 1, name)), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        frames = bytearray()
        for n in range(44100 * 12):
            v = int(12000 * math.sin(2 * math.pi * f * n / 44100) * (0.6 + 0.4 * math.sin(2 * math.pi * 3 * n / 44100)))
            frames += struct.pack("<hh", v, v)
        w.writeframes(bytes(frames))


def bmp24(w, h, rgb):
    row = bytes(rgb[::-1]) * w
    pad = (4 - len(row) % 4) % 4
    data = (row + b"\0" * pad) * h
    return b"BM" + struct.pack("<IHHI", 54 + len(data), 0, 0, 54) + struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(data), 2835, 2835, 0, 0) + data


def cur32():
    w = h = 32
    xor = b"".join(bytes((0, 0, 255, 255)) if (x + y) % 8 < 4 else bytes((255, 255, 255, 255)) for y in range(h) for x in range(w))
    and_mask = b"\0" * (4 * h)
    img = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(xor) + len(and_mask), 0, 0, 0, 0) + xor + and_mask
    return struct.pack("<HHH", 0, 2, 1) + struct.pack("<BBBBHHII", w, h, 0, 0, 3, 4, len(img), 22) + img


src = zipfile.ZipFile(own)
with zipfile.ZipFile(os.path.join(out, "testskin.wsz"), "w", zipfile.ZIP_DEFLATED) as z:
    for n in src.namelist():
        if n != "main.bmp":
            z.writestr("TestSkin/" + n, src.read(n))
    z.writestr("TestSkin/Main.bmp", bmp24(275, 116, (10, 70, 140)))
    z.writestr("TestSkin/text.bmp", bmp24(155, 18, (200, 200, 60)))
    z.writestr("TestSkin/region.txt", "[Normal]\nNumPoints=6\nPointList=0,2 2,0 273,0 275,2 275,116 0,116\n"
               "[WindowShade]\nNumPoints=4\nPointList=0,0 275,0 275,14 0,14\n")
    z.writestr("TestSkin/normal.cur", cur32())
print("made", sorted(os.listdir(out)))
