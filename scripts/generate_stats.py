"""Draw stats.svg, streak.svg, langs.svg and year.svg from the GraphQL data.

    GITHUB_TOKEN=... GH_LOGIN=opxie1 python scripts/generate_stats.py

Each graphic is written twice, -dark and -light, and the README picks between
them with <picture>. Standard library only: no dependencies to break in CI.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghdata  # noqa: E402
from palette import RAMP, ROOT, THEMES, esc, font_face, write  # noqa: E402

MONO = "'JBM',ui-monospace,'DejaVu Sans Mono',monospace"
_FACES = None


def faces():
    global _FACES
    if _FACES is None:
        _FACES = font_face("data-regular.woff2", weight=400) + font_face("data-bold.woff2", weight=700)
    return _FACES


def open_svg(w, h, label):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
        'role="img" aria-label="%s"><defs><style>%s'
        # font-family only. A fill here would be a CSS declaration and would
        # beat every per-element fill="", which are presentation attributes.
        "text{font-family:%s}</style></defs>" % (w, h, w, h, esc(label), faces(), MONO)
    )


def frame(w, h, c):
    return ('<rect x="0.5" y="0.5" width="%.1f" height="%.1f" rx="6" fill="none" '
            'stroke="%s" stroke-width="1"/>' % (w - 1, h - 1, c["faint"]))


def txt(x, y, s, size=11, fill="#000", weight=400, anchor="start", extra=""):
    return ('<text x="%.2f" y="%.2f" font-size="%.1f" font-weight="%d" fill="%s" '
            'text-anchor="%s"%s>%s</text>' % (x, y, size, weight, fill, anchor, extra, esc(str(s))))


def n(v):
    return "{:,}".format(v)


def short(v):
    if v >= 1_000_000:
        return "%.1fM" % (v / 1_000_000)
    if v >= 1_000:
        return "%.1fk" % (v / 1_000)
    return str(v)


def pretty(iso):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d %b %Y").lstrip("0")


def clip(name, chars=17):
    """Language names are a fixed grid wide; longer ones would run into the bar."""
    return name if len(name) <= chars else name[:chars - 1] + "."


def days(n):
    return "%d day%s" % (n, "" if n == 1 else "s")


# --------------------------------------------------------------------------- stats

def stats_svg(d, theme, w=420, h=214):
    c = THEMES[theme]
    o = [open_svg(w, h, "%s contributions in the last year" % n(d["total"])), frame(w, h, c)]

    o.append(txt(18, 40, n(d["total"]), 34, c["ink"], 700))
    o.append(txt(18, 58, "contributions", 10, c["dim"]))
    o.append(txt(w - 18, 40, d["from"].replace("-", "."), 9.5, c["dim"], anchor="end"))
    o.append(txt(w - 18, 54, d["today"].replace("-", "."), 9.5, c["dim"], anchor="end"))

    # Weekly aggregates, so an area is defensible here where a line over daily
    # counts would claim values that never existed.
    wk = ghdata.weekly(d["days"])
    x0, y0, pw, ph = 18.0, 74.0, w - 36.0, 52.0
    peak = max(wk) or 1
    step = pw / max(1, len(wk) - 1)
    pts = [(x0 + i * step, y0 + ph - (v / peak) * ph) for i, v in enumerate(wk)]
    line = " ".join("%.2f,%.2f" % p for p in pts)
    o.append('<polygon points="%.2f,%.2f %s %.2f,%.2f" fill="%s" opacity="0.30"/>'
             % (x0, y0 + ph, line, x0 + pw, y0 + ph, c["accent"]))
    o.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="1.6" '
             'stroke-linejoin="round" stroke-linecap="round"/>' % (line, c["accent"]))
    o.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="1"/>'
             % (x0, y0 + ph + 0.5, x0 + pw, y0 + ph + 0.5, c["faint"]))
    o.append(txt(x0, y0 + ph + 14, "weekly  peak %d" % peak, 9, c["dim"]))
    o.append(txt(x0 + pw, y0 + ph + 14, "%d weeks" % len(wk), 9, c["dim"], anchor="end"))

    rows = [("commits", d["commits"]), ("pull requests", d["prs"]),
            ("issues", d["issues"]), ("reviews", d["reviews"])]
    ry = 162.0
    for i, (label, v) in enumerate(rows):
        cx = 18 + (i % 2) * (w - 36) / 2
        cy = ry + (i // 2) * 20
        o.append(txt(cx, cy, label, 10, c["dim"]))
        o.append(txt(cx + (w - 36) / 2 - 12, cy, n(v), 10.5, c["ink"], 700, anchor="end"))
    o.append("</svg>")
    return "".join(o)


# -------------------------------------------------------------------------- streak

def streak_svg(d, theme, w=420, h=214):
    c = THEMES[theme]
    s = ghdata.streaks(d["days"], d["today"])
    o = [open_svg(w, h, "current streak %s, longest %s" % (days(s["current"]), days(s["longest"]))),
         frame(w, h, c)]

    def block(y, title, n, span, accent):
        o.append(txt(18, y, title, 10, c["dim"]))
        o.append(txt(18, y + 32, str(n), 30, accent, 700))
        unit = "day" if n == 1 else "days"
        o.append(txt(18 + len(str(n)) * 18.0 + 7, y + 32, unit, 11, c["dim"]))      # 30px * 0.600 advance
        if span:
            rng = pretty(span[0]) if span[0] == span[1] else "%s - %s" % (pretty(span[0]), pretty(span[1]))
        else:
            rng = "no run in the window"
        o.append(txt(18, y + 48, rng, 9.5, c["dim"]))

    block(30, "current streak", s["current"], s["current_span"], c["accent"])
    o.append('<line x1="18" y1="98" x2="%.1f" y2="98" stroke="%s" stroke-width="1"/>' % (w - 18, c["faint"]))
    block(122, "longest streak", s["longest"], s["longest_span"], c["ink"])

    active = sum(1 for _, v in d["days"] if v > 0)
    o.append(txt(w - 18, 30, "%d/%d active days" % (active, len(d["days"])), 9.5, c["dim"], anchor="end"))
    o.append(txt(w - 18, 122, "since %s" % pretty(d["created"]), 9.5, c["dim"], anchor="end"))
    o.append("</svg>")
    return "".join(o)


# --------------------------------------------------------------------------- langs

def langs_svg(d, theme, w=860):
    c = THEMES[theme]
    L = ghdata.languages(d["repos"])
    # Height follows the row count. Fixed at six rows, an account with four
    # languages gets a card that is a third empty.
    h = 50 + 22 * max(1, len(L["bytes"]), len(L["repos"])) + 8
    # One colour, fading by rank. Cycling through accent/accent2/accent3 was
    # not monotonic -- on the light palette rank 3 came out darker than rank 1.
    fade = [1.0, 0.80, 0.62, 0.46, 0.33, 0.23]
    o = [open_svg(w, h, "top languages by bytes and by repository"), frame(w, h, c)]
    o.append('<line x1="%.1f" y1="16" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1"/>'
             % (w / 2, w / 2, h - 16, c["faint"]))

    o.append(txt(20, 28, "by bytes written", 10, c["dim"]))
    o.append(txt(w / 2 - 20, 28, short(L["total_bytes"]) + "B total", 9.5, c["dim"], anchor="end"))
    bar_x, bar_w = 150.0, w / 2 - 20 - 150.0 - 46
    widest = L["bytes"][0][2] if L["bytes"] else 1
    for i, (name, _, pct, colour) in enumerate(L["bytes"]):
        y = 50 + i * 22
        if colour:
            o.append('<circle cx="24" cy="%.1f" r="3.5" fill="%s"/>' % (y - 3.5, colour))
        o.append(txt(34, y, clip(name), 10.5, c["ink"]))
        o.append('<rect x="%.1f" y="%.1f" width="%.2f" height="7" rx="3.5" fill="%s" opacity="%.2f"/>'
                 % (bar_x, y - 9, max(2.0, bar_w * pct / widest), c["accent"], fade[min(i, 5)]))
        o.append(txt(w / 2 - 20, y, "%.1f%%" % pct, 10, c["dim"], anchor="end"))

    o.append(txt(w / 2 + 20, 28, "by repository", 10, c["dim"]))
    o.append(txt(w - 20, 28, "%d public repos" % d["repo_count"], 9.5, c["dim"], anchor="end"))
    rbar_x, rbar_w = w / 2 + 150.0, w - 20 - (w / 2 + 150.0) - 34
    rmax = L["repos"][0][1] if L["repos"] else 1
    for i, (name, count) in enumerate(L["repos"]):
        y = 50 + i * 22
        colour = L["colors"].get(name)
        if colour:
            o.append('<circle cx="%.1f" cy="%.1f" r="3.5" fill="%s"/>' % (w / 2 + 24, y - 3.5, colour))
        o.append(txt(w / 2 + 34, y, clip(name), 10.5, c["ink"]))
        o.append('<rect x="%.1f" y="%.1f" width="%.2f" height="7" rx="3.5" fill="%s" opacity="%.2f"/>'
                 % (rbar_x, y - 9, max(2.0, rbar_w * count / rmax), c["accent"], fade[min(i, 5)]))
        o.append(txt(w - 20, y, str(count), 10, c["dim"], anchor="end"))
    o.append("</svg>")
    return "".join(o)


# ---------------------------------------------------------------------------- year

YEAR_RAMP = [RAMP[1], RAMP[3], RAMP[6], RAMP[10], RAMP[12]]     # . : + # @


def year_svg(d, theme, w=860):
    """One character per day, drawn from the portrait's own ramp.

    Daily counts are sparse and discrete, so this is a grid of marks rather
    than a line: a day with nothing in it is just the faintest character.
    """
    c = THEMES[theme]
    left, right, top, legend = 30.0, 10.0, 26.0, 22.0
    days = d["days"]
    first = datetime.strptime(days[0][0], "%Y-%m-%d").date()
    offset = (first.weekday() + 1) % 7                          # GitHub weeks start on Sunday
    cols = -(-(len(days) + offset) // 7)
    cell = (w - left - right) / cols
    h = top + 7 * cell + legend
    # A sequential scale has to be monotonic, so it is one hue at rising
    # opacity rather than three named greens that do not order cleanly.
    fade = [None, 0.40, 0.60, 0.80, 1.0]

    peak = max((v for _, v in days), default=0)
    def level(v):
        if v <= 0:
            return 0
        return min(4, 1 + int(3 * (v - 1) / max(1, peak - 1)))

    o = [open_svg(w, round(h), "%s contributions, one character per day" % n(d["total"]))]

    # Month labels sit above the first column of each month.
    seen = set()
    for i, (date, _) in enumerate(days):
        dt = datetime.strptime(date, "%Y-%m-%d").date()
        key = (dt.year, dt.month)
        if key in seen:
            continue
        seen.add(key)
        col = (i + offset) // 7
        if col < cols - 1:
            o.append(txt(left + col * cell, top - 10, dt.strftime("%b").lower(), 8.5, c["dim"]))

    for row, label in ((1, "mon"), (3, "wed"), (5, "fri")):
        o.append(txt(left - 6, top + row * cell + cell * 0.72, label, 8.5, c["dim"], anchor="end"))

    # One <text> per (row, level) with a multi-value x list: each absolute x
    # starts its own chunk, so text-anchor="middle" centres every glyph.
    buckets = {}
    for i, (_, v) in enumerate(days):
        pos = i + offset
        buckets.setdefault((pos % 7, level(v)), []).append(left + (pos // 7) * cell + cell / 2)
    for (row, lv), xs in sorted(buckets.items()):
        fill, op = (c["faint"], 1.0) if lv == 0 else (c["accent"], fade[lv])
        o.append('<text x="%s" y="%.2f" font-size="%.1f" fill="%s" opacity="%.2f" '
                 'text-anchor="middle" xml:space="preserve">%s</text>'
                 % (" ".join("%.2f" % x for x in xs), top + row * cell + cell * 0.74,
                    cell * 0.95, fill, op, YEAR_RAMP[lv] * len(xs)))

    y = h - 7
    o.append(txt(left, y, "%s in the last year" % n(d["total"]), 9, c["dim"]))
    o.append(txt(w - right - 96, y, "less", 9, c["dim"], anchor="end"))
    o.append('<text x="%.1f" y="%.1f" font-size="10" fill="%s" xml:space="preserve">%s</text>'
             % (w - right - 90, y, c["dim"], "".join(YEAR_RAMP)))
    o.append(txt(w - right, y, "more", 9, c["dim"], anchor="end"))
    o.append("</svg>")
    return "".join(o)


# ---------------------------------------------------------------------------- main

def main():
    login = os.environ.get("GH_LOGIN") or "opxie1"
    d = ghdata.fetch(login, ghdata.token())
    print("%s: %s contributions, %d public repos, %d days"
          % (login, n(d["total"]), d["repo_count"], len(d["days"])))

    for theme in THEMES:
        write(ROOT / ("stats-%s.svg" % theme), stats_svg(d, theme))
        write(ROOT / ("streak-%s.svg" % theme), streak_svg(d, theme))
        write(ROOT / ("langs-%s.svg" % theme), langs_svg(d, theme))
        write(ROOT / ("year-%s.svg" % theme), year_svg(d, theme))


if __name__ == "__main__":
    main()
