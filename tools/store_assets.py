"""Context Ahead: Connect IQ Store images.

    SAIRA_FONT_DIR=/path/to/saira python3 tools/store_assets.py

Writes store/: app-icon-500.png, hero-1440x720.png, anatomy-1440x900.png and four screenshots (1440 x 900):
01 themes, circle and bar; 02 spring; 03 summer; 04 autumn and winter.
Every Context message shown is the watch engine's own output for that situation: tools/check/extract.cjs runs the
transpiled Context.mc on the simulation cases and writes tools/check/store_states.json. The faces are drawn with
the face's bitmap fonts and coordinates (tools/preview.py).
"""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont
TOOLS = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import preview as P

OUT = os.path.join(PROJ, "store")
os.makedirs(OUT, exist_ok=True)
FD = os.environ.get("SAIRA_FONT_DIR", os.path.join(TOOLS, "fonts"))
ST = json.load(open(os.path.join(TOOLS, "check", "store_states.json"), encoding="utf-8"))

WHITE = (245, 244, 240)
GREY = (176, 181, 186)
DIM = (120, 126, 132)
ORANGE = P.ORANGE
W, H = 1440, 900


def fb(size, wt="Bold"):
    return ImageFont.truetype(os.path.join(FD, f"SairaSemiCondensed-{wt}.ttf"), size)


MON = {"Jan": 31, "Feb": 28, "Mar": 31, "Apr": 30, "May": 31, "Jun": 30, "Jul": 31, "Aug": 31, "Sep": 30,
       "Oct": 31, "Nov": 30, "Dec": 31}


def state(key, circle=None, bar=("G_STEPS", 64, "%"), awake=False):
    """The face for a harness case: its message, clock and date exactly as the engine and the sim had them."""
    s = ST[key]
    dow, day, mon, _ = s["date"].replace(",", "").split()
    if circle is None:
        circle = ("date", dow.upper(), int(day), mon.upper(), int(day) / MON[mon])
    lines = (s["l1"], s["l2"], s["e1"])                 # the third line shows only on a wrist raise
    im, hidden = P.face(signal=(s["icon"], s["word"], s["detail"]), lines=lines,
                        fresh=f"{s['wAge']} MIN AGO", clock="%02d:%02d" % divmod(s["localMin"], 60),
                        circle=circle, bar=bar, invert=s["inv"], awake=awake)
    assert hidden == 0, (key, hidden)
    return im


def ctext(d, x, y, text, f, fill):
    d.text((x - d.textlength(text, font=f) / 2, y), text, font=f, fill=fill)


def wrap(d, text, f, width):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            out.append(cur)
            cur = w
    return out + [cur]


def footer(c, text="One message at a time. The time stays untouched. Raise your wrist for one more fact."):
    d = ImageDraw.Draw(c)
    d.line((84, 812, W - 84, 812), fill=(58, 62, 66), width=2)
    ctext(d, W // 2, 832, text, fb(22, "SemiBold"), DIM)


def header(d, kicker, title, sub):
    d.text((84, 54), kicker, font=fb(24), fill=ORANGE)
    d.text((80, 84), title, font=fb(58), fill=WHITE)
    d.text((84, 160), sub, font=fb(25, "SemiBold"), fill=GREY)


def three(canvas, items, y=224, light=()):
    """Three faces at 2x (as on a wrist raise) with a place line and a sentence."""
    d = ImageDraw.Draw(canvas)
    gap = (W - 3 * 384) // 4
    for i, (img, place, says, raise_) in enumerate(items):
        x = gap + i * (384 + gap)
        sc = P.screen(img, 2, pad=8, light=i in light)
        canvas.paste(sc, (x, y), sc)
        cx = x + 192
        ctext(d, cx, y + 404, place, fb(24), ORANGE)
        for k, ln in enumerate(wrap(d, says, fb(22, "SemiBold"), 380)):
            ctext(d, cx, y + 440 + 30 * k, ln, fb(22, "SemiBold"), WHITE)
        if raise_:
            ctext(d, cx, y + 510 + 30 * (len(wrap(d, says, fb(22, "SemiBold"), 380)) - 2), "RAISE: " + raise_,
                  fb(18, "SemiBold"), DIM)


# ------------------------------------------------------------------ 01 themes, circle, bar
def shot_themes():
    c = P.gradient((W, H))
    d = ImageDraw.Draw(c)
    header(d, "MAKE IT YOURS", "Dark or light. Your circle, your bar.",
           "Context keeps to its own lines. The circle and the bar under the time are yours to fill.")
    face = state("02.4", circle=("metric", "I_BOLT", "72", "BB", 72), bar=("G_STEPS", 64, "%"))
    for i, light in enumerate((False, True)):
        sc = P.screen(face, 2, pad=8, light=light)
        x = 70 + i * 404
        c.paste(sc, (x, 236), sc)
        ctext(d, x + 192, 640, "DARK" if not light else "LIGHT", fb(24), ORANGE)
    ctext(d, 70 + 394, 680, "Same face, same pixels: the theme only swaps ink and paper.", fb(21, "SemiBold"), GREY)
    # circle options, cropped from real renders
    d.text((900, 236), "CIRCLE", font=fb(26), fill=ORANGE)
    d.text((1010, 240), "15 readings or off. Date by default.", font=fb(21, "SemiBold"), fill=GREY)
    opts = [("DATE", ("date", "MON", 20, "JUL", 20 / 31)), ("WEATHER", ("wxnow", "W_PARTLY", "28", 40)), ("PRESSURE", ("metric", "F_BARO", "1013", "HPA", None)),
            ("MOON", ("metric", "N_MOON", "38", "LIT %", 36)), ("STEPS", ("metric", "G_STEPS", "8432", "STEPS", 84)),
            ("INTENSITY", ("metric", "G_INT", "35", "TODAY", 80)), ("INT. WEEK", ("metric", "F_WEEK", "120", "WEEK", 80)),
            ("HEART", ("metric", "I_HEART", "62", "BPM", None)), ("BODY BATT.", ("metric", "I_BOLT", "72", "BB", 72)),
            ("STRESS", ("metric", "G_STRESS", "28", "STRESS", 28)), ("ALTITUDE", ("metric", "F_MOUNT", "1840", "M", None)),
            ("BATTERY", ("metric", "F_BATT", "12", "DAYS", 64)), ("SOLAR", ("metric", "G_SOLAR", "45", "SOLAR", 45)),
            ("NOTIFS", ("metric", "F_MAIL", "3", "NEW", None)), ("SECONDS", ("sec", "42"))]
    for k, (name, circ) in enumerate(opts):
        im, _ = P.face(signal=(None, "", ""), lines=("", ""), fresh="", clock="10:08", circle=circ, bar=None)
        crop = im.crop((112, 0, 176, 64))
        big = crop.resize((96, 96), Image.NEAREST).convert("L")
        tile = Image.new("RGB", (96, 96), P.DARK_BG)
        tile.paste(Image.new("RGB", (96, 96), P.DARK_INK), (0, 0), big)
        x, y = 900 + (k % 4) * 128, 282 + (k // 4) * 124
        m = Image.new("L", (96, 96), 0)
        ImageDraw.Draw(m).ellipse((0, 0, 95, 95), fill=255)
        c.paste(tile, (x, y), m)
        ImageDraw.Draw(c).ellipse((x - 3, y - 3, x + 98, y + 98), outline=ORANGE, width=2)
        ctext(d, x + 48, y + 100, name, fb(15), GREY)
    # bar options
    d.text((900, 790), "BAR", font=fb(26), fill=ORANGE)
    d.text((960, 794), "steps, floors, intensity day or week, move,", font=fb(21, "SemiBold"), fill=GREY)
    d.text((960, 822), "Body Battery, stress, battery, solar, or off", font=fb(21, "SemiBold"), fill=GREY)
    d.text((84, 726), "ALSO ON THE WATCH", font=fb(22), fill=ORANGE)
    d.text((84, 756), "Time format  ·  weather every 5 min to 2 h  ·  EU or US air index  ·  pollen", font=fb(21, "SemiBold"),
           fill=GREY)
    c.save(os.path.join(OUT, "screenshot-01-make-it-yours.png"), optimize=True)


# ------------------------------------------------------------------ 02-04 Context across the year
def shot_spring():
    c = P.gradient((W, H))
    header(ImageDraw.Draw(c), "SPRING", "Showers, with a start time you can trust.",
           "Minutes where the model is truly 15-minute. \"BY 16:00\" where it is hourly. Never fake precision.")
    three(c, [
        (state("09", awake=True), "APRIL  ·  BUCHAREST", "Rain by 16:00 (not before 15:00), how much, and when it is dry again.", ""),
        (state("07", awake=True, circle=("metric", "I_BOLT", "64", "BB", 64), bar=("G_STEPS", 42, "%")),
         "MAY  ·  ON THE LAKE", "Gusts building from 18 to 43 km/h. Worth knowing before you paddle out.", ""),
        (state("33", awake=True, circle=("metric", "F_MOUNT", "2010", "M", None), bar=("F_WEEK", 80, "%")),
         "MOUNTAIN TRAIL  ·  2000 M", "Rain by 13:00, and above 2200 m it falls as snow.", ""),
    ], light=(1,))
    footer(c)
    c.save(os.path.join(OUT, "screenshot-02-spring.png"), optimize=True)


def shot_summer():
    c = P.gradient((W, H))
    header(ImageDraw.Draw(c), "SUMMER", "When it needs you now, the clock inverts.",
           "Storms and dangerous heat take over the time. Everything else waits its turn, quietly.")
    three(c, [
        (state("04", awake=True, circle=("metric", "I_HEART", "88", "BPM", None), bar=("G_STRESS", 46, "")),
         "JULY  ·  MUNICH", "Thunderstorm within the hour, gusts to 68 km/h, over by about 19:00.", ""),
        (state("01", awake=True, circle=("temp", "39°")), "JULY  ·  BUCHAREST",
         "Dry heat counts too: the higher of air temperature and heat index.", ""),
        (state("23.1", awake=True, bar=("G_STEPS", 30, "%")), "JULY  ·  MORNING",
         "UV 8 or more until about 16:00. Sunscreen, or wait for the shade.", ""),
    ], light=(2,))
    footer(c)
    c.save(os.path.join(OUT, "screenshot-03-summer.png"), optimize=True)


def shot_winter():
    c = P.gradient((W, H))
    header(ImageDraw.Draw(c), "AUTUMN & WINTER", "Short days, honest about the dark.",
           "Daylight left, freezing fog, snow totals. Each one says when it ends.")
    three(c, [
        (state("14b", awake=True, bar=("G_STEPS", 88, "%")), "OCTOBER  ·  EVENING RUN",
         "25 minutes of sun left, then civil dusk at 19:02.", ""),
        (state("15", awake=True, circle=("metric", "N_MOON", "64", "LIT %", 55), bar=("G_BB", 58, "")),
         "DECEMBER  ·  MORNING", "Freezing fog at -2°, 300 m visibility, lifting about 10:00.", ""),
        (state("16", awake=True, bar=("G_BATT", 70, "%")), "JANUARY  ·  SNOW DAY",
         "7.2 cm over the next six hours, easing about 16:00.", ""),
    ], light=(0,))
    footer(c)
    c.save(os.path.join(OUT, "screenshot-04-autumn-winter.png"), optimize=True)


# ------------------------------------------------------------------ hero, icon, anatomy
def hero():
    c = P.gradient((1440, 720))
    d = ImageDraw.Draw(c)
    d.text((70, 52), "CONTEXT AHEAD", font=fb(72), fill=WHITE)
    d.text((74, 140), "One line about the weather and the light, only when it changes what you do next.",
           font=fb(27, "SemiBold"), fill=GREY)
    items = [(state("02.4", circle=("date", "MON", 20, "JUL", 20 / 31)), False, "CALM DAY"),
             (state("14", circle=("temp", "11°"), bar=("G_BB", 72, "")), True, "RAIN IN 15 MIN"),
             (state("39", circle=("date", "THU", 15, "JAN", 15 / 31), bar=("G_STEPS", 20, "%")), False, "ACT NOW")]
    for i, (img, light, cap) in enumerate(items):
        sc = P.screen(img, 2, pad=8, light=light)
        x = 70 + i * 450
        c.paste(sc, (x, 224), sc)
        ctext(d, x + 192, 622, cap, fb(24), ORANGE)
    d.text((70, 668), "Free  ·  Instinct 3 Solar 45 mm  ·  Forecast by Open-Meteo, the watch's own barometer when offline",
           font=fb(20, "SemiBold"), fill=DIM)
    c.save(os.path.join(OUT, "hero-1440x720.png"), optimize=True)


COVER_STYLE = "topo"      # the chosen cover background (see cover_background)


def cover_background(style, S=500):
    """The cover's background, 500 x 500. glow: dark with an orange glow around the watch. disc: a large orange
    disc behind the watch on charcoal. split: charcoal and orange divided on the diagonal. topo: burnt orange with
    darker contour lines, like a map."""
    import math
    import numpy as np
    cx = cy = S // 2
    yy, xx = np.mgrid[0:S, 0:S]
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    dark = np.array([16, 15, 16])
    org = np.array(ORANGE)
    if style == "disc":
        img = np.zeros((S, S, 3)) + dark
        disc = r <= 236
        img[disc] = org
        img[(r > 236) & (r <= 240)] = (120, 44, 14)
        img[r < 214] = (170, 60, 20)                    # darker inside, under the case, so the disc reads as a ring
    elif style == "split":
        t = ((xx + yy) / (2.0 * S))[..., None]
        img = np.where(xx + yy > S - 40, 1.0, 0.0)[..., None] * org + np.where(xx + yy > S - 40, 0.0, 1.0)[..., None] * dark
        img = img * (1 - 0.18 * t)
        band = np.abs(xx + yy - (S - 40)) <= 3
        img[band] = (250, 150, 90)
    elif style == "topo":
        img = np.zeros((S, S, 3)) + np.array([206, 82, 28])
        # contour lines of a made-up hill, one every 0.12 of its height
        h = (np.exp(-((xx - 120) ** 2 + (yy - 400) ** 2) / 26000.0) * 1.0
             + np.exp(-((xx - 430) ** 2 + (yy - 90) ** 2) / 18000.0) * 0.8
             + 0.15 * np.sin(xx / 47.0) * np.cos(yy / 61.0))
        frac = (h / 0.08) % 1.0
        img[(frac < 0.07)] = (160, 56, 16)
    else:
        t = (yy / S)[..., None]
        base = np.array([16, 14, 14]) * (1 - t) + np.array([44, 20, 10]) * t
        glow = (np.clip(1.0 - (r - 190) / 150.0, 0, 1) ** 1.5)[..., None]    # strongest just outside the case
        img = base * (1 - 0.7 * glow) + org * 0.7 * glow
    return Image.fromarray(np.clip(img, 0, 255).astype("uint8"), "RGB")


def watch_on(c, light=False):
    """The face at 2x in a drawn watch case: rounded octagon, lighter rim with a thin orange line, round lens,
    screws on the chamfers, orange lens accents at 12 and 6 o'clock. Centred on c."""
    S = c.width
    cx, cy = S // 2, S // 2
    d = ImageDraw.Draw(c)

    def octagon(rx, ch):
        return [(cx - rx + ch, cy - rx), (cx + rx - ch, cy - rx), (cx + rx, cy - rx + ch), (cx + rx, cy + rx - ch),
                (cx + rx - ch, cy + rx), (cx - rx + ch, cy + rx), (cx - rx, cy + rx - ch), (cx - rx, cy - rx + ch)]
    d.polygon(octagon(194, 62), fill=(6, 6, 7))
    d.polygon(octagon(191, 60), fill=(56, 57, 60))
    d.line(octagon(188, 59) + [octagon(188, 59)[0]], fill=(214, 84, 30), width=2)   # thin orange rim
    d.polygon(octagon(184, 56), fill=(34, 35, 38))
    d.ellipse((cx - 180, cy - 180, cx + 180, cy + 180), fill=(8, 8, 9))            # the round lens
    for sgn in (-1, 1):                                                             # orange accents at 12 and 6
        yb = cy + sgn * 188
        d.rounded_rectangle((cx - 58, yb - 9, cx + 58, yb + 9), radius=5, fill=(6, 6, 7))   # dark seat
        d.rounded_rectangle((cx - 56, yb - 7, cx + 56, yb + 7), radius=4, fill=ORANGE)
        d.rectangle((cx - 56, yb + (2 if sgn < 0 else -7), cx + 56, yb + (7 if sgn < 0 else -2)), fill=(190, 66, 20))
    for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):                             # screws on the chamfers
        px, py = cx + sx * 156, cy + sy * 156
        d.ellipse((px - 8, py - 8, px + 8, py + 8), fill=(64, 66, 70))
        d.ellipse((px - 3, py - 3, px + 3, py + 3), fill=(18, 18, 20))
    face = state("04", circle=("wxnow", "W_STORM", "24", 80), bar=("G_STEPS", 64, "%"))
    sc = P.screen(face, 2, pad=8, light=light, bezel=False)
    c.paste(sc, (cx - sc.width // 2, cy - sc.height // 2), sc)
    return c


def cover(style=None, name="cover-500.png"):
    """Store cover (web and mobile): 500 x 500, under 300 KB. No title: the store shows the name next to it."""
    c = watch_on(cover_background(style or COVER_STYLE))
    c.save(os.path.join(OUT, name), optimize=True)


def app_icon():
    """125 x 125 (drawn at 500, scaled once): the face's three marks, large enough to read at 60 px. The rain cloud from the face's own icon
    font (the Signal), the orange ring (the circle) and the meter cells (the bar)."""
    S = 500
    c = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=104, fill=(14, 15, 16, 255))
    # the circle, top right
    d.ellipse((300, 44, 456, 200), outline=ORANGE + (255,), width=14)
    # the Signal: the cloud glyph in big pixels
    cv = P.Canvas()
    cv.icon("W_RAIN", 0, 0)
    ys, xs = cv.A.nonzero()
    g = cv.A[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    k = 9
    gw, gh = g.shape[1] * k, g.shape[0] * k
    ox, oy = 60, 290 - gh // 2 - 30
    for (y, x) in zip(*g.nonzero()):
        d.rectangle((ox + x * k, oy + y * k, ox + x * k + k - 1, oy + y * k + k - 1), fill=P.DARK_INK + (255,))
    # the bar: ten cells, six lit
    for i in range(10):
        x = 60 + i * 38
        if i < 6:
            d.rectangle((x, 404, x + 32, 422), fill=P.DARK_INK + (255,))
        else:
            d.rectangle((x, 416, x + 32, 422), fill=P.DARK_INK + (255,))
    # the store wants it at most 125 x 125: drawn large, then scaled down once
    c.resize((125, 125), Image.LANCZOS).save(os.path.join(OUT, "app-icon-125.png"), optimize=True)


def anatomy():
    S = 4
    img = state("14", circle=("date", "TUE", 20, "OCT", 20 / 31), bar=("G_BB", 72, ""))
    c = P.gradient((W, H))
    d = ImageDraw.Draw(c)
    d.text((70, 40), "ANATOMY", font=fb(48), fill=WHITE)
    sc = P.screen(img, S, pad=8)
    ox, oy = 60, 112
    c.paste(sc, (ox, oy), sc)
    # numbered markers on the face itself (face pixel coordinates), placed beside each zone
    marks = [(1, 30, 22), (2, 4, 53), (3, 110, 10), (4, 7, 92), (5, 158, 119), (6, 6, 136), (7, 30, 155)]
    for n, fx, fy in marks:
        x, y = ox + 8 + fx * S, oy + 8 + fy * S
        r = 22
        d.ellipse((x - r - 3, y - r - 3, x + r + 3, y + r + 3), fill=(14, 15, 16))
        d.ellipse((x - r, y - r, x + r, y + r), fill=ORANGE)
        ctext(d, x, y - 17, str(n), fb(28), (14, 15, 16))
    notes = [("FORECAST AGE", "How old the forecast is, or why there is none: NO PHONE, NO GPS."),
             ("SIGNAL", "The one message that matters most right now: a word, its detail, an icon."),
             ("CIRCLE  ·  YOURS", "Weekday and date by default, with an arc for the month. Or temperature, heart rate, Body Battery, altitude, moon, "
                                  "battery days, notifications, seconds."),
             ("TIME", "Large and untouched. It inverts only when something needs acting on now."),
             ("BAR  ·  YOURS", "Steps, floors, intensity, move, Body Battery, stress, battery, solar."),
             ("HOW MUCH", "The amount, the chance or the strength."),
             ("WHEN IT CHANGES", "When it stops, eases, or what follows.")]
    y = 100
    for k, (head, body) in enumerate(notes):
        x = 830
        d.ellipse((x, y + 2, x + 34, y + 36), fill=ORANGE)
        ctext(d, x + 17, y + 1, str(k + 1), fb(23), (14, 15, 16))
        d.text((x + 50, y), head, font=fb(26), fill=WHITE)
        lines = wrap(d, body, fb(20, "SemiBold"), 520)
        for j, ln in enumerate(lines):
            d.text((x + 50, y + 34 + 26 * j), ln, font=fb(20, "SemiBold"), fill=GREY)
        y += 44 + 26 * len(lines) + 6
    d.text((830, y + 6), "RAISE YOUR WRIST", font=fb(26), fill=ORANGE)
    for j, ln in enumerate(wrap(d, "One more fact appears under line 7 (here: THEN DRY ~17:00), and the "
                                   "bar shows its value on the right. Nothing on screen is replaced.", fb(20, "SemiBold"), 560)):
        d.text((830, y + 40 + 26 * j), ln, font=fb(20, "SemiBold"), fill=GREY)
    c.save(os.path.join(OUT, "anatomy-1440x900.png"), optimize=True)


if __name__ == "__main__":
    for f in os.listdir(OUT):
        if f.endswith(".png"):
            os.remove(os.path.join(OUT, f))
    shot_themes()
    shot_spring()
    shot_summer()
    shot_winter()
    hero()
    cover()
    app_icon()
    anatomy()
    print("store images written to", OUT, sorted(f for f in os.listdir(OUT) if f.endswith(".png")))
