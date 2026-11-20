"""Scenarios: the audit's 31 cases plus the ones that matter for this face (Europe and North America first).
Each scenario returns a list of (Snapshot, extra_state) raises; most are a single raise, sequences test memory."""
from datetime import datetime, timedelta
from data import (Snapshot, Fetch, Hour, Baro, hours_from, m15_from_hours, sun_for, stationary_baro, tz, H, Q)

P = {  # lat, lon, tz, elevation
    "BUC": (44.43, 26.10, "Europe/Bucharest", 83), "OMU": (45.445, 25.456, "Europe/Bucharest", 2497),
    "SNAGOV": (44.70, 26.15, "Europe/Bucharest", 80), "MUN": (48.14, 11.58, "Europe/Berlin", 524),
    "DEN": (39.74, -104.99, "America/Denver", 1597), "HEL": (60.17, 24.94, "Europe/Helsinki", 7),
    "UTS": (69.91, 27.03, "Europe/Helsinki", 100), "DEL": (28.61, 77.21, "Asia/Kolkata", 217),
    "NAI": (-1.29, 36.82, "Africa/Nairobi", 1668), "ASP": (-23.70, 133.88, "Australia/Darwin", 581),
}


def snap(name, place, when, fields=None, age=15, m15=None, daily=None, aq=None, sun=None, baro=None, alt=None,
         ok=True, error=None, moon=None, dist=0.0, fixed_tz=False, pollen_on=False, hours=30):
    lat, lon, z, elev = P[place]
    now = datetime.fromisoformat(when).replace(tzinfo=tz(z))
    hs = hours_from(now, n=hours, **(fields or {})) if ok else []
    f = Fetch(ok=ok, age_min=age, error=error, hours=hs, grid_elev=elev, daily=daily or {"tmax": 20, "tmin": 10,
              "uv_max": 4}, aq=aq)
    if ok:
        f.m15 = m15_from_hours(hs, now, native=m15)
    s = Snapshot(name=name, now=now, lat=lat, lon=lon, fetch=f, sun=sun, moon=moon, fc_dist_km=dist,
                 altitude=alt if alt is not None else elev, baro=baro or Baro(), tz_fixed_offset=fixed_tz,
                 pollen_on=pollen_on)
    return s


def at(now_str, place):
    return datetime.fromisoformat(now_str).replace(tzinfo=tz(P[place][2]))


def SUN(now_str, place, rise, set_, **k):
    return sun_for(at(now_str, place), rise, set_, **k)


SC = []


def scenario(num, title, expect, gate=None):
    def deco(fn):
        SC.append({"num": num, "title": title, "expect": expect, "build": fn, "gate": gate})
        return fn
    return deco


day = lambda tmax, tmin, uvmax=6, sun_h=8, **k: dict(tmax=tmax, tmin=tmin, uv_max=uvmax, sunshine_s=sun_h * H, **k)


def diurnal(tmin, tmax, peak=15):
    import math
    return lambda dt, loc: tmin + (tmax - tmin) * max(0.0, math.cos((loc.hour - peak) / 12 * math.pi)) ** 1.5


# ------------------------------------------------------------------------------------------------ heat and calm
@scenario("01", "Bucharest July, 39° dry air, UV 9",
          "One HEAT (air path), no permanent UV lock; heat index alone under-reads dry heat")
def s01():
    w = "2026-07-15 14:00"
    return [(snap("01", "BUC", w, dict(temp=diurnal(24, 39), rh=18, uv=lambda d, l: 9 if 10 <= l.hour <= 15 else 3,
                                       sun_s=3600, cloud=5), daily=day(40, 24, 9, 13),
                  sun=SUN(w, "BUC", (5, 45), (20, 55))), {})]


@scenario("02", "Bucharest, calm 28° summer day, raises from dawn to night",
          "Quiet varies with the time of day: dawn, TODAY, sunny, tomorrow, night; no invented hazard")
def s02():
    out = []
    for i, w in enumerate(["2026-07-20 04:40", "2026-07-20 07:10", "2026-07-20 11:00", "2026-07-20 15:30",
                           "2026-07-20 21:30", "2026-07-20 23:40"]):
        tm = {"tmax": 29, "tmin": 18, "prob": 10, "hours": hours_from(at("2026-07-21 00:00", "BUC"), n=24,
                                                                         temp=diurnal(18, 29))}
        out.append((snap("02", "BUC", w, dict(temp=diurnal(17, 28), rh=45, uv=lambda d, l: 7 if 11 <= l.hour <= 14 else 3,
                                              sun_s=lambda d, l: 3600 if 7 <= l.hour <= 19 else 0, cloud=10),
                         daily=day(28, 17, 7, 13, tomorrow=tm), sun=SUN(w, "BUC", (5, 50), (20, 50)),
                         moon={"rise": at("2026-07-20 03:10", "BUC"), "set": at("2026-07-20 17:40", "BUC"), "phase": 0.08}),
                    {"first_raise": i == 1}))
    return out


# ------------------------------------------------------------------------------------------------ storms, pressure
@scenario("03", "CAPE 1800, no thunderstorm code, no rain", "No STORM message from instability alone",
          gate=lambda r: not r.chosen.family == "STORM")
def s03():
    w = "2026-07-10 12:00"
    return [(snap("03", "MUN", w, dict(temp=29, rh=55, cape=1800, li=-4, code=2), daily=day(31, 18),
                  sun=SUN(w, "MUN", (5, 30), (21, 10))), {})]


@scenario("04", "Thunderstorm code 95 next hour, no pressure fall", "Forecast STORM can reach act-now; baro not required",
          gate=lambda r: r.chosen.family == "STORM" and r.chosen.tier == 1)
def s04():
    w = "2026-07-10 15:20"
    return [(snap("04", "MUN", w, dict(code=lambda d, l: 95 if 0.5 < d < 3 else 2, precip=lambda d, l: 6 if 0.5 < d < 3 else 0,
                                       prob=lambda d, l: 70 if 0.5 < d < 3 else 10, cape=1500, gust=lambda d, l: 68 if 0.5 < d < 3 else 25),
                  daily=day(30, 18), sun=SUN(w, "MUN", (5, 30), (21, 10)), baro=stationary_baro(at(w, "MUN"), 0.5)), {})]


@scenario("05", "Mountain hike, 600 m climb in 3 h, CAPE 1200", "No storm or baro claim from a climb",
          gate=lambda r: r.chosen.family not in ("STORM", "BARO"))
def s05():
    w = "2026-08-02 13:00"
    return [(snap("05", "OMU", w, dict(temp=12, cape=1200, code=2), daily=day(14, 6),
                  sun=SUN(w, "OMU", (6, 10), (20, 30)), baro=stationary_baro(at(w, "OMU"), 0, 600, base=760, alt=1900),
                  alt=2500), {})]


@scenario("06", "Stationary watch, pressure -5 hPa in 3 h, online, no storm code", "Descriptive at most; no storm claim",
          gate=lambda r: r.chosen.family != "STORM")
def s06():
    w = "2026-10-12 10:00"
    return [(snap("06", "BUC", w, dict(temp=14, code=3, cloud=90), daily=day(16, 9, 3, 1),
                  sun=SUN(w, "BUC", (7, 25), (18, 40)), baro=stationary_baro(at(w, "BUC"), 5)), {})]


@scenario("06b", "Same pressure fall, phone offline 14 h", "Offline: BARO FALLING FAST from the watch, labelled as such",
          gate=lambda r: r.chosen.family == "BARO")
def s06b():
    w = "2026-10-12 10:00"
    return [(snap("06b", "BUC", w, ok=False, error="NO PHONE", sun=SUN(w, "BUC", (7, 25), (18, 40)),
                  baro=stationary_baro(at(w, "BUC"), 5)), {})]


# ------------------------------------------------------------------------------------------------ wind
@scenario("07", "Lake Snagov, gusts rising 18 to 43 km/h over 2 h", "WIND RISING before any strong-wind threshold",
          gate=lambda r: r.chosen.id == "WINDUP")
def s07():
    w = "2026-05-03 11:10"
    return [(snap("07", "SNAGOV", w, dict(gust=lambda d, l: 18 if d < 1 else (31 if d < 2 else 43), wind=lambda d, l: 8 if d < 1 else 20),
                  daily=day(22, 10), sun=SUN(w, "SNAGOV", (6, 10), (20, 15))), {})]


@scenario("08", "Gusts steady at 55 km/h", "GUST tier 5 in km/h, no Beaufort label, no WIND RISING",
          gate=lambda r: r.chosen.id == "GUST5" and "F7" not in r.chosen.line1)
def s08():
    w = "2026-11-02 12:00"
    return [(snap("08", "BUC", w, dict(gust=55, wind=30), daily=day(12, 5), sun=SUN(w, "BUC", (6, 55), (17, 2))), {})]


@scenario("34", "Gusts wobbling around the act-now line: 66, 62, 59, 57, 63 km/h, raises 10 min apart",
          "v1 flips between act-now and tier 5; v2 holds act-now until gusts fall under 58")
def s34():
    out = []
    for i, g in enumerate([66, 62, 59, 57, 63]):
        w = (datetime(2026, 11, 2, 12, 0) + timedelta(minutes=10 * i)).isoformat(sep=" ")
        out.append((snap("34", "MUN", w, dict(gust=g, wind=35), daily=day(10, 4), sun=SUN(w, "MUN", (7, 5), (16, 50))), {}))
    return out


# ------------------------------------------------------------------------------------------------ rain timing
@scenario("09", "Bucharest (hourly model), rain in the 15:00-16:00 block, raise at 14:15",
          "No minute countdown from interpolated data; hour-level 'FROM ~15:00'",
          gate=lambda r: "MIN" not in r.chosen.detail)
def s09():
    w = "2026-04-14 14:15"
    return [(snap("09", "BUC", w, dict(precip=lambda d, l: 2.0 if 1 <= d < 3 else 0, prob=lambda d, l: 70 if 1 <= d < 3 else 10,
                                       code=lambda d, l: 63 if 1 <= d < 3 else 3), daily=day(16, 8),
                  sun=SUN(w, "BUC", (6, 45), (20, 0))), {})]


@scenario("10", "Denver (HRRR, native 15 min), rain starting 15:15, raise at 14:30",
          "Quarter-hour timing allowed: '~45 MIN'", gate=lambda r: r.chosen.id == "RAIN3")
def s10():
    w = "2026-06-10 14:30"
    return [(snap("10", "DEN", w, dict(precip=lambda d, l: 1.5 if 1 <= d < 3 else 0, prob=lambda d, l: 60 if 1 <= d < 3 else 5,
                                       code=lambda d, l: 61 if 1 <= d < 3 else 2),
                  m15=[0, 0, 0, 0.3, 0.4, 0.5, 0.4, 0.4], daily=day(26, 12), sun=SUN(w, "DEN", (5, 32), (20, 28))), {})]


@scenario("11", "Forecast drizzle 0.1-0.2 mm, probability 15%", "No rain-start message for negligible drizzle",
          gate=lambda r: r.chosen.id != "RAIN3")
def s11():
    w = "2026-09-20 10:00"
    return [(snap("11", "MUN", w, dict(precip=lambda d, l: 0.2 if 1 <= d < 2 else 0, prob=15, code=lambda d, l: 51 if 1 <= d < 2 else 3),
                  m15=[0, 0, 0, 0.05, 0.05, 0.1, 0.0, 0], daily=day(17, 9), sun=SUN(w, "MUN", (7, 5), (19, 20))), {})]


@scenario("12", "Munich showers with a 20-minute break", "No DRY claim for a 20-minute gap",
          gate=lambda r: r.chosen.id != "DRY3")
def s12():
    w = "2026-06-03 13:00"
    return [(snap("12", "MUN", w, dict(precip=lambda d, l: 1.2 if d < 5 else 0, prob=80, code=lambda d, l: 80 if d < 5 else 3),
                  m15=[0.4, 0.3, 0.0, 0.4, 0.5, 0.4, 0.3, 0.3], daily=day(20, 12), sun=SUN(w, "MUN", (5, 15), (21, 10))), {})]


@scenario("13", "Rain stopping, then dry for 4 h", "DRY eligible, at the real precision",
          gate=lambda r: r.chosen.id == "DRY3")
def s13():
    w = "2026-06-03 13:00"
    return [(snap("13", "MUN", w, dict(precip=lambda d, l: 1.2 if d < 1 else (0 if d < 5 else 1.0), prob=lambda d, l: 80 if d < 1 else 20,
                                       code=lambda d, l: 61 if d < 1 else 3),
                  m15=[0.4, 0.3, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0], daily=day(20, 12), sun=SUN(w, "MUN", (5, 15), (21, 10))), {})]


@scenario("14", "Munich: rain in 20 min, sunset in 25 min", "Imminent rain wins, sunset kept in line 2",
          gate=lambda r: r.chosen.id == "RAIN3" and "SUNSET" in r.chosen.line2)
def s14():
    w = "2026-10-20 17:50"
    return [(snap("14", "MUN", w, dict(precip=lambda d, l: 2.0 if 0 <= d < 3 else 0, prob=80, code=lambda d, l: 63 if 0 <= d < 3 else 3),
                  m15=[0, 0.4, 0.5, 0.5, 0.6, 0.5, 0.5, 0.5], daily=day(14, 6), sun=SUN(w, "MUN", (7, 40), (18, 15))), {})]


@scenario("14b", "Same, but in Bucharest (hourly model)", "Cannot resolve 20 minutes: the sunset countdown stays")
def s14b():
    w = "2026-10-20 18:05"
    return [(snap("14b", "BUC", w, dict(precip=lambda d, l: 2.0 if 0 <= d < 3 else 0, prob=80, code=lambda d, l: 63 if 0 <= d < 3 else 3),
                  daily=day(14, 6), sun=SUN(w, "BUC", (7, 30), (18, 30))), {})]


@scenario("25", "Hourly rain 8 mm stamped 16:00, raise 14:40", "Read as rain over 15:00-16:00, heavy from ~15:00",
          gate=lambda r: "15:00" in (r.chosen.detail + r.chosen.line1 + r.chosen.line2))
def s25():
    w = "2026-07-04 14:40"
    return [(snap("25", "BUC", w, dict(precip=lambda d, l: 8 if 1.0 < d <= 1.4 else 0, prob=lambda d, l: 80 if 1.0 < d <= 1.4 else 10,
                                       code=lambda d, l: 65 if 0.3 < d <= 1.4 else 2), daily=day(30, 19),
                  sun=SUN(w, "BUC", (5, 40), (20, 55))), {})]


@scenario("29", "Delhi monsoon, about 40 mm over 6 h", "Accumulation reported plainly; no flood talk")
def s29():
    w = "2026-07-22 11:00"
    return [(snap("29", "DEL", w, dict(precip=lambda d, l: 7 if d < 6 else 1, prob=90, code=63, temp=30, rh=88),
                  daily=day(32, 27, 6, 1), sun=SUN(w, "DEL", (5, 40), (19, 15))), {})]


# ------------------------------------------------------------------------------------------------ fog, ice, snow
@scenario("15", "Freezing fog, code 48, -2°, visibility 300 m", "Freezing fog stated; no road-ice claim",
          gate=lambda r: r.chosen.family == "FOG" and "FREEZING" in (r.chosen.detail + r.chosen.line1))
def s15():
    w = "2026-12-12 08:00"
    return [(snap("15", "BUC", w, dict(code=lambda d, l: 48 if d < 2 else 3, vis=lambda d, l: 300 if d < 2 else 4000, temp=-2, rh=99),
                  daily=day(1, -4), sun=SUN(w, "BUC", (7, 40), (16, 35))), {})]


@scenario("36", "Model visibility 600 m, no fog code", "v2 does not raise fog from visibility alone")
def s36():
    w = "2026-11-05 07:30"
    return [(snap("36", "BUC", w, dict(vis=600, rh=93, code=3), daily=day(12, 6), sun=SUN(w, "BUC", (7, 0), (16, 55))), {})]


@scenario("35", "Freezing-rain code 66 in the next hour", "Forecast wording 'ICE ~1 H', not 'ICE NOW'",
          gate=lambda r: r.chosen.family == "ICE" and r.chosen.detail != "NOW")
def s35():
    w = "2026-01-14 09:20"
    return [(snap("35", "BUC", w, dict(code=lambda d, l: 66 if 0.5 < d < 3 else 3, precip=lambda d, l: 1 if 0.5 < d < 3 else 0,
                                       prob=70, temp=-1), daily=day(1, -3), sun=SUN(w, "BUC", (7, 50), (16, 55))), {})]


@scenario("16", "7 cm of new snow over 6 h, light wind", "SNOW total, no blizzard wording",
          gate=lambda r: r.chosen.family in ("SNOW", "RAIN") and "BLOWING" not in r.chosen.line1)
def s16():
    w = "2026-01-20 09:00"
    return [(snap("16", "BUC", w, dict(snow=lambda d, l: 1.2 if -2 < d < 8 else 0, precip=lambda d, l: 1.7 if -2 < d < 8 else 0,
                                       prob=90, code=73, temp=-3, gust=20), daily=day(-1, -5), sun=SUN(w, "BUC", (7, 45), (17, 10))), {})]


@scenario("32", "Viscol: snow 2 cm/h, gusts 70, visibility 300 m", "Act-now blowing snow",
          gate=lambda r: r.chosen.family == "SNOW" and r.chosen.tier == 1)
def s32():
    w = "2026-01-24 18:30"
    return [(snap("32", "BUC", w, dict(snow=2, precip=3, prob=95, code=75, temp=-4, gust=70, wind=45, vis=300),
                  daily=day(-2, -7), sun=SUN(w, "BUC", (7, 40), (17, 15))), {})]


@scenario("32b", "Light snow 0.3 cm/h with 60 km/h gusts, visibility 5 km", "Not a blizzard: tier 5 at most")
def s32b():
    w = "2026-01-24 12:30"
    return [(snap("32b", "BUC", w, dict(snow=0.3, precip=0.4, prob=60, code=71, temp=-2, gust=60, wind=35, vis=5000),
                  daily=day(-1, -6), sun=SUN(w, "BUC", (7, 40), (17, 15))), {})]


@scenario("33", "Bucegi hike at 2000 m, snowfall height 2200 m, rain in 2 h", "SNOW LINE where the model gives it")
def s33():
    w = "2026-10-03 11:00"
    return [(snap("33", "OMU", w, dict(precip=lambda d, l: 1.5 if 2 <= d < 6 else 0, prob=70, code=lambda d, l: 61 if 2 <= d < 6 else 3,
                                       snow_h=2200, temp=4), daily=day(6, 1), sun=SUN(w, "OMU", (7, 15), (18, 55)), alt=2000), {})]


@scenario("33b", "Rockies hike, same weather, no snowfall_height in NA models", "No snow-line message, reason given")
def s33b():
    w = "2026-10-03 11:00"
    return [(snap("33b", "DEN", w, dict(precip=lambda d, l: 1.5 if 2 <= d < 6 else 0, prob=70, code=lambda d, l: 61 if 2 <= d < 6 else 3,
                                        snow_h=None, temp=4), daily=day(6, 1), sun=SUN(w, "DEN", (7, 5), (18, 40)), alt=3200), {})]


# ------------------------------------------------------------------------------------------------ air, pollen, UV
EU_OZONE = {"age_min": 30, "eaqi": 75, "usaqi": 120, "sub_eu": {"pm2_5": 20, "pm10": 15, "ozone": 75, "no2": 10},
            "sub_us": {"pm2_5": 60, "ozone": 120}, "sub": {"pm2_5": 12, "pm10": 20}, "dust": 5, "pollen": None}


@scenario("17", "EU AQI 75 driven by ozone, PM2.5 low", "Right scale and the real driver (ozone)",
          gate=lambda r: "OZONE" in r.chosen.line1)
def s17():
    w = "2026-07-18 16:00"
    return [(snap("17", "BUC", w, dict(temp=31, rh=35), daily=day(32, 20), aq=EU_OZONE, sun=SUN(w, "BUC", (5, 50), (20, 50))), {})]


@scenario("18", "Pollen asked outside Europe (Denver, winter)", "No pollen message, no zero claimed")
def s18():
    w = "2026-01-10 12:00"
    aq = dict(EU_OZONE, eaqi=20, usaqi=30, pollen={"grass": None, "ragweed": None})
    return [(snap("18", "DEN", w, dict(temp=2), daily=day(4, -6), aq=aq, sun=SUN(w, "DEN", (7, 20), (16, 55)), pollen_on=True), {})]


@scenario("18b", "Bucharest, ragweed 140 grains/m3, pollen setting off (default)", "Pollen stays silent until opted in")
def s18b():
    w = "2026-08-28 10:00"
    aq = dict(EU_OZONE, eaqi=30, sub_eu={"pm2_5": 30}, pollen={"ragweed": 140, "grass": 10})
    return [(snap("18b", "BUC", w, dict(temp=27), daily=day(30, 17), aq=aq, sun=SUN(w, "BUC", (6, 35), (20, 0))), {})]


@scenario("23", "UV 9 for six hours, nothing else, raises every 30 min 10:00-16:00",
          "UV first, then Quiet, with a reminder; never six hours of lock-out")
def s23():
    out = []
    for i in range(13):
        w = (datetime(2026, 7, 8, 10, 0) + timedelta(minutes=30 * i)).isoformat(sep=" ")
        out.append((snap("23", "BUC", w, dict(uv=lambda d, l: 9 if 10 <= l.hour < 16 else 4, temp=27, sun_s=3600, cloud=5),
                         daily=day(28, 17, 9, 13), sun=SUN(w, "BUC", (5, 50), (20, 50))), {}))
    return out


@scenario("30", "Nairobi 1670 m, UV 12, air 24°", "UV qualifies; no heat message",
          gate=lambda r: r.chosen.family == "UV")
def s30():
    w = "2026-02-10 12:30"
    return [(snap("30", "NAI", w, dict(uv=lambda d, l: 12 if 10 <= l.hour <= 14 else 5, temp=24, rh=40, cloud=10),
                  daily=day(26, 13, 12, 9), sun=SUN(w, "NAI", (6, 35), (18, 45))), {})]


@scenario("31", "Alice Springs 43°, humidity 8%", "Air-temperature path catches dry heat; no sub-hour timing",
          gate=lambda r: r.chosen.family == "HEAT" and r.chosen.tier == 1)
def s31():
    w = "2026-01-12 14:00"
    return [(snap("31", "ASP", w, dict(temp=lambda d, l: 43 - abs(d) * 0.5, rh=8, uv=11), daily=day(44, 26, 12, 12),
                  sun=SUN(w, "ASP", (6, 5), (19, 40))), {})]


@scenario("26", "Feels 41° and air 40° at once", "Exactly one HEAT with consistent evidence")
def s26():
    w = "2026-07-30 15:00"
    return [(snap("26", "BUC", w, dict(temp=lambda d, l: 40 - abs(d), rh=28), daily=day(40, 25, 9),
                  sun=SUN(w, "BUC", (6, 5), (20, 40))), {})]


@scenario("39", "Denver, -20° with 40 km/h wind (wind chill about -34°)", "Act-now COLD, honest 'MILDER' time")
def s39():
    w = "2026-01-15 07:30"
    return [(snap("39", "DEN", w, dict(temp=lambda d, l: -20 + max(0, d) * 0.8, wind=40, gust=55), daily=day(-8, -21),
                  sun=SUN(w, "DEN", (7, 18), (17, 5))), {})]


# ------------------------------------------------------------------------------------------------ temperature changes
@scenario("27", "Temperature falls 6° between 17:00 and 20:00, no wind shift", "No 'FRONT' from evening cooling",
          gate=lambda r: r.chosen.family != "TEMP")
def s27():
    w = "2026-09-15 16:50"
    return [(snap("27", "BUC", w, dict(temp=lambda d, l: 24 - max(0, d) * 2.0, wdir=200, gust=15), daily=day(25, 12),
                  sun=SUN(w, "BUC", (6, 55), (19, 25))), {})]


@scenario("27b", "Midday drop of 8° with the wind turning NW and gusts rising", "COLDER, with the wind shift as evidence",
          gate=lambda r: r.chosen.family in ("TEMP", "GUST"))
def s27b():
    w = "2026-09-15 12:10"
    return [(snap("27b", "BUC", w, dict(temp=lambda d, l: 26 - max(0, min(d, 3)) * 2.7, wdir=lambda d, l: 200 if d < 1 else 320,
                                        gust=lambda d, l: 20 if d < 1 else 48), daily=day(26, 12), sun=SUN(w, "BUC", (6, 55), (19, 25))), {})]


@scenario("37", "October evening, mild day (14°), low -2° at 06:00 under 60% cloud", "FROST without a 'clear and calm' claim",
          gate=lambda r: r.chosen.id != "FROST" or "CLEAR" not in r.chosen.line2)
def s37():
    w = "2026-10-21 19:30"
    return [(snap("37", "BUC", w, dict(temp=lambda d, l: 8 - min(max(d, 0), 10) * 1.0, cloud=60, wind=6), daily=day(14, -2),
                  sun=SUN(w, "BUC", (7, 40), (18, 20))), {})]


@scenario("38", "Summer evening, coming night's minimum 23°", "Hot night as evening Quiet, not an advisory")
def s38():
    w = "2026-07-27 21:30"
    tm = {"tmax": 36, "tmin": 23, "prob": 5, "hours": hours_from(at("2026-07-28 00:00", "BUC"), n=24, temp=diurnal(23, 36))}
    return [(snap("38", "BUC", w, dict(temp=lambda d, l: 27 - max(0, min(d, 8)) * 0.5), daily=day(36, 23, 9, 13, tomorrow=tm),
                  sun=SUN(w, "BUC", (6, 5), (20, 45))), {})]


@scenario("40", "Bucharest winter, 17:30 (sunset 16:50), rain tomorrow from 09:00", "Tomorrow's outlook after dusk, with hourly times",
          gate=lambda r: r.chosen.id == "TMRW")
def s40():
    w = "2026-12-03 17:30"
    tm = {"tmax": 6, "tmin": 1, "prob": 70, "hours": hours_from(at("2026-12-04 00:00", "BUC"), n=24,
                                                                 precip=lambda d, l: 1.2 if 10 <= l.hour <= 15 else 0,
                                                                 prob=lambda d, l: 70 if 10 <= l.hour <= 15 else 10)}
    return [(snap("40", "BUC", w, dict(temp=3), daily=day(5, 0, 1, 2, tomorrow=tm), sun=SUN(w, "BUC", (7, 35), (16, 50))), {})]


# ------------------------------------------------------------------------------------------------ data quality
@scenario("19", "Utsjoki, Finland, polar night", "No sunrise/sunset countdown",
          gate=lambda r: r.chosen.family != "LIGHT" and "SUNSET" not in r.chosen.line1)
def s19():
    w = "2026-12-15 12:00"
    return [(snap("19", "UTS", w, dict(temp=-15, wind=5), daily=day(-13, -18, 0, 0), sun={"polar": "NIGHT"}), {})]


@scenario("20", "DST ends in Bucharest at 04:00; rain from 01:00 UTC; raise 02:30 summer time",
          "Local times follow the clock change (rain from 03:00 EET). First raise formats with the fetch's fixed "
          "UTC offset (the trap the audit names), second with real time-zone rules",
          gate=None)
def s20():
    out = []
    for fixed in (True, False):
        w = "2026-10-25 02:30"
        out.append((snap("20", "BUC", w, dict(precip=lambda d, l: 2.0 if 2.4 <= d < 5 else 0, prob=80,
                                              code=lambda d, l: 63 if 2.4 <= d < 5 else 3),
                         daily=day(14, 6), sun=SUN(w, "BUC", (7, 30), (18, 25)), fixed_tz=fixed), {}))
    return out


@scenario("21", "Phone offline, forecast 13 h old, location known", "No forecast claims; astronomy or watch baro instead",
          gate=lambda r: r.chosen.basis in ("astronomy", "watch"))
def s21():
    w = "2026-05-10 09:00"
    s = snap("21", "BUC", w, dict(precip=lambda d, l: 2 if 1 <= d < 3 else 0, prob=70, code=63), age=13 * 60,
             daily=day(20, 9), sun=SUN(w, "BUC", (6, 5), (20, 25)))
    return [(s, {})]


@scenario("21b", "Gusts of 70 forecast, but the fetch is 3 h old", "Not act-now on 3-hour-old data (tier 5 at most)",
          gate=lambda r: not (r.chosen.family == "GUST" and r.chosen.tier == 1))
def s21b():
    w = "2026-11-02 12:00"
    return [(snap("21b", "MUN", w, dict(gust=70, wind=40), age=180, daily=day(10, 4), sun=SUN(w, "MUN", (7, 5), (16, 50))), {})]


@scenario("22", "Phone offline, no usable location", "No invented sun times, no 'CALM DRY 12H+'; the reason instead",
          gate=lambda r: r.chosen.id == "NODATA")
def s22():
    w = "2026-05-10 09:00"
    return [(snap("22", "BUC", w, ok=False, error="NO GPS", sun=None), {})]


@scenario("24", "Helsinki: lifted index and visibility missing (null)", "Missing fields treated as unknown, no crash",
          gate=lambda r: True)
def s24():
    w = "2026-03-10 12:00"
    return [(snap("24", "HEL", w, dict(li=None, vis=None, temp=1, code=45, rh=98), daily=day(2, -3), sun=SUN(w, "HEL", (7, 10), (18, 5))), {})]


@scenario("28", "Fresh fetch, but for a position 60 km away; gusts 70 there", "No precise act-now claim for somewhere else",
          gate=lambda r: not (r.chosen.family == "GUST" and r.chosen.tier == 1))
def s28():
    w = "2026-11-02 12:00"
    return [(snap("28", "MUN", w, dict(gust=70, wind=40), dist=60, daily=day(10, 4), sun=SUN(w, "MUN", (7, 5), (16, 50))), {})]


@scenario("42", "Gusts of 70 forecast; the phone drops out and the fetch ages: 30, 100, 250, 800 min",
          "Urgency fades with the data: act-now, then tier 5, then nothing from the forecast, then astronomy")
def s42():
    out = []
    for i, age in enumerate([30, 100, 250, 800]):
        w = "2026-11-02 12:00"
        out.append((snap("42", "MUN", w, dict(gust=70, wind=40), age=age, daily=day(10, 4),
                         sun=SUN(w, "MUN", (7, 5), (16, 50)), baro=stationary_baro(at(w, "MUN"), 1.0)), {}))
    return out


@scenario("43", "Same rain forecast fetched again 30 min later (same event), then moved one hour later",
          "Event identity: a re-fetch is not a new event; a real shift is")
def s43():
    out = []
    for i, (w, shift) in enumerate([("2026-04-14 13:20", 0), ("2026-04-14 13:50", 0), ("2026-04-14 14:20", 1)]):
        base = at("2026-04-14 13:20", "BUC").timestamp()
        def pr(d, l, shift=shift, base=base, w=w):
            hrs = (at(w, "BUC").timestamp() - base) / 3600 + d
            return 2.0 if 2 + shift <= hrs < 4 + shift else 0
        out.append((snap("43", "BUC", w, dict(precip=pr, prob=70, code=3), daily=day(16, 8),
                         sun=SUN(w, "BUC", (6, 45), (20, 0))), {}))
    return out


@scenario("44", "Ordinary hot Bucharest afternoon, 33° and 40% humidity, raises 11:30 to 15:30",
          "HEAT tier 5 is shown, then yields to Quiet: a common summer day must not become a day-long alert")
def s44():
    out = []
    for i in range(9):
        w = (datetime(2026, 7, 22, 11, 30) + timedelta(minutes=30 * i)).isoformat(sep=" ")
        out.append((snap("44", "BUC", w, dict(temp=diurnal(20, 33), rh=40, uv=lambda d, l: 7, sun_s=3600, cloud=10),
                         daily=day(33, 20, 7, 13), sun=SUN(w, "BUC", (6, 0), (20, 45))), {}))
    return out
