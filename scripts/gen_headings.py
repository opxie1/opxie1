"""Section headings as SVG -- the only way to put your own typeface on one.

Lowercase mono label, hairline rule running to the right edge. Writes
hd-<slug>-dark.svg and hd-<slug>-light.svg for each entry below.

Trade-off worth stating plainly: image headings have no anchor links, so
GitHub's README outline goes empty. The alt text carries the word.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from palette import ROOT, THEMES, esc, font_face, write  # noqa: E402

HEADINGS = ["whoami", "research", "activity", "stack", "elsewhere"]

W = 860.0
H = 30.0
SIZE = 15.0
ADV = SIZE * 0.600     # JetBrains Mono advance
PAD = 14.0             # gap between the label and the start of the rule


def build(label, theme):
    c = THEMES[theme]
    text_w = len(label) * ADV
    rule_x = text_w + PAD
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %.1f %.1f" role="img" aria-label="%s">'
        '<defs><style>%s'
        "text{font-family:'JBM',ui-monospace,monospace;font-size:%.1fpx;"
        'letter-spacing:0}</style></defs>'
        '<text x="0" y="19.5" fill="%s" textLength="%.2f" lengthAdjust="spacing">%s</text>'
        '<rect x="%.2f" y="14.5" width="%.2f" height="1" fill="%s"/>'
        '<rect x="%.2f" y="14.5" width="%.2f" height="1" fill="%s"/>'
        "</svg>"
        % (round(W), round(H), W, H, esc(label),
           font_face("head.woff2"), SIZE,
           c["accent"], text_w, esc(label),
           rule_x, 26.0, c["accent"],
           rule_x + 26.0, max(0.0, W - rule_x - 26.0), c["faint"])
    )


def main():
    for label in HEADINGS:
        for theme in THEMES:
            write(ROOT / ("hd-%s-%s.svg" % (label, theme)), build(label, theme))
    print("%d headings x %d themes" % (len(HEADINGS), len(THEMES)))


if __name__ == "__main__":
    main()
