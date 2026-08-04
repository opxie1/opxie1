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
MODEL = "u2net_human_seg"
CEILING = 210          # brightest a normalised subject pixel may get; 255 is the background
FLOOR = 2              # dimmest ramp index inside the subject, so the silhouette stays whole
DUR = 0.55             # seconds for one row to finish wiping in
TOTAL = 5.2            # seconds for the whole portrait to print; sets the stagger,
                       # so a 77-row figure does not sit there typing for 7 seconds


def subject_box(alpha, pad=0.03):
    """Bounding box of the cut-out subject, with a little air around it."""
    ys, xs = np.nonzero(np.array(alpha) > 8)
    if not len(xs):
        return None
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    mx, my = int((x1 - x0) * pad), int((y1 - y0) * pad)
    w, h = alpha.size
    return (max(0, x0 - mx), max(0, y0 - my), min(w, x1 + mx), min(h, y1 + my))


def head_box(alpha, box, shoulder=0.52, jaw=0.18):
    """Head crop, found from the cut-out mask rather than a face detector.

    OpenCV 5 dropped the Haar cascades, and this needs no model anyway: on a
    standing figure the mask is narrow across the head and widens sharply at
    the shoulders, so the first row past that threshold is the neckline.
    """
    m = np.array(alpha)[box[1]:box[3], box[0]:box[2]] > 8
    widths = m.sum(axis=1)
    if not widths.max():
        return None
    wide = np.nonzero(widths >= shoulder * widths.max())[0]
    neck = int(wide[0]) if len(wide) else 0
    if neck < 0.06 * len(widths):                     # no clear shoulder line
        neck = int(0.22 * len(widths))
    bottom = min(len(widths), int(neck * (1 + jaw)))

    # Measure the width across the head only. Taking it over the whole band
    # picks up the shoulders that have already started flaring at the neckline
    # and returns a box wider than it is tall.
    xs = np.nonzero(m[:int(bottom * 0.65)].any(axis=0))[0]
    if not len(xs):
        return None
    pad_x = int((xs[-1] - xs[0]) * 0.10)
    pad_y = int(bottom * 0.10)
    return (max(0, box[0] + int(xs[0]) - pad_x),
            max(0, box[1] - pad_y),
            min(alpha.size[0], box[0] + int(xs[-1]) + pad_x),
            min(alpha.size[1], box[1] + bottom))


def to_grid(src, cols=COLS, crop="none", model=MODEL, normalize=False, ceiling=CEILING,
             gamma=GAMMA, clahe=CLAHE_CLIP):
    """rembg cut-out -> crop -> normalise -> bilateral -> CLAHE -> curve.

    Returns per-cell brightness in [0,1] and a per-cell subject mask; turning
    those into characters is to_lines(), because the two themes need
    different mappings.
    """
    from rembg import new_session, remove

    img = Image.open(src).convert("RGBA")
    # Model choice decides what counts as the subject. u2net_human_seg cuts out
    # the person alone; the general models keep whatever they are touching, so
    # a person standing against a car comes back as person-and-car.
    cut = remove(img, session=new_session(model))
    alpha = cut.split()[3]

    # Composite onto white. Everything outside the subject becomes 255, which
    # maps to the blank end of the ramp. Skip this and the background fills
    # with '@' and drowns the portrait.
    flat = Image.new("RGB", cut.size, (255, 255, 255))
    flat.paste(cut, mask=alpha)

    if crop != "none":
        box = subject_box(alpha)
        if crop == "head" and box:
            box = head_box(alpha, box) or box
        if box:
            flat, alpha = flat.crop(box), alpha.crop(box)
            print("cropped to %dx%d" % (flat.width, flat.height))

    g = np.array(flat.convert("L"))
    mask = np.array(alpha) > 8

    if normalize and mask.any():
        # A white car against a white background is a level and a half apart on
        # a 13-step ramp, so the body renders as nothing and the wheels float.
        # Stretching the subject's own range to a ceiling below 255 keeps the
        # background blank while giving light subjects somewhere to live.
        lo, hi = np.percentile(g[mask], (1.0, 99.0))
        if hi > lo:
            g = np.where(mask, np.clip((g - lo) / (hi - lo) * ceiling, 0, ceiling), 255.0)
        g = g.astype(np.uint8)

    g = cv2.bilateralFilter(g, 9, 75, 75)                       # smooth skin, keep edges
    if clahe > 0:
        g = cv2.createCLAHE(clipLimit=clahe, tileGridSize=(8, 8)).apply(g)
    g = g.copy()
    g[~mask] = 255          # CLAHE tiles straddling the edge darken the background

    h, w = g.shape
    rows = max(1, int(round(cols * (h / w) * ASPECT)))
    small = cv2.resize(g, (cols, rows), interpolation=cv2.INTER_AREA).astype(np.float32)
    keep = cv2.resize(mask.astype(np.float32), (cols, rows), interpolation=cv2.INTER_AREA) > 0.4

    # Local contrast alone leaves a flatly-lit face washed out. This curve is
    # what makes glasses, brows and lips survive the 13-level quantisation.
    small = np.clip((small / 255.0) ** gamma, 0.0, 1.0)
    return small, keep


def to_lines(small, keep, invert=False, floor=FLOOR):
    """Quantise brightness onto the ramp.

    A character's ink is dark on the light theme and light on the dark theme,
    so the same mapping cannot serve both: drawn straight, a white car on the
    dark theme renders as a hole and its black tyres come out glowing. The dark
    theme therefore maps bright-to-dense, with the background pinned to blank
    since it would otherwise be the densest thing on the page.

    Whichever way it runs, one end of the subject falls off. A white car goes
    blank on the light theme and a dark jacket goes blank on the dark theme, so
    part of the subject drops out and the silhouette breaks. The floor holds
    every subject cell at one visible character, which keeps the outline whole
    while leaving the relative tones alone.
    """
    v = small if invert else 1.0 - small

    # Spread the subject across the whole ramp. The normalisation ceiling and
    # the floor each eat into the range from one end, and clipping to the floor
    # instead of mapping to it piles every dark tone onto one character. Left
    # alone the subject used indices 2 to 10 of 0 to 12, which is why the dark
    # render came out a flat grey smudge with the tyres and the jacket landing
    # on the same glyph.
    if keep.any():
        lo, hi = np.percentile(v[keep], (2.0, 98.0))
        if hi > lo:
            v = np.clip((v - lo) / (hi - lo), 0.0, 1.0)

    top = len(RAMP) - 1
    idx = np.clip((floor + v * (top - floor)).round().astype(int), 0, top)
    idx = np.where(keep, idx, 0)                    # outside the subject is always blank
    return ["".join(RAMP[i] for i in row) for row in idx]


def to_ascii(src, cols=COLS, crop="none", model=MODEL, normalize=False, ceiling=CEILING,
             gamma=GAMMA, invert=False):
    small, keep = to_grid(src, cols, crop, model, normalize, ceiling, gamma)
    return to_lines(small, keep, invert)


def trim(lines):
    """Drop fully blank rows top and bottom.

    Blank rows are skipped when drawing but still occupy height, so an
    uncropped frame ships dead space above and below the subject and pushes
    everything below it off the first screen.
    """
    top, bottom = 0, len(lines)
    while top < bottom and not lines[top].strip():
        top += 1
    while bottom > top and not lines[bottom - 1].strip():
        bottom -= 1
    return lines[top:bottom] or lines


def build_svg(lines, theme, cols=COLS, display_w=DISPLAY_W):
    c = THEMES[theme]
    lines = trim(lines)
    w = cols * CHAR_W
    h = len(lines) * LINE_H + LINE_H * 0.4
    scale = display_w / w
    stagger = max(0.02, (TOTAL - DUR) / max(1, len(lines) - 1))
    total = (len(lines) - 1) * stagger + DUR

    out = [
        # The ramp now carries shade blocks, so state the encoding rather than
        # leaning on the XML default.
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %.2f %.2f" role="img" aria-label="ASCII portrait">'
        % (round(display_w), round(h * scale), w, h),
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
        begin = i * stagger
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
    ap.add_argument("--crop", choices=("none", "subject", "head"), default="none",
                    help="none keeps the frame; subject fits the cut-out; head goes chin-to-hair")
    ap.add_argument("--model", default=MODEL,
                    help="rembg model; birefnet-general keeps a person and what they stand against")
    ap.add_argument("--width", type=int, default=DISPLAY_W, help="display width in px")
    ap.add_argument("--normalize", action="store_true",
                    help="stretch the subject's own range; needed when the subject is light")
    ap.add_argument("--ceiling", type=int, default=CEILING)
    ap.add_argument("--gamma", type=float, default=GAMMA)
    ap.add_argument("--clahe", type=float, default=CLAHE_CLIP,
                    help="0 disables it; local contrast flattens a scene that already has global structure")
    ap.add_argument("--floor", type=int, default=FLOOR)
    args = ap.parse_args()

    small, keep = to_grid(args.photo, args.cols, args.crop, args.model,
                          args.normalize, args.ceiling, args.gamma, args.clahe)
    print("%d cols x %d rows" % (args.cols, len(small)))

    for theme in THEMES:
        lines = to_lines(small, keep, invert=(theme == "dark"), floor=args.floor)
        svg, total = build_svg(lines, theme, args.cols, args.width)
        ink = sum(1 for r in lines for ch in r if ch != " ") / (len(lines) * args.cols)
        write(ROOT / ("portrait-%s.svg" % theme), svg)
        print("   %-5s density %.2f" % (theme, ink))
    print("types for %.1fs, then freezes" % total)


if __name__ == "__main__":
    main()
