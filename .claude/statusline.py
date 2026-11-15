#!/usr/bin/env python3
"""Claude Code status line: live Claude glyph, session info to its left.

Two DIFFERENT percentages are shown, because they measure different things:
  ctx     = context_window.used_percentage  -> how full THIS conversation is
  5h / 7d = rate_limits.*.used_percentage   -> plan limits (what /usage reports),
            each annotated with time remaining until the window resets.

Glyph: the eyes live INSIDE the head -- two cells of the face row rendered in a
dark tone. Blinking recolours those cells toward the face colour, so the mark's
shape is never altered. The bottom row is legs and stays put. Cells are shaded
by row and column for a soft light-from-upper-left depth.

Layout: the glyph is anchored a fixed gap past the widest text row, and every
row carries left-hand content, so alignment comes from computed interior padding
rather than leading whitespace (which a renderer may trim). Rows are all
newline-terminated: a final row without one is not rendered. RESERVE keeps the
block clear of the interface's own left/right spacing.

Animation runs at 1 fps -- Claude Code enforces a 1s minimum on refreshInterval.
Schema: docs.claude.com/en/docs/claude-code/statusline
"""
import json
import os
import re
import sys
import time

RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
BLUE = "\033[1;34m"
RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"

TRUECOLOR = os.environ.get("COLORTERM", "") in ("truecolor", "24bit")

BASE = (217, 119, 87)     # Claude terracotta #D97757
FALLBACK = "\033[38;5;173m"

# Soft light from the upper left: each row/column step darkens slightly.
ROW_STEP = 0.10
COL_STEP = 0.022
FLOOR = 0.60

# Muscular Clawd, drawn as a 30x6 pixel grid and packed into quadrant blocks
# (2x2 pixels per cell) -> 15 cols x 3 rows. Double-biceps pose: fists up,
# bicep peaks, wide shoulders, broad torso, thick legs.
FIELD = 17           # 15-col glyph + 2 cols of slack for the sway
BUFF = [
    ".111.....111111111111.....111.",   # fists + top of head
    ".111.....11.111111.11.....111.",   # forearms + eyes (holes at x=11, 18)
    ".1111..1111111111111111..1111.",   # bicep peaks + shoulders
    "..11111111111111111111111111..",   # upper arms into chest
    ".......1111111111111111.......",   # broad torso
    ".......11111......11111.......",   # thick legs
]
EYES = {"c": (11, 18), "l": (10, 17), "r": (12, 19), "shut": ()}
QUAD = {'0000': ' ', '1111': '█', '1100': '▀', '0011': '▄', '1010': '▌',
        '0101': '▐', '1000': '▘', '0100': '▝', '0010': '▖', '0001': '▗',
        '1110': '▛', '1101': '▜', '1011': '▙', '0111': '▟', '1001': '▚',
        '0110': '▞'}


def buff_rows(eyes, pump):
    g = [list(r) for r in BUFF]
    for x in range(9, 21):               # clear default eye holes
        g[1][x] = "1"
    for x in eyes:
        g[1][x] = "."
    if pump:                             # flex pump: fists drop one pixel
        for x in (1, 2, 3, 26, 27, 28):
            g[0][x] = "."
    out = []
    for y in range(0, len(g), 2):
        a, b = g[y], g[y + 1]
        out.append("".join(QUAD["".join("1" if c == "1" else "0" for c in
                                        (a[x], a[x + 1], b[x], b[x + 1]))]
                           for x in range(0, len(a), 2)))
    return out


GAP = 3              # columns between the text block and the glyph
RESERVE = 6          # columns left free for the interface's own spacing
CYCLE = 20           # seconds per full animation loop

# One single blink, then a double, so the rhythm reads as organic rather than
# metronomic. The eye holes are a single quadrant each, so there is no partial
# state to render -- a blink is one frame, open to shut to open.
BLINKS = frozenset((6, 14, 16))
# A held glance left, then a deliberate left-to-right sweep across f8..f11.
GAZE_LEFT = frozenset((3, 4, 8))
GAZE_RIGHT = frozenset((10, 11))
SWAY_RIGHT = frozenset((12, 13))
SWAY_LEFT = frozenset((18, 19))

ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def vis(s):
    """Visible width, ignoring ANSI colour codes."""
    return len(ANSI_RE.sub("", s))


def hue(v):
    return RED if v >= 80 else YELLOW if v >= 50 else GREEN


def rgb(c):
    return "\033[38;2;%d;%d;%dm" % c


def shade(color, row, col):
    """Darken `color` by its position: light comes from the upper left."""
    if not TRUECOLOR:
        return FALLBACK
    f = max(FLOOR, 1.0 - ROW_STEP * row - COL_STEP * col)
    return rgb(tuple(int(v * f) for v in color))


def place(art, x):
    """Drop `art` at column x inside a FIELD-wide row, clamped in bounds."""
    x = max(0, min(FIELD - len(art), x))
    return " " * x + art + " " * (FIELD - x - len(art))


def paint(row_art, row_idx):
    """Colour a placed row with the positional shading."""
    out, prev = [], None
    for c, ch in enumerate(row_art):
        if ch == " ":
            out.append(" ")
            prev = None
            continue
        color = shade(BASE, row_idx, c)
        if color != prev:
            out.append(color)
            prev = color
        out.append(ch)
    out.append(RESET)
    return "".join(out)


# Curl frames while working: (cell art, colour map) per row, 15 cols each.
# Colour map: o = body (shaded terracotta), g = dumbbell (steel grey).
HEAD_OPEN, HEAD_SHUT = "▐▛███▜▌", "▐█████▌"
LEGS_ROW = ("    ▐█▀▀▀█▌    ", "    ooooooo    ")
CURL = {
    "down": [("    {H}    ",     "    ooooooo    "),
             ("  ▟█████████▙  ", "  ooooooooooo  "),
             (" ▐█▌▐█▀▀▀█▌▐█▌ ", " gogooooooogog ")],
    "mid":  [("    {H}    ",     "    ooooooo    "),
             ("▐█▌▄▟█████▙▄▐█▌", "gogoooooooooogog"[:15]),
             LEGS_ROW],
    "up":   [("▐█▌ {H} ▐█▌",     "gog ooooooo gog"),
             (" ▜▙▟███████▙▟▛ ", " ooooooooooooo "),
             LEGS_ROW],
}
CURL_CYCLE = ("down", "mid", "up", "up", "mid")   # lift, squeeze at top, lower
STEEL = (150, 160, 170)


def paint_mapped(art, cmap, row_idx):
    out = []
    for c, (ch, k) in enumerate(zip(art, cmap)):
        if ch == " ":
            out.append(" ")
        else:
            out.append(shade(STEEL if k == "g" else BASE, row_idx, c) + ch)
    out.append(RESET)
    return "".join(out)


def is_busy(session_id):
    """Hooks touch this flag on prompt/tool use and remove it on Stop."""
    f = os.path.join(os.environ.get("TMPDIR", "/tmp"),
                     "clawd-busy-%s" % (session_id or "default"))
    try:
        return time.time() - os.path.getmtime(f) < 600   # stale after 10 min
    except OSError:
        return False


def animate(t, busy=False):
    """Return the three glyph rows for second `t`."""
    f = t % CYCLE
    if busy:
        head = HEAD_SHUT if f in BLINKS else HEAD_OPEN
        frame = CURL[CURL_CYCLE[t % len(CURL_CYCLE)]]
        rows = []
        for i, (art, cmap) in enumerate(frame):
            art = art.replace("{H}", head)
            pad = (FIELD - len(art)) // 2
            rows.append(paint_mapped(" " * pad + art + " " * (FIELD - pad - len(art)),
                                     " " * pad + cmap + " " * (FIELD - pad - len(cmap)), i))
        return rows
    sway = 1 if f in SWAY_RIGHT else -1 if f in SWAY_LEFT else 0
    eyes = (EYES["shut"] if f in BLINKS
            else EYES["l"] if f in GAZE_LEFT
            else EYES["r"] if f in GAZE_RIGHT
            else EYES["c"])
    pump = f % 2 == 1                    # flex every other second
    return [paint(place(row, 1 + sway), i)
            for i, row in enumerate(buff_rows(eyes, pump))]


def countdown(secs):
    """Compact 'time remaining' string."""
    if secs <= 0:
        return "now"
    d, rem = divmod(int(secs), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return "%dd%dh" % (d, h)
    if h:
        return "%dh%02dm" % (h, m)
    return "%dm" % max(m, 1)


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}

    def dig(*path, default=None):
        cur = data
        for k in path:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k)
        return default if cur is None else cur

    now = time.time()

    model = dig("model", "display_name", default="unknown") or "unknown"

    try:
        pct = max(0, min(100, int(float(dig("context_window", "used_percentage",
                                            default=0) or 0))))
    except (TypeError, ValueError):
        pct = 0

    def window(name):
        """(used_percentage, seconds_until_reset) for a rate-limit window."""
        v = dig("rate_limits", name, "used_percentage")
        try:
            used = max(0, min(100, int(float(v))))
        except (TypeError, ValueError):
            return None
        try:
            left = float(dig("rate_limits", name, "resets_at")) - now
        except (TypeError, ValueError):
            left = None
        return used, left

    five, week = window("five_hour"), window("seven_day")

    d = dig("workspace", "current_dir", default="") or os.getcwd()
    home = os.path.expanduser("~")
    if d == home:
        d = "~"
    elif d.startswith(home + os.sep):
        d = "~" + d[len(home):]

    filled = max(0, min(10, pct // 10))
    bar = "█" * filled + "░" * (10 - filled)

    # --- rows: (plain, coloured) so widths can be measured before padding ---
    r0 = (d, "%s%s%s" % (BLUE, d, RESET))

    r1_plain = "%s  ctx [%s] %d%%" % (model, bar, pct)
    r1 = (r1_plain, "%s%s%s  %sctx%s %s[%s]%s %s%d%%%s"
          % (BOLD, model, RESET, DIM, RESET, hue(pct), bar, RESET, DIM, pct, RESET))

    seg_plain, seg_col = [], []
    for label, w in (("5h", five), ("7d", week)):
        if w is None:
            continue
        used, left = w
        tail = "" if left is None else " %s" % countdown(left)
        seg_plain.append("%s %d%%%s" % (label, used, tail))
        seg_col.append("%s%s%s %s%d%%%s%s"
                       % (DIM, label, RESET, hue(used), used, RESET,
                          "" if not tail else "%s%s%s" % (DIM, tail, RESET)))
    if seg_plain:
        r2 = ("  ".join(seg_plain), "  ".join(seg_col))
    else:
        r2 = ("plan limits n/a", "%splan limits n/a%s" % (DIM, RESET))

    rows = [r0, r1, r2]

    # --- terminal width: Claude Code sets COLUMNS; stdout is captured, not a tty ---
    try:
        cols = int(os.environ.get("COLUMNS", "80"))
    except ValueError:
        cols = 80

    # The interface adds its own left/right spacing around the status line, so
    # filling all of COLUMNS overflows and the renderer ellipsizes the tail.
    usable = cols - RESERVE

    show_glyph = usable >= FIELD + 12
    budget = usable - (FIELD + GAP) if show_glyph else usable

    # Trim over-long left content (path from the left, others from the right)
    out = []
    for i, (plain, colored) in enumerate(rows):
        if budget > 3 and len(plain) > budget:
            if i == 0:
                plain = "…" + plain[-(budget - 1):]
                colored = "%s%s%s" % (BLUE, plain, RESET)
            else:
                plain = plain[: budget - 1] + "…"
                colored = "%s%s%s" % (DIM, plain, RESET)
        out.append((plain, colored))

    if not show_glyph:
        for _, colored in out:
            print(colored)
        return

    # Anchor the glyph just past the widest row rather than at the terminal
    # edge: keeps it visually attached to the text and clear of the margins.
    glyph = animate(int(now), is_busy(dig("session_id")))
    start = min(max(len(p) for p, _ in out) + GAP, usable - FIELD)
    for (plain, colored), g in zip(out, glyph):
        print("%s%s%s" % (colored, " " * max(1, start - len(plain)), g))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("%s%s%s" % (DIM, buff_rows(EYES["c"], False)[1], RESET))
