"""Context engine, two versions side by side.

v1 = CONTEXT.md Draft 1 as written (and as Solar Frontier 1.9 does rain): tiers decide, soonest wins inside a tier,
     forecasts trusted for 12 h, 15-minute data used for minutes everywhere, Beaufort labels, CAPE storms.
v2 = the revision proposed after the judgment audit, with the adjustments in REPORT.md: evidence and precision
     gates before ranking, one rain timeline at the real resolution, hysteresis, event identity, cooldown for
     persistent advisories, and a Quiet scheduler.

Every candidate records why it exists; every rejection records why it does not. Nothing here is watch code.
"""
from dataclasses import dataclass, field
from datetime import timedelta
from data import H, Q, EUROPE, in_box, heat_index_c, wind_chill_c

GUST1_IN, GUST1_OUT = 65.0, 58.0       # km/h, v2 act-now gusts (enter / leave)
GUST5_IN, GUST5_OUT = 50.0, 45.0       # km/h, v2 worth-adapting gusts
HEAT1_IN, HEAT1_OUT = 40.0, 38.0       # °C, effective heat = max(air, heat index)
HEAT5_IN, HEAT5_OUT = 33.0, 31.0
MAX_AGE = {1: 90, 3: 90, 5: 240, 6: 720, "aq": 180}     # minutes since the last successful fetch, v2
WET_H = 0.3            # mm in an hour block: a wet hour (v2)
WET_Q = 0.1            # mm in a 15-minute block (native data only)
MIN_DRY = 90           # minutes: a dry gap shorter than this is not "dry" (v2)
HEAVY_H = 7.6          # mm/h, heavy rain (v2)
# Inside a tier: which family usually changes the next decision more. A ranking, not a risk score.
FAMILY_RANK = {"STORM": 0, "ICE": 1, "SNOW": 2, "FOG": 3, "COLD": 4, "HEAT": 5, "RAIN": 6, "TEMP": 7, "GUST": 8,
               "AIR": 9, "FROST": 10, "UV": 11, "DUST": 12, "POLLEN": 13, "HOTNIGHT": 14, "BARO": 15}
PERSISTENT = {"UV", "AIR", "DUST", "POLLEN", "HEAT5", "GUST5"}
HOLD_MIN, REMIND_MIN = 60, 120


@dataclass
class Cand:
    id: str
    family: str
    tier: int
    word: str
    detail: str
    line1: str
    line2: str
    ev1: str = ""
    ev2: str = ""
    sev: float = 0.0               # severity inside the family, bigger = worse
    onset_min: float = 0.0         # minutes until it starts (0 = now)
    event: str = ""                # identity, stable across re-fetches
    basis: str = "forecast"        # forecast / derived / watch / astronomy
    invert: bool = False


@dataclass
class Result:
    chosen: Cand
    cands: list
    rejected: list


def hhmm(dt):
    return dt.strftime("%H:%M")


def r5(m):
    return int((m + 2) // 5 * 5)


# =====================================================================================================  shared reads

class Ctx:
    def __init__(self, s, v):
        self.s, self.v = s, v
        self.f = s.fetch
        self.rej = []
        self.cands = []
        self.native = s.res == "native15"

    # ---- data validity
    def fc_ok(self, tier):
        f = self.f
        if f is None or not f.ok or not f.hours:
            return False
        if self.v == 1:
            return f.age_min <= 720
        if f.age_min > (720 if getattr(self, "relaxed", False) else MAX_AGE[tier]):
            return False
        if tier in (1, 3) and self.s.fc_dist_km > 25:
            return False
        return True

    def why_not(self, tier):
        f = self.f
        if f is None or not f.ok:
            return "no forecast (" + (f.error if f else "never fetched") + ")"
        if f.age_min > MAX_AGE[tier]:
            return f"forecast {int(f.age_min)} min old > {MAX_AGE[tier]} for tier {tier}"
        if self.s.fc_dist_km > 25:
            return f"forecast point {self.s.fc_dist_km:.0f} km from the watch"
        return "?"

    def reject(self, mid, why):
        self.rej.append((mid, why))

    def add(self, c):
        self.cands.append(c)

    # ---- series
    def hours(self):
        return self.f.hours if self.f else []

    def block(self, t):
        """The hour whose preceding-hour interval contains t."""
        for h in self.hours():
            if h.t - H < t <= h.t:
                return h
        return None

    def inst(self, t):
        """Instant fields: the stamp nearest to t."""
        hs = self.hours()
        return min(hs, key=lambda h: abs(h.t - t)) if hs else None

    def ahead(self, hours):
        now = self.s.ts
        return [h for h in self.hours() if now < h.t <= now + hours * H + H - 1]

    def loc(self, t):
        return self.s.local(t)

    def at(self, t, approx=True):
        """A forecast time at its real precision: hourly data -> nearest hour, native -> nearest quarter."""
        step = Q if (self.native or self.v == 1) else H
        tt = int(round(t / step) * step)
        return ("~" if approx else "") + hhmm(self.loc(tt))

    def src(self):
        f = self.f
        age = int(f.age_min)
        a = f"{age}M" if age < 60 else f"{age // 60}H"
        if self.v == 1:
            return f"FCST {a}"
        return ("MODEL 15MIN " if self.native else "MODEL HOURLY ") + a

    # ---- watch pressure
    def baro_change(self, hours=3):
        """(drop_hpa, stationary, reason). Drop > 0 means falling. v2 refuses a weather reading when the watch
        climbed or descended more than 30 m, or when the record has a gap over 30 min."""
        p = self.s.baro.press
        if len(p) < 2 or p[-1][0] - p[0][0] < hours * H * 0.9:
            return None, False, "pressure record shorter than 3 h"
        gaps = max(b[0] - a[0] for a, b in zip(p, p[1:]))
        drop = p[0][1] - p[-1][1]
        if self.v == 1:
            return drop, True, ""
        if gaps > 1800:
            return drop, False, "pressure record has a gap over 30 min"
        e = self.s.baro.elev
        if not e:
            return drop, False, "no elevation history to rule out a climb"
        moved = max(x[1] for x in e) - min(x[1] for x in e)
        if moved > 30:
            return drop, False, f"watch moved {moved:.0f} m in height: pressure change is mostly altitude"
        return drop, True, ""


# =====================================================================================================  rain timeline

def rain_timeline(c, hours=12):
    """One rain truth: a list of (start, end, mm, snow_cm, prob) wet spells, at the resolution that is real here.
    v1: SF behaviour, 15-minute blocks everywhere (interpolated or not), wet from 0.1 mm per block, then hourly.
    v2: native 15-min blocks only where native; otherwise hourly blocks; wet from WET_H per hour; spells separated
        by dry gaps under MIN_DRY are merged; probability is the hourly ensemble value of the spell's hours."""
    now = c.s.ts
    blocks = []                                   # (start, end, mm, snow, prob)
    use_q = c.f.m15 and (c.v == 1 or c.native)
    q_end = now
    if use_q:
        for t, mm in c.f.m15:
            h = c.block(t)
            blocks.append((t - Q, t, mm, (h.snow / 4) if h else 0.0, h.prob if h else None))
        q_end = c.f.m15[-1][0]
    for h in c.hours():
        if h.t <= max(now, q_end) or h.t > now + hours * H + H:
            continue
        blocks.append((h.t - H, h.t, h.precip, h.snow, h.prob))
    if not blocks:
        return [], []
    wet = []
    for b in blocks:
        thr = (WET_Q if b[1] - b[0] == Q else (0.1 if c.v == 1 else WET_H))
        if c.v == 1 and b[1] - b[0] == H:
            h = c.block(b[1])
            w = h is not None and h.code >= 51            # SF: hourly weather code after the 15-min data
        else:
            w = b[2] >= thr
        wet.append(w)
    spells = []
    cur = None
    for b, w in zip(blocks, wet):
        if w:
            if cur and (c.v == 1 and b[0] > cur[1]):
                spells.append(cur); cur = None
            if cur and c.v == 2 and b[0] - cur[1] >= MIN_DRY * 60:
                spells.append(cur); cur = None
            if cur is None:
                cur = [b[0], b[1], b[2], b[3], b[4] or 0]
            else:
                cur[1] = b[1]; cur[2] += b[2]; cur[3] += b[3]; cur[4] = max(cur[4], b[4] or 0)
        elif cur and c.v == 1:
            spells.append(cur); cur = None
    if cur:
        spells.append(cur)
    return spells, blocks


# =====================================================================================================  messages

def gusts(c):
    if not c.fc_ok(5 if c.v == 2 else 1):
        c.reject("GUST", c.why_not(5)); return
    now = c.s.ts
    cur_h = c.block(now + 1)
    nxt = c.ahead(1)
    g_now = cur_h.gust if cur_h else 0
    g1 = max([g_now] + [h.gust for h in nxt])
    w = c.inst(now).wind
    if c.v == 1:
        if g1 >= 62:
            c.add(Cand("GUST1", "GUST", 1, "GUST", f"{g1:.0f} KMH", f"WIND {w:.0f} GUST F8", "PRESSURE --",
                       f"GUST {g1:.0f}", c.src(), sev=g1, invert=True, event="GUST1"))
        elif g1 >= 50:
            c.add(Cand("GUST5", "GUST", 5, "GUST", f"{g1:.0f} KMH", f"WIND {w:.0f} GUST F7", "",
                       f"GUST {g1:.0f}", c.src(), sev=g1, event="GUST5"))
        return
    was = c.state.get("level", {}).get("GUST", 0)
    level = 0
    if g1 >= GUST1_IN or (was == 1 and g1 >= GUST1_OUT):
        level = 1
    elif g1 >= GUST5_IN or (was in (1, 5) and g1 >= GUST5_OUT):
        level = 5
    if level == 0:
        if g1 >= GUST5_OUT:
            c.reject("GUST", f"gust {g1:.0f} km/h below entry {GUST5_IN:.0f} (not already active)")
        return
    if level == 1 and not c.fc_ok(1):
        c.reject("GUST1", c.why_not(1) + ": strong gusts kept as tier 5, not act-now")
        level = 5
    out = GUST1_OUT if level == 1 else GUST5_OUT
    ease = next((h for h in c.hours() if h.t > now + H and h.gust < out), None)
    l2 = ("EASING " + c.at(ease.t - H)) if ease else "NO EASING IN 12H"
    tier = 1 if level == 1 else 5
    c.add(Cand(f"GUST{level}", "GUST", tier, "GUST", f"{g1:.0f} KMH", f"WIND {w:.0f}  GUSTS {g1:.0f}", l2,
               f"MODEL GUST MAX/HOUR {g1:.0f}", c.src(), sev=g1, invert=tier == 1, event=f"GUST{level}",
               basis="forecast"))
    c.state.setdefault("level_new", {})["GUST"] = level


def wind_rising(c):
    if c.v == 1:
        return
    if not c.fc_ok(5):
        c.reject("WINDUP", c.why_not(5)); return
    now = c.s.ts
    cur = c.block(now + 1)
    if not cur:
        return
    nxt = c.ahead(3)
    if not nxt:
        return
    peak = max(nxt, key=lambda h: h.gust)
    if cur.gust >= GUST5_IN:
        c.reject("WINDUP", "already strong: GUST covers it"); return
    if peak.gust - cur.gust >= 20 and peak.gust >= 40:
        c.add(Cand("WINDUP", "GUST", 5, "WIND", "RISING", f"GUSTS {cur.gust:.0f} TO {peak.gust:.0f}",
                   "STRONGER " + c.at(peak.t - H), f"+{peak.gust - cur.gust:.0f} KMH IN 3H", c.src(),
                   sev=peak.gust - 10, onset_min=(peak.t - H - now) / 60, event="WINDUP"))
    elif peak.gust - cur.gust >= 10:
        c.reject("WINDUP", f"gusts rise only {peak.gust - cur.gust:.0f} km/h or stay under 40")


def storm(c):
    now = c.s.ts
    drop, stat, why = c.baro_change()
    if c.v == 1:
        if not c.fc_ok(1):
            return
        soon = [h for h in c.ahead(2) if h.code >= 95 or h.cape >= 1000]
        if drop is not None and drop >= 6 and soon:
            c.add(Cand("STORM1", "STORM", 1, "STORM", "SIGNS", f"BARO ▼{drop:.1f} IN 3H", "HIGH RISK", "",
                       c.src(), sev=9, invert=True, event="STORM1"))
            return
        six = [h for h in c.ahead(6) if h.cape >= 1000 or h.code >= 95]
        if six:
            h = six[0]
            c.add(Cand("STORM5", "STORM", 5, "STORM", c.at(h.t - H), "T-STORMS POSSIBLE", "", f"CAPE {h.cape:.0f}",
                       c.src(), sev=5, onset_min=(h.t - H - now) / 60, event="STORM5"))
        return
    if not c.fc_ok(5):
        c.reject("STORM", c.why_not(5)); return
    TS = (95, 96, 97, 99)
    cur = c.inst(now)
    hs = ([cur] if cur and cur.code in TS and abs(cur.t - now) <= 1800 else []) + \
         [h for h in c.ahead(6) if h.code in TS]
    capeonly = [h for h in c.ahead(6) if h.cape >= 1000 and h.code not in TS]
    if not hs:
        if capeonly:
            c.reject("STORM", f"CAPE {max(h.cape for h in capeonly):.0f} without a thunderstorm code: instability "
                              "is not a storm forecast (CAPE shown only as evidence)")
        if drop is not None and drop >= 6 and not stat:
            c.reject("STORM", "pressure drop with altitude change: " + why)
        return
    h = hs[0]
    wet = max([x.precip for x in c.hours() if h.t <= x.t <= h.t + H] + [0])
    if wet < 0.5:
        c.reject("STORM", f"thunderstorm code {h.code} with {wet:.1f} mm: treated as a weak signal, tier 5 only")
    onset = 0 if h is cur else code_onset(c, h)
    start = now + onset * 60
    tier = 1 if (onset <= 60 and wet >= 0.5 and c.fc_ok(1)) else 5
    if onset <= 60 and not c.fc_ok(1):
        c.reject("STORM1", c.why_not(1) + ": shown as tier 5")
    gmax = max([x.gust for x in hs] + [0])
    end = next((x for x in c.hours() if x.t > h.t and x.code not in TS), None)
    l1 = (f"BARO ▼{drop:.1f} IN 3H" if (drop and drop >= 2 and stat) else
          (f"GUSTS TO {gmax:.0f} KMH" if gmax >= 50 else "FCST THUNDERSTORM"))
    l2 = ("UNTIL " + c.at(end.t)) if end else "FOR HOURS"
    detail = "NOW" if onset <= 10 else ("~1 H" if onset <= 60 else c.at(start))
    c.add(Cand(f"STORM{tier}", "STORM", tier, "STORM", detail, l1, l2,
               f"CODE {h.code} CAPE {h.cape:.0f}", c.src(), sev=8 + (1 if h.code in (96, 99) else 0),
               onset_min=onset, invert=tier == 1, event=f"STORM@{c.loc(start):%d%H}", basis="derived"))


def fog(c):
    now = c.s.ts
    h = c.inst(now)
    if h is None:
        return
    if c.v == 1:
        if c.fc_ok(1) and h.vis < 1000:
            c.add(Cand("FOG1", "FOG", 1, "FOG", f"{h.vis / 1000:.1f} KM", f"HUMIDITY {h.rh:.0f}%", "", "",
                       c.src(), sev=1000 - h.vis, invert=True, event="FOG"))
        return
    if not c.fc_ok(5):
        c.reject("FOG", c.why_not(5)); return
    if h.vis is None:
        if h.code in (45, 48):
            c.reject("FOG", "fog code but no visibility field: no distance claimed (tier 5 only)")
        else:
            return
    coded = h.code in (45, 48)
    freezing = h.code == 48 or (coded and h.temp <= 0)
    vis = h.vis if h.vis is not None else 999.0
    if vis >= 1000 and not coded:
        return
    if not coded:
        c.reject("FOG", f"model visibility {vis:.0f} m without a fog code: not corroborated")
        return
    lift = next((x for x in c.hours() if x.t > now and x.code not in (45, 48) and (x.vis or 0) >= 1000), None)
    l2 = ("LIFTS " + c.at(lift.t)) if lift else "NO CLEARING IN 12H"
    dense = h.vis is not None and h.vis < 400
    tier = 1 if (dense and c.fc_ok(1)) else 5
    l1 = f"FREEZING FOG {h.temp:.0f}°" if freezing else f"HUMIDITY {h.rh:.0f}%"
    c.add(Cand(f"FOG{tier}", "FOG", tier, "FOG", "FREEZING" if (freezing and not dense) else
               ("FCST" if h.vis is None else f"{h.vis / 1000:.1f} KM"), l1, l2, f"VIS {vis:.0f} M  CODE {h.code}", c.src(), sev=1000 - vis,
               invert=tier == 1,
               event="FOG" + ("Z" if freezing else ""), basis="forecast"))


def code_onset(c, h):
    """Weather codes are instants at their stamp. With hourly data a change seen at the next stamp happened some
    time in the hour before it, so onset is (stamp - now) minus half an hour, never below zero."""
    m = (h.t - c.s.ts) / 60
    return max(0.0, m - (0 if c.native else 30))


def ice(c):
    now = c.s.ts
    if not c.fc_ok(1 if c.v == 1 else 5):
        c.reject("ICE", c.why_not(5)); return
    ZR = (56, 57, 66, 67)
    if c.v == 1:
        cur = c.block(now + 1)
        hs = ([cur] if cur else []) + c.ahead(1)
        z = [h for h in hs if h.code in ZR]
        if z:
            c.add(Cand("ICE1", "ICE", 1, "ICE", "NOW", f"FREEZING RAIN {z[0].temp:.0f}\u00b0", "", "", c.src(), sev=9,
                       invert=True, event="ICE"))
        return
    cur = c.inst(now)
    z = ([cur] if cur and cur.code in ZR and abs(cur.t - now) <= 1800 else []) + \
        [h for h in c.ahead(6) if h.code in ZR]
    if not z:
        return
    h = z[0]
    onset = 0 if h is cur else code_onset(c, h)
    tier = 1 if onset <= 60 and c.fc_ok(1) else 5
    detail = "NOW" if onset == 0 else ("~1 H" if onset <= 60 else c.at(h.t - (0 if c.native else 1800)))
    end = next((x for x in c.hours() if x.t > h.t and x.code not in ZR), None)
    c.add(Cand(f"ICE{tier}", "ICE", tier, "ICE", detail, f"FREEZING RAIN {h.temp:.0f}\u00b0",
               ("UNTIL " + c.at(end.t)) if end else "", f"FCST CODE {h.code}", c.src(), sev=9, onset_min=onset,
               invert=tier == 1, event="ICE"))


def heat(c):
    now = c.s.ts
    tier_need = 5
    if not c.fc_ok(tier_need):
        c.reject("HEAT", c.why_not(tier_need)); return
    win = [c.inst(now)] + c.ahead(3)
    def eff(h):
        hi = heat_index_c(h.temp, h.rh) if h.temp >= 26.7 else h.temp
        return max(hi, h.temp) if c.v == 2 else hi, hi
    best = max(win, key=lambda h: eff(h)[0])
    e, hi = eff(best)
    if c.v == 1:
        if hi >= 40:
            c.add(Cand("HEAT1", "HEAT", 1, "HEAT", f"FEELS {hi:.0f}°", f"{best.temp:.0f}° HUMIDITY "
                       f"{best.rh:.0f}%", "", "", c.src(), sev=hi, invert=True, event="HEAT1"))
        elif hi >= 32:
            c.add(Cand("HEAT5", "HEAT", 5, "HEAT", f"FEELS {hi:.0f}°", f"HIGH {best.temp:.0f}°", "", "",
                       c.src(), sev=hi, event="HEAT5"))
        else:
            if best.temp >= 35:
                c.reject("HEAT", f"air {best.temp:.0f}° but heat index {hi:.0f}° (dry): Draft 1 misses it")
        return
    was = c.state.get("level", {}).get("HEAT", 0)
    level = 0
    if e >= HEAT1_IN or (was == 1 and e >= HEAT1_OUT):
        level = 1
    elif e >= HEAT5_IN or (was in (1, 5) and e >= HEAT5_OUT):
        level = 5
    if level == 0:
        return
    tier = 1 if level == 1 and c.fc_ok(1) else 5
    c.state.setdefault("level_new", {})["HEAT"] = level
    if not c.inst(now).t or not (6 <= c.loc(now).hour < 21) and tier == 5:
        c.reject("HEAT5", "evening/night: heat advisory left to Quiet (hot night)"); return
    detail = f"FEELS {hi:.0f}°" if hi >= best.temp + 1 else f"AIR {best.temp:.0f}°"
    out_ = HEAT1_OUT if tier == 1 else HEAT5_OUT
    cool = next((h for h in c.hours() if h.t > best.t and eff(h)[0] < out_), None)
    l2 = ("EASES " + c.at(cool.t)) if cool else "NO EASING IN 12H"
    c.add(Cand(f"HEAT{tier}", "HEAT", tier, "HEAT", detail, f"{best.temp:.0f}° HUMIDITY {best.rh:.0f}%", l2,
               f"HEAT INDEX {hi:.0f}  AIR {best.temp:.0f}", c.src(), sev=e,
               onset_min=max(0, (best.t - now) / 60), invert=tier == 1,
               event=f"HEAT{tier}@{c.loc(now):%j}", basis="derived"))


def cold(c):
    now = c.s.ts
    if not c.fc_ok(1 if c.v == 1 else 5):
        return
    win = [c.inst(now)] + c.ahead(1)
    best, wc = None, None
    for h in win:
        w = wind_chill_c(h.temp, h.wind)
        if w is not None and (wc is None or w < wc):
            best, wc = h, w
    if wc is None:
        if c.v == 2 and min(h.temp for h in win) <= -25:
            c.reject("COLD", "wind under 4.8 km/h: wind chill undefined (no message from air alone)")
        return
    if wc <= -28:
        tier = 1 if (c.v == 1 or c.fc_ok(1)) else 5
        milder = next((h for h in c.hours() if h.t > now and (wind_chill_c(h.temp, h.wind) or h.temp) > -28), None)
        l2 = ("MILDER " + c.at(milder.t)) if (milder and c.v == 2) else ("MILDER ~11:00" if c.v == 1 else "")
        c.add(Cand(f"COLD{tier}", "COLD", tier, "COLD", f"FEELS {wc:.0f}°",
                   f"{best.temp:.0f}° WIND {best.wind:.0f}", l2, f"WIND CHILL {wc:.0f}", c.src(), sev=-wc,
                   invert=tier == 1, event="COLD", basis="derived"))


def snow_wind(c):
    now = c.s.ts
    win = ([c.block(now + 1)] if c.block(now + 1) else []) + c.ahead(1)
    if c.v == 1:
        if c.fc_ok(1) and any(h.snow > 0 and h.gust >= 56 for h in win):
            h = max(win, key=lambda x: x.gust)
            c.add(Cand("BLIZ1", "SNOW", 1, "SNOW", f"GUST {h.gust:.0f}", "BLOWING SNOW", "", "", c.src(), sev=7,
                       invert=True, event="BLIZ"))
        return
    if not c.fc_ok(5):
        c.reject("BLIZ", c.why_not(5)); return
    sw = [h for h in win if h.snow > 0]
    if not sw:
        return
    h = max(sw, key=lambda x: x.gust)
    if h.gust < 45:
        return
    strong = h.snow >= 1.0 and h.gust >= 56 and (h.vis < 1000 or h.code in (75, 86))
    if not strong:
        c.reject("BLIZ1", f"snow {h.snow:.1f} cm/h, gust {h.gust:.0f}, vis {h.vis:.0f}: not enough for blowing "
                          "snow (tier 5 SNOW / WINDY)")
    tier = 1 if strong and c.fc_ok(1) else 5
    ease = next((x for x in c.hours() if x.t > h.t and (x.snow < 0.2 or x.gust < 45)), None)
    c.add(Cand(f"BLIZ{tier}", "SNOW", tier, "SNOW", f"GUST {h.gust:.0f}" if tier == 1 else "WINDY",
               "BLOWING SNOW" if tier == 1 else f"{h.snow:.1f} CM/H  GUSTS {h.gust:.0f}",
               ("EASES " + c.at(ease.t - H)) if ease else "", f"VIS {h.vis:.0f} M", c.src(), sev=h.gust,
               invert=tier == 1, event="BLIZ"))


def snow_total(c):
    if c.v == 1:
        return
    if not c.fc_ok(5):
        return
    now = c.s.ts
    hs = c.ahead(6)
    tot = sum(h.snow for h in hs)
    if tot >= 5:
        end = next((h for h in c.hours() if h.t > now and h.snow < 0.2 and h.t > hs[0].t), None)
        c.add(Cand("SNOWTOT", "SNOW", 5, "SNOW", f"+{tot:.0f} CM", "NEXT 6 HOURS",
                   ("EASES " + c.at(end.t - H)) if end else "", f"SNOWFALL {tot:.1f} CM / 6H", c.src(),
                   sev=tot, event=f"SNOWTOT@{c.loc(now):%j}"))
    elif tot >= 2:
        c.reject("SNOWTOT", f"{tot:.1f} cm in 6 h, under 5 cm")


def air(c):
    aq = c.f.aq if c.f else None
    if not aq:
        return
    eu = in_box(c.s.lat, c.s.lon, EUROPE)
    if c.v == 2 and aq.get("age_min", 0) > MAX_AGE["aq"]:
        c.reject("AIR", f"air-quality data {aq['age_min']:.0f} min old"); return
    if c.v == 1:
        v = aq.get("eaqi") if eu else aq.get("usaqi")
        if v is None:
            return
        if (eu and v > 100) or (not eu and v >= 300):
            c.add(Cand("AIR1", "AIR", 1, "AIR", "EXTREME", f"PM2.5 {aq['sub'].get('pm2_5', 0):.0f}", "BETTER ~WED",
                       "", c.src(), sev=v, invert=True, event="AIR1"))
        elif (eu and v >= 60) or (not eu and v >= 150):
            c.add(Cand("AIR5", "AIR", 5, "AIR", "POOR", f"PM10 {aq['sub'].get('pm10', 0):.0f} AIR POOR", "", "",
                       c.src(), sev=v, event="AIR5"))
        if aq.get("dust", 0) >= 100:
            c.add(Cand("DUST", "DUST", 5, "DUST", "SAHARA", f"PM10 {aq['sub'].get('pm10', 0):.0f}", "", "", c.src(),
                       sev=aq["dust"], event="DUST"))
        return
    scale, v = ("EU AQI", aq.get("eaqi")) if eu else ("US AQI", aq.get("usaqi"))
    if v is None:
        c.reject("AIR", f"{scale} missing"); return
    sub = aq.get("sub_eu" if eu else "sub_us", {})
    driver = max(sub, key=sub.get).upper().replace("PM2_5", "PM2.5") if sub else "?"
    t1 = v > 100 if eu else v >= 301
    t5 = v >= 60 if eu else v >= 151
    if t1 or t5:
        word = ("EXTREME" if eu else "HAZARD") if t1 else ("POOR" if eu else "UNHEALTHY")
        dust = aq.get("dust", 0)
        l2 = f"DUST {dust:.0f}" if dust >= 100 else ""
        c.add(Cand(f"AIR{1 if t1 else 5}", "AIR", 1 if t1 else 5, "AIR", word, f"{scale} {v:.0f}  {driver}", l2,
                   f"{scale} {v:.0f} FROM {driver}", "CAMS VIA OPEN-METEO", sev=v, invert=t1, event="AIR"))
    elif aq.get("dust", 0) >= 100:
        c.add(Cand("DUST", "DUST", 5, "DUST", "HIGH", f"DUST {aq['dust']:.0f} UG/M3", f"{scale} {v:.0f}",
                   "", "CAMS VIA OPEN-METEO", sev=aq["dust"], event="DUST"))


def pollen(c):
    aq = c.f.aq if c.f else None
    if not aq:
        return
    pl = aq.get("pollen")
    if c.v == 2 and not c.s.pollen_on:
        if pl and max((x for x in pl.values() if x is not None), default=0) >= 30:
            c.reject("POLLEN", "pollen is opt-in (thresholds not yet sourced)")
        return
    if not pl or all(x is None for x in pl.values()):
        if c.v == 2:
            c.reject("POLLEN", "no pollen data here (null outside Europe): no claim either way")
        return
    k, x = max(((k, x) for k, x in pl.items() if x is not None), key=lambda kv: kv[1])
    if x >= 100:
        c.add(Cand("POLLEN", "POLLEN", 5, "POLLEN", k.upper(), "LEVEL HIGH", "", f"{x:.0f} GRAINS/M3",
                   "CAMS VIA OPEN-METEO", sev=x, event="POLLEN"))


def uv(c):
    now = c.s.ts
    if not c.fc_ok(5):
        return
    if c.v == 1:
        today = [h for h in c.hours() if c.loc(h.t).date() == c.s.now.date() and h.t >= now]
        if today and max(h.uv for h in today) >= 8:
            p = max(today, key=lambda h: h.uv)
            c.add(Cand("UV", "UV", 5, "UV", "VERY HIGH", "UV 8+ TODAY", f"PEAK {p.uv:.0f} AT {hhmm(c.loc(p.t))}",
                       "", c.src(), sev=p.uv, event="UV"))
        return
    win = [c.inst(now)] + c.ahead(2)
    hi = [h for h in win if h.uv >= 8]
    if not hi:
        later = [h for h in c.ahead(12) if h.uv >= 8]
        if later:
            c.reject("UV", "UV 8+ only later today: outside the 2 h relevance window")
        return
    allday = [h for h in c.hours() if c.loc(h.t).date() == c.s.now.date()]
    p = max(allday, key=lambda h: h.uv)
    end = next((h for h in c.hours() if h.t > now and h.uv < 8), None)
    c.add(Cand("UV", "UV", 5, "UV", "VERY HIGH" if p.uv < 11 else "EXTREME",
               ("UV 8+ UNTIL " + c.at(end.t)) if end else "UV 8+", f"PEAK {p.uv:.0f} AT {hhmm(c.loc(p.t))}",
               f"UV {c.inst(now).uv:.0f} NOW", c.src(), sev=p.uv, event=f"UV@{c.loc(now):%j}"))


def snow_line(c):
    alt = c.s.altitude
    if c.v == 1:
        h = c.inst(c.s.ts)
        if h and alt is not None and h.temp is not None:
            fl = getattr(h, "fl", None)
        return                                      # Draft 1 used freezing level - 300 m: not modelled further
    if not c.fc_ok(5):
        return
    wet = [h for h in c.ahead(6) if h.precip >= WET_H]
    if not wet:
        return
    h = wet[0]
    if h.snow_h is None:
        c.reject("SNOWLINE", "no snowfall_height from the model here (Europe models only)"); return
    if alt is None:
        c.reject("SNOWLINE", "no watch altitude"); return
    margin = h.snow_h - alt
    if 0 < margin <= 300:
        c.add(Cand("SNOWLINE", "SNOW", 5, "SNOW", f"LINE ▲{r5(margin) // 10 * 10:.0f} M",
                   f"SNOW FROM {h.snow_h:.0f} M", f"YOU {alt:.0f} M  WET " + c.at(h.t - H),
                   f"GRID {c.f.grid_elev:.0f} M", c.src(), sev=300 - margin,
                   onset_min=(h.t - H - c.s.ts) / 60, event="SNOWLINE"))
    elif margin <= 0:
        c.reject("SNOWLINE", "you are above the snow line: the rain timeline says SNOW")


def temp_drop(c):
    now = c.s.ts
    if not c.fc_ok(5):
        return
    hs = [c.inst(now)] + c.ahead(6)
    for i, a in enumerate(hs):
        for b in hs[i + 1:i + 4]:
            d = a.temp - b.temp
            if d >= 5:
                if c.v == 1:
                    c.add(Cand("FRONT", "TEMP", 5, "FRONT", f"-{d:.0f}° {c.at(b.t)}", "NW WIND ~15:00",
                               "GUSTS TO 70 KMH", "", c.src(), sev=d, event="FRONT"))
                    return
                shift = abs((b.wdir - a.wdir + 180) % 360 - 180)
                rise = b.gust - a.gust
                if shift < 45 and rise < 15:
                    c.reject("TEMP", f"-{d:.0f}\u00b0 in 3 h without a wind shift or gust rise: likely the daily "
                                     "cooling, not a change of air")
                    return
                l1 = (f"WIND {compass(b.wdir)} " + c.at(b.t)) if shift >= 45 else f"FROM {a.temp:.0f}° TO {b.temp:.0f}°"
                c.add(Cand("TEMP", "TEMP", 5, "TEMP", f"-{d:.0f}° " + c.at(b.t), l1,
                           f"GUSTS TO {max(x.gust for x in hs):.0f} KMH" if shift >= 45 else "",
                           f"WIND SHIFT {shift:.0f} DEG", c.src(), sev=d, onset_min=(a.t - now) / 60, event="TEMP"))
                return


def compass(b):
    i = int((b + 22.5) // 45) % 8
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][i]


def night_temps(c):
    """Frost and hot nights: the coming night's minimum (now .. next 09:00)."""
    now = c.s.ts
    if not c.fc_ok(5 if c.v == 2 else 5):
        return
    lt = c.s.now
    sun = c.s.sun or {}
    if c.v == 1:
        evening = lt.hour >= 19
    else:
        evening = ("set" in sun and lt >= sun["set"] - timedelta(hours=2)) or lt.hour < 6
    if not evening:
        return
    hs = [h for h in c.hours() if h.t > now and c.loc(h.t).hour <= 9 or (h.t > now and c.loc(h.t).date() == lt.date())]
    hs = [h for h in hs if h.t <= now + 15 * H]
    if not hs:
        return
    low = min(hs, key=lambda h: h.temp)
    day_max = c.f.daily.get("tmax", 10)
    if low.temp <= 0 and (c.v == 1 or day_max >= 5):
        calm = low.cloud < 30 and low.wind < 10
        c.add(Cand("FROST", "FROST", 5, "FROST", "TONIGHT" if lt.hour >= 12 else "BY DAWN",
                   f"LOW {low.temp:.0f}° " + c.at(low.t),
                   ("CLEAR SKY  CALM" if c.v == 1 else ("CLEAR  LIGHT WIND" if calm else "")),
                   f"AIR TEMP, NOT GROUND", c.src(), sev=-low.temp, event=f"FROST@{c.loc(low.t):%j}"))
    elif c.v == 2 and low.temp <= 0:
        c.reject("FROST", f"day max {day_max:.0f}°: frost is not news after a cold day")
    if low.temp >= 20:
        tier = 5 if (c.v == 1 or low.temp >= 25) else 6
        c.add(Cand("HOTNIGHT", "HOTNIGHT", tier, "HOT", f"MIN {low.temp:.0f}°", "TROPICAL NIGHT",
                   "COOLEST " + c.at(low.t), "", c.src(), sev=low.temp, event=f"HOTN@{c.loc(now):%j}"))


def baro_trend(c):
    drop, stat, why = c.baro_change()
    if drop is None:
        return
    p_now = c.s.baro.press[-1][1]
    online = c.fc_ok(6)
    if c.v == 1:
        if drop >= 3:
            c.add(Cand("BARO5", "BARO", 5, "BARO", "FALLING", f"{p_now:.0f} HPA ▼{drop:.1f} IN 3H",
                       "CHANGE COMING", "", "WATCH BARO", sev=drop, event="BARO"))
        return
    if not stat:
        c.reject("BARO", why); return
    if drop >= 4 and not online:
        c.add(Cand("BARO5", "BARO", 5, "BARO", "FALLING", f"{p_now:.0f} HPA ▼{drop:.1f} IN 3H",
                   "WATCH STILL 3H", f"{len(c.s.baro.press)} SAMPLES / 3H", "WATCH BARO", sev=drop,
                   event="BARO", basis="watch"))
    elif drop >= 4:
        c.reject("BARO5", "online: the forecast speaks for the weather; pressure only supports it")


def light(c):
    sun = c.s.sun
    if not sun:
        if c.v == 2:
            c.reject("LIGHT", "no valid location: no sun times")
        return
    if "polar" in sun:
        return
    now = c.s.now
    left = (sun["set"] - now).total_seconds() / 60
    if 0 < left <= 120:
        tier = 2 if left <= 30 else 4
        l2 = (f"DARK {hhmm(sun['dusk'])}  FIRST {hhmm(sun['dawn'])}" if c.v == 1 else
              f"CIVIL DUSK {hhmm(sun['dusk'])}")
        c.add(Cand(f"LIGHT{tier}", "LIGHT", tier, "LIGHT", f"{int(left) // 60}:{int(left) % 60:02d} LEFT",
                   f"SUNSET {hhmm(sun['set'])}", l2, "SUN CALC, NOT TERRAIN", "WATCH, POSITION",
                   sev=120 - left, onset_min=left, event=f"LIGHT{tier}", basis="astronomy"))


def rain(c):
    now = c.s.ts
    if not c.fc_ok(3):
        c.reject("RAIN", c.why_not(3)); return None
    spells, blocks = rain_timeline(c)
    first = spells[0] if spells else None
    wet_now = bool(first and first[0] <= now + 60)
    if c.v == 1:
        if not first:
            return spells
        h3 = c.ahead(3)
        prob = max([h.prob for h in h3] + [0])
        word = "SNOW" if first[3] > 0 else "RAIN"
        if wet_now:
            left = (first[1] - now) / 60
            if left <= 120:
                c.add(Cand("DRY3", "RAIN", 3, "DRY", f"~{max(5, r5(left))} MIN", f"{word} {first[2]:.1f} MM",
                           "", "", c.src(), onset_min=left, sev=3, event="DRY"))
            if any(b[2] >= 4 for b in blocks if b[1] - b[0] == H):
                pass
        else:
            m = (first[0] - now) / 60
            if m <= 120:
                c.add(Cand("RAIN3", "RAIN", 3, word, f"~{max(5, r5(m))} MIN", f"{prob:.0f}%  ABOUT "
                           f"{first[2]:.0f} MM", "", "", c.src(), onset_min=m, sev=3, event="RAIN"))
        heavy = [b for b in blocks if (b[2] * (H / (b[1] - b[0]))) >= 4 and b[0] < now + 2 * H]
        if heavy:
            b = heavy[0]
            c.add(Cand("HEAVY3", "RAIN", 3, "RAIN", "HEAVY " + c.at(b[0]), f"~{b[2] * H / (b[1] - b[0]):.0f} MM IN 1H",
                       "", "", c.src(), onset_min=max(0, (b[0] - now) / 60), sev=4, event="HEAVY"))
        return spells
    # ---------------- v2
    if not spells:
        return spells
    word = "SNOW" if first[3] >= first[2] * 0.5 and first[3] > 0 else "RAIN"
    prob = first[4]
    sun = c.s.sun or {}
    def before_dark(t):
        if "set" in sun and now < sun["set"].timestamp() and t < sun["dusk"].timestamp() \
                and sun["set"].timestamp() - now <= 2 * H:
            return f"SUNSET {hhmm(sun['set'])}"
        return ""
    if wet_now:
        end = first[1]
        nxt = spells[1] if len(spells) > 1 else None
        left = (end - now) / 60
        gap = ((nxt[0] - end) / 60) if nxt else 999
        if left <= 120:
            if gap < MIN_DRY:
                c.reject("DRY", f"dry gap of {gap:.0f} min after {c.at(end)}: under {MIN_DRY}")
            else:
                detail = (f"~{max(15, int(round(left / 15) * 15))} MIN" if c.native and left < 100
                          else c.at(end))
                c.add(Cand("DRY3", "RAIN", 3, "DRY", detail, f"{first[2]:.1f} MM STILL TO FALL",
                           ("DRY ~%dH AFTER" % min(12, gap // 60)) if gap < 999 else "DRY 12H+",
                           f"PROB {prob:.0f}%", c.src(), onset_min=left, sev=3,
                           event=f"DRY@{c.loc(end):%d%H}"))
        elif first[2] >= 0.5:
            c.state.setdefault("quiet_hint", {})["WETLONG"] = first
    else:
        m = (first[0] - now) / 60
        if m <= 120:
            if first[2] < 0.5:
                c.reject("RAIN3", f"only {first[2]:.1f} mm forecast: negligible")
            elif prob is not None and prob < 30:
                c.reject("RAIN3", f"{first[2]:.1f} mm but ensemble probability {prob:.0f}%: not a confident onset")
            else:
                detail = (f"~{max(15, int(round(m / 15) * 15))} MIN" if c.native and m < 100 else "FROM " + c.at(first[0]))
                nxt_dry = first[1]
                l2 = before_dark(first[0]) or ("THEN DRY " + c.at(nxt_dry) if nxt_dry - first[0] < 12 * H else
                                               "NO DRY SPELL 12H")
                c.add(Cand("RAIN3", "RAIN", 3, word, detail.replace("FROM ", ""),
                           f"{prob:.0f}%  ABOUT {first[2]:.0f} MM", l2,
                           "RAIN TIMELINE " + ("15MIN" if c.native else "HOURLY"), c.src(),
                           onset_min=m, sev=3 + first[2] / 10, event=f"RAIN@{c.loc(first[0]):%d%H}"))
    # heavy rain (rate) and accumulation (total), same timeline
    hrs = [h for h in c.ahead(2)] + ([c.block(now + 1)] if c.block(now + 1) else [])
    heavy = [h for h in hrs if h.precip >= HEAVY_H]
    if heavy:
        h = min(heavy, key=lambda x: x.t)
        c.add(Cand("HEAVY3", "RAIN", 3, "RAIN", "HEAVY", f"~{h.precip:.0f} MM IN 1H",
                   f"FROM {c.at(h.t - H)}", f"RATE {h.precip:.1f} MM/H", c.src(),
                   onset_min=max(0, (h.t - H - now) / 60), sev=5, event=f"HEAVY@{c.loc(h.t):%d%H}"))
    else:
        mid = [h for h in hrs if 4 <= h.precip < HEAVY_H]
        if mid:
            c.reject("HEAVY3", f"{max(h.precip for h in mid):.1f} mm/h: above Draft 1's 4, under {HEAVY_H}")
    six = c.ahead(6)
    tot = sum(h.precip for h in six)
    if tot >= 20:
        pk = max(six, key=lambda h: h.precip)
        c.add(Cand("RAINTOT", "RAIN", 5, "RAIN", f"+{tot:.0f} MM", "NEXT ~6 HOURS", "HEAVIEST " + c.at(pk.t - H),
                   f"TOTAL {tot:.0f} MM / 6H", c.src(), sev=tot, event=f"RAINTOT@{c.loc(now):%j}"))
    return spells


# =====================================================================================================  quiet

def quiet(c, spells):
    s, now = c.s, c.s.now
    sun = s.sun
    online = c.fc_ok(6)
    st = c.state
    def Qc(id_, word, detail, l1, l2, ev1="", ev2="", basis="forecast"):
        return Cand(id_, "QUIET", 6, word, detail, l1, l2, ev1, ev2 or (c.src() if online else "WATCH"),
                    event=id_ + f"@{now:%j}", basis=basis)
    if sun and "polar" in sun:
        return Qc("POLAR", "POLAR", sun["polar"], "NO SUNRISE TODAY" if sun["polar"] == "NIGHT" else "NO SUNSET TODAY",
                  "", basis="astronomy")
    if not online:
        if c.v == 1:
            drop, _, _ = c.baro_change()
            if drop is not None:
                return Qc("BAROQ", "BARO", "RISING" if drop < -1 else "FALLING" if drop > 1 else "STEADY",
                          f"{s.baro.press[-1][1]:.0f} HPA", "", basis="watch")
            if sun:
                return Qc("SUNQ", "SUN", hhmm(sun["set"]), "", "", basis="astronomy")
            return Qc("CALM", "CALM", "DRY 12H+", "", "")
        drop, stat, why = c.baro_change()
        if drop is not None and stat:
            word = "RISING" if drop <= -1 else "FALLING" if drop >= 1 else "STEADY"
            return Qc("BAROQ", "BARO", word, f"{s.baro.press[-1][1]:.0f} HPA {'▼' if drop > 0 else '▲'}"
                      f"{abs(drop):.1f} IN 3H", (f"SUNSET {hhmm(sun['set'])}" if sun else ""), "WATCH BARO",
                      "NO FORECAST: " + (c.f.error or "OLD") if c.f else "NO FORECAST", basis="watch")
        if sun:
            return Qc("SUNQ", "SUN", hhmm(sun["set"]) if now < sun["set"] else hhmm(sun["rise"]),
                      f"SUNSET {hhmm(sun['set'])}", f"FIRST LIGHT {hhmm(sun['dawn'])}", basis="astronomy")
        return Qc("NODATA", "NO FIX", (c.f.error if c.f and c.f.error else "NO GPS"), "NO POSITION YET",
                  "", basis="none")
    hs = c.hours()
    today = [h for h in hs if c.loc(h.t).date() == now.date()]
    d = c.f.daily
    if c.v == 1:
        if st.get("first_raise"):
            return Qc("TODAY", "TODAY", f"HI {d.get('tmax', 0):.0f}°", "RAIN --", f"UV {d.get('uv_max', 0):.0f}")
        if now.hour >= 19:
            tm = d.get("tomorrow", {})
            return Qc("TMRW", "TMRW", f"RAIN {tm.get('prob', 0):.0f}%", f"FROM ~09:00 ~{tm.get('mm', 0):.0f} MM",
                      f"HIGH {tm.get('tmax', 0):.0f}°")
        if sun and (now < sun["rise"] or now > sun["dusk"]):
            return Qc("NIGHT", "NIGHT", f"LOW {d.get('tmin', 0):.0f}°", "", "")
        if d.get("sunshine_s", 0) >= 8 * H:
            return Qc("CLEAR", "CLEAR", "ALL DAY", f"SUN {d['sunshine_s'] / H:.0f}H", "DRY TILL TOMORROW")
        if spells:
            amt = sum(x[2] for x in spells)
            return Qc("CALM", "CALM", f"RAIN +{amt:.0f}MM" if spells[0][0] <= s.ts else "DRY ~%dH" %
                      ((spells[0][0] - s.ts) // H), "", "")
        return Qc("CALM", "CALM", "DRY 12H+", f"HIGH {d.get('tmax', 0):.0f}°", "")
    # ------------- v2 scheduler: by local windows relative to the sun
    if sun:
        dawn, rise, set_, dusk = sun["dawn"], sun["rise"], sun["set"], sun["dusk"]
    else:
        dawn = rise = set_ = dusk = None
    if dawn and dawn - timedelta(minutes=75) <= now < dawn:
        m = int((dawn - now).total_seconds() // 60)
        return Qc("DAWN", "DAWN", f"~{max(5, r5(m))} MIN", f"FIRST LIGHT {hhmm(dawn)}", f"SUNRISE {hhmm(rise)}",
                  "CIVIL DAWN, SUN CALC", "WATCH, POSITION", basis="astronomy")
    if st.get("first_raise") and rise and rise - timedelta(hours=1) <= now < set_ and now.hour < 12:
        rain_t = next((x for x in spells), None)
        l1 = ("RAIN " + c.at(rain_t[0])) if rain_t else "DRY 12H+"
        return Qc("TODAY", "TODAY", f"HI {d.get('tmax', 0):.0f}°", l1,
                  f"UV {d.get('uv_max', 0):.0f}  SUNSET {hhmm(set_)}")
    hot = st.get("pending_hotnight")
    if set_ and now >= max(set_, now.replace(hour=17, minute=0)) and now.hour < 23:
        if hot:
            return hot
        tm = d.get("tomorrow")
        if tm and tm.get("hours"):
            wet = [h for h in tm["hours"] if h.precip >= WET_H]
            if wet:
                return Qc("TMRW", "TMRW", f"RAIN {max(h.prob for h in wet):.0f}%",
                          "FROM " + c.at(wet[0].t - H) + f" ~{sum(h.precip for h in wet):.0f} MM",
                          f"HIGH {tm['tmax']:.0f}°")
            return Qc("TMRW", "TMRW", "DRY", f"HIGH {tm['tmax']:.0f}°  LOW {tm['tmin']:.0f}°",
                      f"RAIN {tm.get('prob', 0):.0f}%")
        elif tm:
            return Qc("TMRW", "TMRW", f"RAIN {tm.get('prob', 0):.0f}%", f"HIGH {tm['tmax']:.0f}°",
                      "NO HOURLY DATA FOR TIMES")
    if dusk and (now >= dusk or now < dawn):
        if hot:
            return hot
        mn = s.moon or {}
        cl = c.inst(s.ts).cloud
        below = mn.get("rise") and mn.get("set") is not None and not (
            (mn["rise"] <= now < mn["set"]) if mn["rise"] < mn["set"] else (now >= mn["rise"] or now < mn["set"]))
        if mn and below and cl < 30:
            return Qc("MOON", "MOON", "BELOW", f"RISES {hhmm(mn['rise'])}  {mn.get('phase', 0) * 100:.0f}%",
                      f"FIRST LIGHT {hhmm(dawn)}", f"CLOUD {cl:.0f}%", basis="astronomy")
        low = min([h for h in hs if h.t > s.ts][:12] or hs, key=lambda h: h.temp)
        return Qc("NIGHT", "NIGHT", f"LOW {low.temp:.0f}°", f"LOWEST " + c.at(low.t),
                  f"FIRST LIGHT {hhmm(dawn)}")
    # daytime
    wl = st.get("quiet_hint", {}).get("WETLONG")
    if wl:
        return Qc("RAINQ", "RAIN", f"+{wl[2]:.0f} MM", "STILL RAINING", "NO DRY SPELL SOON" if wl[1] - s.ts > 12 * H
                  else "DRY " + c.at(wl[1]))
    if len(spells) >= 1 and spells[0][0] > s.ts:
        gap = (spells[0][0] - s.ts) / 60
        if 90 <= gap <= 240 and len(spells) >= 1:
            return Qc("GAP", "DRY", f"~{gap / 60:.0f}H GAP", "UNTIL " + c.at(spells[0][0]),
                      f"THEN RAIN {spells[0][4]:.0f}%")
    rest = [h for h in today if h.t > s.ts]
    sun_s = sum(h.sun_s for h in rest)
    cloud = (sum(h.cloud for h in rest) / len(rest)) if rest else 100
    if sun_s >= 5 * H and cloud < 40 and not spells:
        return Qc("SUNNY", "SUNNY", f"~{sun_s / H:.0f}H SUN", f"HIGH {d.get('tmax', 0):.0f}°  UV {d.get('uv_max', 0):.0f}",
                  "DRY 12H+", f"CLOUD {cloud:.0f}%")
    if not spells:
        return Qc("CALM", "CALM", "DRY 12H+", f"HIGH {d.get('tmax', 0):.0f}°  UV {d.get('uv_max', 0):.0f}",
                  f"SUNSET {hhmm(set_)}" if set_ else "")
    return Qc("CALM", "DRY", "~%dH" % ((spells[0][0] - s.ts) // H), "RAIN " + c.at(spells[0][0]),
              f"SUNSET {hhmm(set_)}" if set_ else "")


# =====================================================================================================  selection

def run(s, v, state=None):
    state = {} if state is None else state
    c = Ctx(s, v)
    c.state = state
    state.pop("level_new", None)
    state.pop("quiet_hint", None)
    for fn in (gusts, wind_rising, storm, fog, ice, heat, cold, snow_wind, snow_total, air, pollen, uv, snow_line,
               temp_drop, baro_trend, light):
        try:
            fn(c)
        except Exception as e:       # a crash in one message must not stop the others
            c.reject(fn.__name__, f"error: {e!r}")
    spells = []
    try:
        spells = rain(c) or []
    except Exception as e:
        c.reject("rain", f"error: {e!r}")
    night_temps(c)
    if v == 2:
        hot = [x for x in c.cands if x.id == "HOTNIGHT" and x.tier == 6]
        for x in hot:
            c.cands.remove(x)
        state["pending_hotnight"] = hot[0] if hot else None
    if v == 2:
        spells = [x for x in spells if x[2] >= 0.5 and (x[4] is None or x[4] >= 30)]
    q = quiet(c, spells)
    state["level"] = state.get("level_new", {})
    if v == 1:
        pool = c.cands + [q]
        pool.sort(key=lambda x: (x.tier, x.onset_min))
        return Result(pool[0], c.cands, c.rej)
    # ---- v2: merge families (one per family, strongest), cross-tier exception, cooldown, hold
    best = {}
    for x in c.cands:
        k = x.family
        if k not in best or (x.tier, -x.sev) < (best[k].tier, -best[k].sev):
            if k in best:
                c.reject(best[k].id, f"merged into {x.id} (same {k} family)")
            best[k] = x
        else:
            c.reject(x.id, f"merged into {best[k].id} (same {k} family)")
    pool = list(best.values())
    now = s.ts
    shown = state.setdefault("shown", {})
    has_t2 = any(p.tier == 2 for p in pool)          # computed before sorting (the list is empty while it sorts)
    def key(x):
        tier = x.tier
        if x.id == "RAIN3" and c.native and x.onset_min <= 30 and has_t2:
            tier = 1.9                                     # imminent rain beats the sunset countdown
        pid = x.family + ("5" if x.family in ("HEAT", "GUST") and x.tier == 5 else "")
        if x.tier == 5 and (pid in PERSISTENT or x.family in PERSISTENT):
            rec = shown.get(x.event)
            if rec and now - rec[0] >= HOLD_MIN * 60 and now - rec[1] < REMIND_MIN * 60 and rec[2] == round(x.sev):
                tier = 6.5                                  # shown long enough, unchanged: let Quiet speak
        rank = FAMILY_RANK.get(x.family, 20) if tier <= 5 else 0
        return (tier, rank, -x.sev, x.onset_min)
    pool.sort(key=key)
    chosen = pool[0] if pool and key(pool[0])[0] < 6 else q
    if pool and key(pool[0])[0] == 6.5:
        c.reject(pool[0].id, "persistent advisory, unchanged for 60+ min: yields to Quiet until a 2-hour reminder")
    # composition: a stronger family absorbs a gust it explains
    g = best.get("GUST")
    if g is not None and chosen is not g and chosen.family in ("STORM", "SNOW") and g.sev >= GUST5_IN:
        if "GUST" not in chosen.line1 and chosen.family == "STORM":
            chosen.line1 = f"GUSTS TO {g.sev:.0f} KMH"
        c.reject(g.id, f"absorbed into {chosen.id}")
    if g is not None and chosen is not g and chosen.family == "TEMP":
        chosen.line2 = f"GUSTS TO {max(g.sev, 0):.0f} KMH" if g.id != "WINDUP" else g.line1
        c.reject(g.id, f"absorbed into {chosen.id}")
    sl = next((x for x in c.cands if x.id == "SNOWLINE"), None)
    if sl is not None and chosen.id == "RAIN3":
        chosen.line2 = sl.line1
        c.reject("SNOWLINE", "composed into RAIN3 line 2")
    # Quiet must not contradict a hazard that was dropped only because the data got old
    if chosen is q and c.f and c.f.ok and c.f.age_min > 90 and v == 2:
        sh = Ctx(s, v); sh.state = {}; sh.relaxed = True
        for fn in (gusts, storm, ice, heat, cold, snow_wind, fog):
            try:
                fn(sh)
            except Exception:
                pass
        old = sorted([x for x in sh.cands if x.tier <= 5], key=lambda x: FAMILY_RANK.get(x.family, 20))
        if old:
            o = old[0]
            age = int(c.f.age_min // 60)
            chosen = Cand("STALE", "QUIET", 6, o.word, f"{age}H OLD", f"FCST {o.detail}",
                          f"NO DATA FOR {age}H", o.ev1, c.src(), event="STALE" + o.event)
            c.reject(o.id, f"forecast {c.f.age_min:.0f} min old: shown only as an old forecast, not a warning")
    prev = state.get("last")
    if prev and chosen.id != prev[0]:
        same = next((x for x in pool if x.id == prev[0]), None)
        if same and key(same)[0] == key(chosen)[0] and same.sev >= chosen.sev * 0.9 and now - prev[1] < 15 * 60:
            c.reject(chosen.id, f"hold: {prev[0]} still valid and comparable (shown {int((now - prev[1]) / 60)} min ago)")
            chosen = same
    if chosen is not q:
        rec = shown.get(chosen.event)
        if rec is None or rec[2] != round(chosen.sev):
            shown[chosen.event] = [now, now, round(chosen.sev)]
        else:
            rec[1] = now
    if not state.get("last") or state["last"][0] != chosen.id:
        state["last"] = (chosen.id, now)
    return Result(chosen, c.cands, c.rej)
