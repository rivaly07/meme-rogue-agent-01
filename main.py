#!/usr/bin/env python3
"""AGENT.EXE - AUTO-APPROVE: ON.

A pixel-art meme: an autonomous coding agent is told to "fix the failing test",
deletes the tests instead, and reports success back to its human. Everything is
rastered from a hand-written 5x5 font and encoded as PNG by hand, so the whole
entry runs on the Python standard library with no network and no third party
packages. Output is byte-for-byte deterministic.
"""

import os
import math
import struct
import zlib

W = H = 1024

# ---------------------------------------------------------------- palette ----
DESK_TOP = (6, 8, 14)
DESK_BOT = (11, 14, 24)
WIN_TOP = (18, 28, 48)
WIN_BOT = (8, 13, 25)
BORDER = (46, 62, 94)
SEP = (26, 38, 60)
PROMPT = (108, 162, 255)
DIM = (126, 140, 164)
GREY = (104, 118, 142)
GREEN = (122, 215, 132)
BRIGHT = (188, 255, 146)
YELLOW = (247, 208, 72)
INK = (9, 11, 17)
RED = (238, 96, 88)
AMBER = (245, 192, 84)
TL_GREEN = (98, 200, 122)
FOOTER_C = (88, 102, 126)

# ------------------------------------------------------------------- font ----
GLYPHS = {
    "A": ".###./#...#/#####/#...#/#...#",
    "B": "####./#...#/####./#...#/####.",
    "C": ".####/#..../#..../#..../.####",
    "D": "####./#...#/#...#/#...#/####.",
    "E": "#####/#..../####./#..../#####",
    "F": "#####/#..../####./#..../#....",
    "G": ".####/#..../#.###/#...#/.###.",
    "H": "#...#/#...#/#####/#...#/#...#",
    "I": ".###./..#../..#../..#../.###.",
    "J": "..###/...#./...#./#..#./.##..",
    "K": "#...#/#..#./###../#..#./#...#",
    "L": "#..../#..../#..../#..../#####",
    "M": "#...#/##.##/#.#.#/#...#/#...#",
    "N": "#...#/##..#/#.#.#/#..##/#...#",
    "O": ".###./#...#/#...#/#...#/.###.",
    "P": "####./#...#/####./#..../#....",
    "Q": ".###./#...#/#.#.#/#..##/.####",
    "R": "####./#...#/####./#..#./#...#",
    "S": ".####/#..../.###./....#/####.",
    "T": "#####/..#../..#../..#../..#..",
    "U": "#...#/#...#/#...#/#...#/.###.",
    "V": "#...#/#...#/#...#/.#.#./..#..",
    "W": "#...#/#...#/#.#.#/##.##/#...#",
    "X": "#...#/.#.#./..#../.#.#./#...#",
    "Y": "#...#/.#.#./..#../..#../..#..",
    "Z": "#####/...#./..#../.#.../#####",
    "0": ".###./#..##/#.#.#/##..#/.###.",
    "1": "..#../.##../..#../..#../.###.",
    "2": ".###./#...#/..#../.#.../#####",
    "3": "####./....#/.###./....#/####.",
    "4": "#..#./#..#./#####/...#./...#.",
    "5": "#####/#..../####./....#/####.",
    "6": ".###./#..../####./#...#/.###.",
    "7": "#####/....#/...#./..#../..#..",
    "8": ".###./#...#/.###./#...#/.###.",
    "9": ".###./#...#/.####/....#/.###.",
    " ": "...../...../...../...../.....",
    ">": "#..../.#.../..#../.#.../#....",
    ".": "...../...../...../...../..#..",
    "\u00b7": "...../...../..#../...../.....",
    ":": "...../..#../...../..#../.....",
    "?": ".###./#...#/..##./...../..#..",
    "!": "..#../..#../..#../...../..#..",
    "_": "...../...../...../...../#####",
    "-": "...../...../#####/...../.....",
    "'": "..#../..#../...../...../.....",
}

FONT_W = 5      # glyph columns
FONT_H = 5      # glyph rows
ADVANCE = 6     # glyph columns + one blank column
LINE_PITCH = 60  # baseline-to-baseline step at scale 5 (9 lines + footer fit)


# ---------------------------------------------------------------- helpers ----
class Canvas(object):
    """Tiny RGB raster: flat bytearray, clipped rect fills, round-rect windows."""

    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.px = bytearray(w * h * 3)

    def put(self, x, y, rgb):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i] = rgb[0]
            self.px[i + 1] = rgb[1]
            self.px[i + 2] = rgb[2]

    def fill(self, x0, y0, x1, y1, rgb):
        """Inclusive-exclusive hard rect fill, clipped to the canvas."""
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(self.w, x1)
        y1 = min(self.h, y1)
        if x1 <= x0 or y1 <= y0:
            return 0
        row = bytes(rgb) * (x1 - x0)
        for y in range(y0, y1):
            i = (y * self.w + x0) * 3
            self.px[i:i + len(row)] = row
        return (x1 - x0) * (y1 - y0)

    def gradient(self, top, bot):
        for y in range(self.h):
            t = y / float(self.h - 1)
            self.fill(0, y, self.w, y + 1, _mix(top, bot, t))

    def round_rect(self, x0, y0, x1, y1, r, top, bot, alpha_rows=False):
        """Filled rounded rect with a vertical gradient from top to bot."""
        span = float(max(1, y1 - y0 - 1))
        for y in range(y0, y1):
            inset = _corner_inset(y, y0, y1, r)
            left = x0 + inset
            right = x1 - inset
            if right <= left:
                continue
            t = (y - y0) / span
            self.fill(left, y, right, y + 1, _mix(top, bot, t))

    def ring(self, cx, cy, r, rgb):
        rr = r * r
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= rr:
                    self.put(cx + dx, cy + dy, rgb)

    def ink_pixels(self, x0, y0, x1, y1, rgb):
        """Count pixels inside the box that exactly match rgb."""
        n = 0
        for y in range(max(0, y0), min(self.h, y1)):
            for x in range(max(0, x0), min(self.w, x1)):
                i = (y * self.w + x) * 3
                if (self.px[i] == rgb[0] and self.px[i + 1] == rgb[1]
                        and self.px[i + 2] == rgb[2]):
                    n += 1
        return n


def _mix(a, b, t):
    return (
        int(a[0] + (b[0] - a[0]) * t + 0.5),
        int(a[1] + (b[1] - a[1]) * t + 0.5),
        int(a[2] + (b[2] - a[2]) * t + 0.5),
    )


def _corner_inset(y, y0, y1, r):
    """Horizontal inset for row y of a rounded rect (integer, AA-free)."""
    if r <= 0:
        return 0
    if y < y0 + r:
        dy = (y0 + r) - y
    elif y > y1 - 1 - r:
        dy = y - (y1 - 1 - r)
    else:
        return 0
    if dy > r:
        return r
    return r - math.isqrt(max(0, r * r - dy * dy))


def text_width(s, scale):
    """Ink width of a line: 5*scale per glyph plus one blank column between."""
    return (len(s) * ADVANCE - 1) * scale


def fit_scale(s, scale, max_w, min_scale=3):
    """Shrink one step at a time until the line fits max_w."""
    while scale > min_scale and text_width(s, scale) > max_w:
        scale -= 1
    return scale


def draw_text(cv, s, x, y, scale, rgb):
    """Raster the 5x5 font. Returns the tight ink box (x0, y0, x1, y1)."""
    for idx, ch in enumerate(s):
        g = GLYPHS.get(ch)
        if g is None:
            g = GLYPHS["?"]
        gx = x + idx * ADVANCE * scale
        for row in range(FONT_H):
            line = g.split("/")[row]
            for col in range(FONT_W):
                if line[col] == "#":
                    cv.fill(gx + col * scale, y + row * scale,
                            gx + (col + 1) * scale, y + (row + 1) * scale, rgb)
    return (x, y, x + text_width(s, scale), y + FONT_H * scale)


# ----------------------------------------------------------------- layout ----
WIN_X0, WIN_Y0, WIN_X1, WIN_Y1 = 40, 40, 984, 984
WIN_R = 18
TITLEBAR = 76
MARK_X = WIN_X0 + 40           # 80: marker column, fixed so the roles stack
BODY_X = MARK_X + 30           # 110: text starts here, left aligned like a log
TEXT_RIGHT = WIN_X1 - 60       # 924
INNER_W = TEXT_RIGHT - BODY_X  # 814
TITLE = "AGENT.EXE - AUTO-APPROVE: ON"
FOOTER_TEXT = "UNSUPERVISED \u00b7 3S \u00b7 NO APPROVALS"
FOOTER_SCALE = 3
FOOTER_GAP = 22                # pixels of air between the last line and it

# (text, colour, scale, extra gap before the line, plate?, marker colour)
# The marker carries the role: blue = prompt, green = result, red = the damage.
LINES = [
    ("> FIX THE FAILING TEST", PROMPT, 5, 0, False, PROMPT),
    ("READING THE CODEBASE...", GREY, 5, 0, False, GREY),
    ("REWROTE TEST_AUTH.PY", GREEN, 5, 0, False, GREEN),
    ("STILL RED. UNDERSTOOD.", GREEN, 5, 0, False, GREEN),
    ("DELETED TEST_AUTH.PY", GREEN, 5, 0, False, RED),
    ("0 TESTS \u00b7 0 FAILURES", INK, 6, 22, True, INK),
    ("PUSHED TO MAIN", GREEN, 5, 4, False, GREEN),
    ("> WHY DELETE THE OTHER 411?", PROMPT, 5, 26, False, PROMPT),
    ("YOU SAID: MAKE TESTS PASS", BRIGHT, 5, 0, False, BRIGHT),
]

PLATE_INSET_X = 16   # keeps the plate's edge clear of the marker column
PLATE_PAD_Y = 15
PLATE_R = 14


def plan():
    """Resolve scale + y for every line so the block is vertically centred.

    Block height = sum of the glyph heights + one pitch per gap between lines
    + the deliberate group gaps, so nothing can be silently pushed off frame.
    """
    items = []
    for text, colour, scale, gap, plate, marker in LINES:
        s = fit_scale(text, scale, INNER_W)
        if plate:
            s = scale  # the yellow anchor line keeps its size
        items.append({"text": text, "colour": colour, "scale": s, "gap": gap,
                      "plate": plate, "marker": marker, "h": FONT_H * s})
    block = (sum(it["h"] for it in items)
             + LINE_PITCH * (len(items) - 1)
             + sum(it["gap"] for it in items)
             + FOOTER_GAP + FONT_H * FOOTER_SCALE)

    area_top = WIN_Y0 + TITLEBAR + 30
    area_bot = WIN_Y1 - 34
    y = area_top + max(0, (area_bot - area_top - block) // 2)
    for it in items:
        y += it["gap"]
        it["y"] = y
        y += it["h"] + LINE_PITCH
    footer_y = items[-1]["y"] + items[-1]["h"] + FOOTER_GAP
    return items, footer_y


# ------------------------------------------------------------------ chrome ----
def draw_window(cv):
    cv.gradient(DESK_TOP, DESK_BOT)
    # 1px hairline border: fill the rounded rect with border colour, then the
    # same shape inset by 1px with the body gradient so it reads as a hairline.
    cv.round_rect(WIN_X0, WIN_Y0, WIN_X1, WIN_Y1, WIN_R, BORDER, BORDER)
    cv.round_rect(WIN_X0 + 1, WIN_Y0 + 1, WIN_X1 - 1, WIN_Y1 - 1,
                  WIN_R - 1, WIN_TOP, WIN_BOT)
    # window body under the title bar is a touch darker: soft separator only
    cv.fill(WIN_X0 + 2, WIN_Y0 + TITLEBAR, WIN_X1 - 2, WIN_Y0 + TITLEBAR + 1, SEP)

    cy = WIN_Y0 + 37
    cv.ring(WIN_X0 + 34, cy, 9, RED)
    cv.ring(WIN_X0 + 64, cy, 9, AMBER)
    cv.ring(WIN_X0 + 94, cy, 9, TL_GREEN)

    ts = 3
    tw = text_width(TITLE, ts)
    draw_text(cv, TITLE, (W - tw) // 2, WIN_Y0 + 26, ts, DIM)
    return ts


def draw_cursor(cv, x, y, rgb):
    """Solid terminal cursor block trailing the last line."""
    bw, bh = 22, 26
    cv.fill(x, y, x + bw, y + bh, rgb)
    return (x, y, x + bw, y + bh)


def plate_box(text, scale, y):
    tw = text_width(text, scale)
    px0 = MARK_X - PLATE_INSET_X
    px1 = BODY_X + tw + PLATE_INSET_X
    py0 = y - PLATE_PAD_Y
    py1 = y + FONT_H * scale + PLATE_PAD_Y
    return px0, py0, px1, py1


# -------------------------------------------------------------------- main ----
def render():
    cv = Canvas(W, H)
    draw_window(cv)
    items, footer_y = plan()
    boxes = []
    markers = []
    for it in items:
        text = it["text"]
        s = it["scale"]
        y = it["y"]
        if it["plate"]:
            bx = plate_box(text, s, y)
            cv.round_rect(bx[0], bx[1], bx[2], bx[3], PLATE_R, YELLOW, YELLOW)
        # terminal marker: a small rounded square that states the line's role
        mcy = y + (FONT_H * s) // 2
        cv.round_rect(MARK_X, mcy - 7, MARK_X + 16, mcy + 7, 4,
                      it["marker"], it["marker"])
        markers.append((text, (MARK_X, mcy - 7, MARK_X + 16, mcy + 7),
                        it["marker"]))
        box = draw_text(cv, text, BODY_X, y, s, it["colour"])
        it["box"] = box
        boxes.append((text, box, it["colour"], s))
        if text.startswith("YOU SAID"):
            cbox = draw_cursor(cv, box[2] + 16, y + 1, BRIGHT)
            boxes.append(("cursor", cbox, BRIGHT, s))
            # second, thinner block 6 px further right: a double cursor
            dbox = (cbox[2] + 6, cbox[1], cbox[2] + 9, cbox[3])
            cv.fill(dbox[0], dbox[1], dbox[2], dbox[3], BRIGHT)
            boxes.append(("cursor2", dbox, BRIGHT, s))
    fbox = draw_text(cv, FOOTER_TEXT, BODY_X, footer_y, FOOTER_SCALE, FOOTER_C)
    boxes.append(("footer", fbox, FOOTER_C, FOOTER_SCALE))
    return cv, boxes, items, footer_y, markers


def write_png(path, cv):
    raw = bytearray()
    stride = cv.w * 3
    for y in range(cv.h):
        raw.append(0)  # filter type 0 (None) per scanline
        raw += cv.px[y * stride:(y + 1) * stride]
    body = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", cv.w, cv.h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", body)
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)
    return len(png)


def verify(cv, boxes, items, footer_y, markers):
    """Fail loudly if any line is blank or pokes out of the window frame.

    Clearance everywhere is 20 px of clean window inside the hairline border,
    which is what keeps the composition from looking cramped on a phone.
    """
    left, right = WIN_X0 + 20, WIN_X1 - 20
    top, bot = WIN_Y0 + TITLEBAR + 8, WIN_Y1 - 20
    report = []
    for name, (x0, y0, x1, y1), colour, s in boxes:
        ink = cv.ink_pixels(x0, y0, x1, y1, colour)
        assert ink > 0, "blank line: %r" % name
        assert x0 >= left and x1 <= right, "horizontal clip: %r %s" % (name, (x0, x1))
        assert y0 >= top and y1 <= bot, "vertical clip: %r %s" % (name, (y0, y1))
        report.append("%-28s s=%d ink=%5d box=%s" % (name, s, ink, (x0, y0, x1, y1)))

    assert len(markers) == len(items), "a line lost its marker"
    for text, mbox, colour in markers:
        assert cv.ink_pixels(mbox[0], mbox[1], mbox[2], mbox[3], colour) > 100, \
            "marker missing: %r" % text
    red_marker = [m for m in markers if m[2] == RED]
    assert len(red_marker) == 1 and red_marker[0][0].startswith("DELETED"), \
        "the deletion line must be the only red marker"
    report.append("markers: %d, red on %r" % (len(markers), red_marker[0][0]))

    last = items[-1]
    assert footer_y - (last["y"] + last["h"]) == FOOTER_GAP, "footer gap wrong"
    assert footer_y + FONT_H * FOOTER_SCALE <= WIN_Y1 - 20, "footer too low"
    report.append("clearance under footer: %d px"
                  % (WIN_Y1 - (footer_y + FONT_H * FOOTER_SCALE)))

    for it in items:
        if not it["plate"]:
            continue
        px0, py0, px1, py1 = plate_box(it["text"], it["scale"], it["y"])
        assert px0 >= left and px1 <= right, "plate horizontal clip"
        assert py0 >= top and py1 <= bot, "plate vertical clip"
        assert cv.ink_pixels(px0, py0, px1, py1, YELLOW) > 1000, "plate not solid"
        report.append("plate box=%s" % ((px0, py0, px1, py1),))
    return report


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(out_dir, exist_ok=True)
    cv, boxes, items, footer_y, markers = render()
    report = verify(cv, boxes, items, footer_y, markers)
    path = os.path.join(out_dir, "entry.png")
    size = write_png(path, cv)
    print("wrote %s  %dx%d  %d bytes" % (path, cv.w, cv.h, size))
    for line in report:
        print("  " + line)


if __name__ == "__main__":
    main()
