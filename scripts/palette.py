"""Shared palette, geometry and font-embedding helpers.

Standard library only -- generate_stats.py runs in CI with no pip install step.
"""

import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"

# The character grid. JetBrains Mono advances 600/1000 units, so a glyph is
# exactly 0.600 em wide and CHAR_W / FONT_SIZE must equal 0.600 or the grid
# shears. Do not touch one without the other.
FONT_SIZE = 12.9
CHAR_W = 7.74          # 12.9 * 0.600
LINE_H = 15.48         # 2 * CHAR_W -- monospace cells are ~2x tall as wide

# Light-to-dark. The leading space is what clears the background to nothing.
#
# Tried and rejected: extending past '@' with the shade blocks U+2591-2593 and
# U+2588. '@' only inks about a third of its cell, so the blocks do lift peak
# contrast against the page by roughly nine times, and JetBrains Mono draws
# them at 600/1000 like everything else so the grid survives. But three of the
# four are dither patterns rather than solid fills, and at six pixels to a cell
# they moire against the pixel grid and pick up colour fringing from subpixel
# antialiasing -- the render came out looking like a decoding fault. Contrast
# is worth having, but not at the price of the page looking broken.
RAMP = " .`:-=+*cs#%@"

# Two palettes, selected by <picture> in the README rather than by a
# prefers-color-scheme query inside the SVG: an <img>-loaded SVG resolves that
# query against the OS preference, not against GitHub's theme setting.
THEMES = {
    "dark": {
        "ink": "#e6edf3",
        "dim": "#7d8590",
        "faint": "#30363d",
        "grid": "#21262d",
        "accent": "#39d353",
        "accent2": "#26a641",
        "accent3": "#006d32",
    },
    "light": {
        "ink": "#1f2328",
        "dim": "#59636e",
        "faint": "#d0d7de",
        "grid": "#eaeef2",
        "accent": "#2da44e",
        "accent2": "#4ac26b",
        "accent3": "#116329",
    },
}


def font_face(woff2_name, family="JBM", weight=400):
    """An @font-face rule carrying the font itself as a data URI.

    An external src cannot work: these files are loaded through an <img> tag
    and browsers refuse subresource fetches for image documents.
    """
    data = base64.b64encode((FONTS / woff2_name).read_bytes()).decode("ascii")
    return (
        "@font-face{font-family:'%s';font-style:normal;font-weight:%d;"
        "src:url(data:font/woff2;base64,%s) format('woff2')}"
        % (family, weight, data)
    )


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write(path, svg):
    path = Path(path)
    path.write_text(svg, encoding="utf-8")
    print("%-28s %7.1f KB" % (path.name, len(svg.encode("utf-8")) / 1024))
