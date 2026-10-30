"""Makes Folio Chord's icons: symbolic (one-colour, recoloured by the app's own CSS) 16x16
action icons and the app icon. python3 tools/mkicons.py"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "share", "icons", "hicolor", "scalable", "actions")

P = {
    "play": "M4 2.5v11l9-5.5z",
    "pause": "M3.5 2.5h3v11h-3zM9.5 2.5h3v11h-3z",
    "stop": "M3.5 3.5h9v9h-9z",
    "prev": "M2.5 3h2v10h-2zM14 3v10L8.5 8zM8.5 3v10L3 8z",
    "next": "M11.5 3h2v10h-2zM2 3v10l5.5-5zM7.5 3v10L13 8z",
    "shuffle": "M1 4h3l6 8h2v-2l3 2.5-3 2.5v-2H9.4l-6-8H1zM1 12h3l1.6-2.1 1 1.3L5 14H1zM9.4 4H12V2l3 2.5L12 7V5h-2l-1.6 2.1-1-1.3z",
    "repeat": "M3 5h8V3l3 3-3 3V7H4v2H2V6a1 1 0 0 1 1-1zM13 11H5v2l-3-3 3-3v2h7V7h2v3a1 1 0 0 1-1 1z",
    "repeat-one": "M3 5h8V3l3 3-3 3V7H4v2H2V6a1 1 0 0 1 1-1zM13 11H5v2l-3-3 3-3v2h7V7h2v3a1 1 0 0 1-1 1zM7.2 6.2h1.6v3.6H7.2z",
    "add": "M7 2h2v5h5v2H9v5H7V9H2V7h5z",
    "volume-low": "M2 6h3l4-3.5v11L5 10H2z",
    "volume-high": "M1 6h3l4-3.5v11L4 10H1zM10 5.3a3.5 3.5 0 0 1 0 5.4l-.9-1a2.2 2.2 0 0 0 0-3.4zM11.8 3.3a6 6 0 0 1 0 9.4l-.9-1a4.7 4.7 0 0 0 0-7.4z",
    "view-list": "M2 3h12v2H2zM2 7h12v2H2zM2 11h12v2H2z",
    "view-albums": "M1 2h5v5H1zM8 3h7v1.5H8zM8 5.5h5v1.5H8zM1 9h5v5H1zM8 10h7v1.5H8zM8 12.5h5V14H8z",
    "view-grid": "M1.5 1.5h5.5v5.5H1.5zM9 1.5h5.5v5.5H9zM1.5 9h5.5v5.5H1.5zM9 9h5.5v5.5H9z",
    "browser": "M1 2h14v12H1zM2.5 3.5v9h3v-9zM6.5 3.5v9h3v-9zM10.5 3.5v9h3v-9z",
    "music": "M6 2.5l8-1.5v9.5a2 2 0 1 1-1.5-1.9V4.2L7.5 5.2v7.3A2 2 0 1 1 6 10.6z",
    "podcast": "M8 1a5.5 5.5 0 0 0-2.6 10.3l.4-1.5a4 4 0 1 1 4.4 0l.4 1.5A5.5 5.5 0 0 0 8 1zM8 4.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM7 9.5h2l.6 5.5H6.4z",
    "radio": "M1 6l11-4 .5 1.4L6 6h8a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1zM5 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM9.5 8.5h4v1h-4zM9.5 10.5h4v1h-4z",
    "playlist": "M1 3h9v1.6H1zM1 6.5h9v1.6H1zM1 10h5v1.6H1zM11 4l4 .6v1.5l-2.5-.4v5.8A1.8 1.8 0 1 1 11 9.8z",
    "smart": "M7 1h2l.3 1.7 1.3.6 1.4-1 1.4 1.4-1 1.4.6 1.3L15 7v2l-1.7.3-.6 1.3 1 1.4-1.4 1.4-1.4-1-1.3.6L9 15H7l-.3-1.7-1.3-.6-1.4 1-1.4-1.4 1-1.4-.6-1.3L1 9V7l1.7-.3.6-1.3-1-1.4 1.4-1.4 1.4 1 1.3-.6zM8 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z",
    "folder": "M1 3h5l1.5 1.5H15V13H1z",
    "cd": "M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm0 5a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm0 1.2a.8.8 0 1 0 0 1.6.8.8 0 0 0 0-1.6z",
    "eject": "M8 2l6 7H2zM2 11h12v2.5H2z",
    "heart": "M8 14S1 9.6 1 5.3A3.3 3.3 0 0 1 8 3.6a3.3 3.3 0 0 1 7 1.7C15 9.6 8 14 8 14zm0-2s5.5-3.6 5.5-6.7a1.8 1.8 0 0 0-3.6-.4L8 6.6 6.1 4.9a1.8 1.8 0 0 0-3.6.4C2.5 8.4 8 12 8 12z",
    "heart-filled": "M8 14S1 9.6 1 5.3A3.3 3.3 0 0 1 8 3.6a3.3 3.3 0 0 1 7 1.7C15 9.6 8 14 8 14z",
    "download": "M7 1.5h2v7h2.5L8 12 4.5 8.5H7zM2 13h12v1.5H2z",
    "up-next": "M1 3h9v1.6H1zM1 6.5h9v1.6H1zM1 10h9v1.6H1zM11.5 8.5l3.5 2.3-3.5 2.2z",
    "mini": "M1 3h14v10H1zM2.5 8.5v3h6v-3z",
    "visualizer": "M1.5 9h2v5h-2zM4.7 5h2v9h-2zM7.9 2h2v12h-2zM11.1 6.5h2V14h-2zM14 10h1v4h-1z",
    "equalizer": "M2.5 1h1.5v14H2.5zM1 9h4.5v2H1zM7.3 1h1.5v14H7.3zM5.8 4h4.5v2H5.8zM12 1h1.5v14H12zM10.5 10.5H15v2h-4.5z",
    "refresh": "M8 2a6 6 0 0 1 5.7 4.1L15 5v4.5h-4.5l1.6-1.6A4.4 4.4 0 1 0 12.3 10l1.5.5A6 6 0 1 1 8 2z",
    "info": "M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm-1 3h2v2H7zm0 3h2v5H7z",
    "search": "M6.5 1a5.5 5.5 0 0 1 4.4 8.8l4 4-1.1 1.1-4-4A5.5 5.5 0 1 1 6.5 1zm0 1.6a3.9 3.9 0 1 0 0 7.8 3.9 3.9 0 0 0 0-7.8z",
    "star": "M8 1l2.1 4.5 4.9.5-3.7 3.3 1.1 4.8L8 11.6l-4.4 2.5 1.1-4.8L1 6l4.9-.5z",
    "close": "M3.5 2.4L8 6.9l4.5-4.5 1.1 1.1L9.1 8l4.5 4.5-1.1 1.1L8 9.1l-4.5 4.5-1.1-1.1L6.9 8 2.4 3.5z",
    "fullscreen": "M1 1h5v1.6H2.6V6H1zM10 1h5v5h-1.6V2.6H10zM1 10h1.6v3.4H6V15H1zM13.4 10H15v5h-5v-1.6h3.4z",
    "back": "M10.5 2l1.1 1.1L6.7 8l4.9 4.9-1.1 1.1-6-6z",
    "speaker": "M3 1.5h10a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1zM8 3a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3zm0 4.5a3 3 0 1 0 0 6 3 3 0 0 0 0-6zm0 1.6a1.4 1.4 0 1 1 0 2.8 1.4 1.4 0 0 1 0-2.8z",
    "coverflow": "M5.5 3h5v8h-5zM1 4.5l3.5-.8v6.6L1 9.5zM15 4.5l-3.5-.8v6.6L15 9.5zM2 13h12v1H2z",
    "skip-back": "M8 2a6 6 0 1 1-5.6 8.1l1.4-.5A4.5 4.5 0 1 0 8 3.5V6L4 2.8 8 0zM6 7h1.2v5H6zM8.2 7h2.6v1.1H9.4v.9h1.2a1.5 1.5 0 0 1 0 3H8.2v-1.1h2.2a.4.4 0 0 0 0-.8H8.2z",
    "skip-fwd": "M8 2a6 6 0 1 0 5.6 8.1l-1.4-.5A4.5 4.5 0 1 1 8 3.5V6l4-3.2L8 0zM4.6 7h2.4v5H4.6v-1.1h1.3v-.9H4.8V8.9h1.1v-.8H4.6zM8.6 7h2.6v5H8.6zm1 1.1v2.8h.6V8.1z",
}

APP = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#f06cc4"/><stop offset="0.55" stop-color="#b8187f"/><stop offset="1" stop-color="#7a0f55"/>
    </linearGradient>
    <linearGradient id="gl" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.55"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect x="16" y="16" width="224" height="224" rx="48" fill="url(#bg)"/>
  <path d="M16 64a48 48 0 0 1 48-48h128a48 48 0 0 1 48 48v28c-60 18-164 18-224 0z" fill="url(#gl)"/>
  <g stroke="#ffffff" stroke-opacity="0.55" stroke-width="5">
    <line x1="44" y1="92" x2="212" y2="92"/><line x1="44" y1="118" x2="212" y2="118"/>
    <line x1="44" y1="144" x2="212" y2="144"/><line x1="44" y1="170" x2="212" y2="170"/>
    <line x1="44" y1="196" x2="212" y2="196"/>
  </g>
  <g fill="#ffffff">
    <ellipse cx="116" cy="170" rx="18" ry="12.5" transform="rotate(-22 116 170)"/>
    <ellipse cx="116" cy="144" rx="18" ry="12.5" transform="rotate(-22 116 144)"/>
    <ellipse cx="116" cy="118" rx="18" ry="12.5" transform="rotate(-22 116 118)"/>
    <rect x="128" y="48" width="8" height="120" rx="3"/>
    <path d="M136 48c18 6 42 20 40 50-8-14-22-20-40-22z"/>
  </g>
</svg>
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, d in P.items():
        with open(os.path.join(OUT, "chord-%s-symbolic.svg" % name), "w") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
                    '<path fill="#bebebe" fill-rule="evenodd" d="%s"/></svg>\n' % d)
    apps = os.path.join(HERE, "..", "packaging", "root", "usr", "share", "icons", "hicolor", "scalable", "apps")
    os.makedirs(apps, exist_ok=True)
    with open(os.path.join(apps, "folio-chord.svg"), "w") as f:
        f.write(APP)
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    svg = os.path.join(apps, "folio-chord.svg")
    for s in (16, 24, 32, 48, 64, 128, 256):
        d = os.path.join(HERE, "..", "packaging", "root", "usr", "share", "icons", "hicolor", "%dx%d" % (s, s), "apps")
        os.makedirs(d, exist_ok=True)
        GdkPixbuf.Pixbuf.new_from_file_at_size(svg, s, s).savev(os.path.join(d, "folio-chord.png"), "png", [], [])
    print("icons written")


if __name__ == "__main__":
    main()
