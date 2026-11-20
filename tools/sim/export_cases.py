"""Exports every simulation raise as the inputs the watch's Context.mc receives (the WeatherService array format),
plus what the Python v2 engine chose, so the transpiled watch code can be run on the same situations."""
import json, sys, os, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import run
from scenarios import SC
from data import resolution_at, EUROPE, in_box

NUL = -9999
POL = ["alder", "birch", "grass", "mugwort", "olive", "ragweed"]


def sc(v, k):
    if v is None:
        return NUL
    x = v * k
    return int(x + 0.5) if x >= 0 else int(x - 0.5)


def minutes(dt):
    return dt.hour * 60 + dt.minute


def pollen_level(pl):
    lvl, typ = None, 0
    for i, name in enumerate(POL):
        g = (pl or {}).get(name)
        if g is None:
            continue
        tree = i in (0, 1, 4)
        hi = 100 if tree else (50 if i == 3 else 30)
        vh = 500 if tree else 100
        l = 0 if g < 1 else (1 if g < 10 else (2 if g < hi else (3 if g <= vh else 4)))
        if lvl is None or l > lvl:
            lvl, typ = l, i
    return lvl, typ


def to_inputs(s):
    f = s.fetch
    now = s.ts
    inp = {"now": now, "localMin": minutes(s.now), "tz": str(s.now.tzinfo), "alt": s.altitude,
           "q15": s.res == "native15", "far": s.fc_dist_km > 25, "pollenOn": s.pollen_on}
    if f is not None and f.ok and f.hours:
        t0 = now // 3600 * 3600
        hs = {h.t: h for h in f.hours}
        tm = f.daily.get("tomorrow")
        if tm and tm.get("hours"):
            mid = int(s.now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()) + 86400
            for h in tm["hours"]:
                if h.t > mid:
                    hs[h.t] = h          # tomorrow's own series wins after midnight
        series = [hs.get(t0 + i * 3600) for i in range(24)]
        n = 0
        while n < 24 and series[n] is not None:
            n += 1
        series = series[:n]
        def col(fn):
            return [fn(h) for h in series]
        w = [now - int(f.age_min * 60), s.lat if s.fc_dist_km <= 25 else s.lat + s.fc_dist_km / 111.0, s.lon, t0, n,
             col(lambda h: sc(h.temp, 10)), col(lambda h: sc(h.rh, 1)), col(lambda h: sc(h.code, 1)),
             col(lambda h: sc(h.prob, 1)), col(lambda h: sc(h.precip, 10)), col(lambda h: sc(h.snow, 10)),
             col(lambda h: sc(h.wind, 1)), col(lambda h: sc(h.wdir, 1)), col(lambda h: sc(h.gust, 1)),
             col(lambda h: sc(h.vis, 0.1)), col(lambda h: sc(h.uv, 10)), col(lambda h: sc(h.cloud, 1)),
             col(lambda h: sc(h.snow_h, 1)), col(lambda h: sc(h.sun_s, 1 / 60.0)),
             f.m15[0][0] if f.m15 else None, [sc(v, 10) for _, v in f.m15] if f.m15 else None]
        d = f.daily
        moon = s.moon or {}
        mr = int(moon["rise"].timestamp()) if moon.get("rise") else None
        ms = int(moon["set"].timestamp()) if moon.get("set") else None
        w.append([sc(d.get("tmax"), 10), sc(d.get("tmin"), 10), sc(d.get("uv_max"), 10),
                  sc(d.get("sunshine_s"), 1 / 60.0), sc((tm or {}).get("tmax"), 10), sc((tm or {}).get("tmin"), 10),
                  sc((tm or {}).get("prob"), 1), mr, ms, sc(moon.get("phase"), 100), mr + 89400 if mr else None, ms + 89400 if ms else None])
        aq = f.aq
        if aq:
            eu = in_box(s.lat, s.lon, EUROPE)
            sub = aq.get("sub_eu" if eu else "sub_us", {})
            order = ["pm2_5", "pm10", "no2", "ozone", "so2"]
            drv = max(range(5), key=lambda i: sub.get(order[i], -1)) if sub else 0
            lvl, typ = pollen_level(aq.get("pollen"))
            w.append([now - int(aq.get("age_min", 0) * 60), 0 if eu else 1, sc(aq.get("eaqi" if eu else "usaqi"), 1),
                      drv, sc(aq.get("dust", 0), 1), lvl, typ])
        else:
            w.append(None)
        w.append(None)
        inp["w"] = w
        inp["wAge"] = int(f.age_min)
    else:
        inp["w"] = None
        inp["wAge"] = 9999
    inp["errText"] = (f.error if (f and f.error) else "NO DATA")
    sun = s.sun
    if sun and "polar" in sun:
        inp.update(riseM=-1, setM=-1, dawnM=-1, duskM=-1, polar=1 if sun["polar"] == "DAY" else -1)
    elif sun:
        inp.update(riseM=minutes(sun["rise"]), setM=minutes(sun["set"]), dawnM=minutes(sun["dawn"]),
                   duskM=minutes(sun["dusk"]), polar=0)
    else:
        inp.update(riseM=-1, setM=-1, dawnM=-1, duskM=-1, polar=0)
    p = s.baro.press
    if len(p) >= 2 and p[-1][0] - p[0][0] >= 9000:
        gap = max(b[0] - a[0] for a, b in zip(p, p[1:]))
        e = s.baro.elev
        moved = (max(x[1] for x in e) - min(x[1] for x in e)) if e else 9999
        inp.update(baroDrop=p[0][1] - p[-1][1], baroStill=moved <= 30 and gap <= 3600, baroNow=p[-1][1])
    else:
        inp.update(baroDrop=None, baroStill=False, baroNow=None)
    return inp


cases = []
for scn in SC:
    seq = scn["build"]()
    st = {}
    raises = []
    for snap, extra in seq:
        st.update(extra)
        r = run(copy.deepcopy(snap), 2, st)
        inp = to_inputs(snap)
        inp["todaySeenOff"] = bool(extra.get("first_raise"))
        raises.append({"inputs": inp, "py": [r.chosen.word, r.chosen.detail, r.chosen.line1, r.chosen.line2, r.chosen.tier]})
    cases.append({"num": scn["num"], "title": scn["title"], "raises": raises})
json.dump(cases, open(sys.argv[1] if len(sys.argv) > 1 else "cases.json", "w"))
print(len(cases), "scenarios exported")
