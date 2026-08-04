"""Photo -> self-typing ASCII portrait, as a pair of SVGs (dark + light).

    python scripts/ascii_portrait.py assets/photo.jpg

Needs pillow, numpy, opencv-python-headless, rembg, onnxruntime. The first run
downloads a ~176 MB background-removal model, once, then caches it.
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from palette import CHAR_W, FONT_SIZE, LINE_H, RAMP, ROOT, THEMES, esc, font_face, write  # noqa: E402

COLS = 90              # below ~88 the face muddies; much above and it dominates
DISPLAY_W = 460        # what the README asks for; the SVG is drawn larger and scaled
ASPECT = 0.48          # monospace cells are ~2x tall as wide
GAMMA = 1.7            # the darkening curve -- without it the face washes out
CLAHE_CLIP = 3.0
STAGGER = 0.09         # seconds between the start of one row and the next
DUR = 0.55             # seconds for one row to finish wiping in


def to_ascii(src, cols=COLS):
    """rembg cut-out -> bilateral -> CLAHE -> darkening curve -> ramp."""
    from rembg import remove

    img = Image.open(src).convert("RGBA")
    cut = remove(img)

    # Composite onto white. Everything outside the subject becomes 255, which
    # maps to the blank end of the ramp. Skip this and the background fills
    # with '@' and drowns the portrait.
    flat = Image.new("RGB", cut.size, (255, 255, 255))
    flat.paste(cut, mask=cut.split()[3])

    g = np.array(flat.convert("L"))
    g = cv2.bilateralFilter(g, 9, 75, 75)                       # smooth skin, keep edges
    g = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=(8, 8)).apply(g)

    h, w = g.shape
    rows = max(1, int(round(cols * (h / w) * ASPECT)))
    small = cv2.resize(g, (cols, rows), interpolation=cv2.INTER_AREA).astype(np.float32)

    # Local contrast alone leaves a flatly-lit face washed out. This curve is
    # what makes glasses, brows and lips survive the 13-level quantisation.
    small = np.clip((small / 255.0) ** GAMMA, 0.0, 1.0)

    idx = np.clip(((1.0 - small) * (len(RAMP) - 1)).round().astype(int), 0, len(RAMP) - 1)
    return ["".join(RAMP[i] for i in row) for row in idx]


def build_svg(lines, theme, cols=COLS):
    c = THEMES[theme]
    w = cols * CHAR_W
    h = len(lines) * LINE_H + LINE_H * 0.4
    scale = DISPLAY_W / w
    total = (len(lines) - 1) * STAGGER + DUR

    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %.2f %.2f" role="img" aria-label="ASCII portrait">'
        % (round(DISPLAY_W), round(h * scale), w, h),
        "<defs><style>%s"
        "text{font-family:'JBM',ui-monospace,'DejaVu Sans Mono',monospace;"
        "font-size:%.2fpx;white-space:pre;fill:%s}</style>" % (font_face("ramp.woff2"), FONT_SIZE, c["ink"]),
    ]

    body, clips = [], []
    for i, raw in enumerate(lines):
        stripped = raw.rstrip()
        if not stripped.strip():
            continue
        lead = len(stripped) - len(stripped.lstrip())
        text = stripped[lead:]
        x = lead * CHAR_W
        y = (i + 1) * LINE_H
        begin = i * STAGGER
        cw = len(text) * CHAR_W

        # Each row is revealed by a rect whose width animates 0 -> full. Every
        # animation freezes, so the portrait prints once and stops. No looping.
        clips.append(
            '<clipPath id="r%d"><rect x="%.2f" y="%.2f" width="0" height="%.2f">'
            '<animate attributeName="width" from="0" to="%.2f" begin="%.2fs" dur="%.2fs" '
            'fill="freeze" calcMode="linear"/></rect></clipPath>'
            % (i, x, y - LINE_H, LINE_H * 1.2, cw, begin, DUR)
        )
        body.append(
            '<text clip-path="url(#r%d)" x="%.2f" y="%.2f" xml:space="preserve" '
            'textLength="%.2f" lengthAdjust="spacing">%s</text>'
            % (i, x, y, cw, esc(text))
        )
        # A small block rides the wipe edge as a cursor, then disappears.
        body.append(
            '<rect y="%.2f" width="%.2f" height="%.2f" fill="%s" opacity="0">'
            '<set attributeName="opacity" to="0.85" begin="%.2fs"/>'
            '<animate attributeName="x" from="%.2f" to="%.2f" begin="%.2fs" dur="%.2fs" fill="freeze"/>'
            '<set attributeName="opacity" to="0" begin="%.2fs" fill="freeze"/></rect>'
            % (y - LINE_H * 0.82, CHAR_W, LINE_H * 0.86, c["accent"],
               begin, x, x + cw - CHAR_W, begin, DUR, begin + DUR)
        )

    out.append("".join(clips))
    out.append("</defs>")
    out.append("".join(body))
    out.append("</svg>")
    return "".join(out), total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photo", help="source photo; 1200px+, tight crop, side light")
    ap.add_argument("--cols", type=int, default=COLS)
    args = ap.parse_args()

    lines = to_ascii(args.photo, args.cols)
    ink = sum(1 for r in lines if r.strip())
    print("%d cols x %d rows (%d non-blank)" % (args.cols, len(lines), ink))

    for theme in THEMES:
        svg, total = build_svg(lines, theme, args.cols)
        write(ROOT / ("portrait-%s.svg" % theme), svg)
    print("types for %.1fs, then freezes" % total)


if __name__ == "__main__":
    main()
