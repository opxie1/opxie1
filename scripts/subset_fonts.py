"""Build the woff2 subsets that get inlined into every SVG.

Run once, or after changing which characters appear in the graphics:

    python scripts/subset_fonts.py

Inlining a full JetBrains Mono TTF into each file would cost roughly 4.5 MB
across the page. These subsets bring that to a few tens of kilobytes.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from palette import FONTS, RAMP  # noqa: E402

# Basic latin, minus the control range, plus the ramp characters (all of which
# are already ASCII). Covers every glyph the data graphics and headings draw.
LATIN = "".join(chr(c) for c in range(0x20, 0x7F))

SUBSETS = [
    # (source ttf,               output,              characters)
    ("JetBrainsMono-Regular.ttf", "ramp.woff2", RAMP),
    ("JetBrainsMono-Regular.ttf", "head.woff2", "abcdefghijklmnopqrstuvwxyz .-/"),
    ("JetBrainsMono-Regular.ttf", "data-regular.woff2", LATIN),
    ("JetBrainsMono-Bold.ttf", "data-bold.woff2", LATIN),
]


def main():
    missing = [s for s, _, _ in SUBSETS if not (FONTS / s).exists()]
    if missing:
        sys.exit("missing source font(s) in %s: %s" % (FONTS, ", ".join(sorted(set(missing)))))

    for src, out, text in SUBSETS:
        subprocess.run(
            [
                sys.executable, "-m", "fontTools.subset", str(FONTS / src),
                "--text=" + text,
                "--flavor=woff2",
                "--layout-features=",
                "--no-hinting",
                "--desubroutinize",
                "--output-file=" + str(FONTS / out),
            ],
            check=True,
        )
        kb = (FONTS / out).stat().st_size / 1024
        print("%-22s %3d chars  %5.1f KB" % (out, len(set(text)), kb))

    total = sum((FONTS / o).stat().st_size for _, o, _ in SUBSETS) / 1024
    print("%-22s %14.1f KB" % ("total", total))


if __name__ == "__main__":
    main()
