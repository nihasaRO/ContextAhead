"""Normalised inputs for the Context simulation.

One Snapshot = everything the watch would know at one wrist raise: the clock, the location (with its age), the last
Open-Meteo fetch (with its age and the time resolution that is real at this location), the watch's own pressure and
elevation history, the sun times, and the engine's memory of what it showed before.

All series are on a UTC epoch grid. Open-Meteo semantics are kept exactly:
  * hourly precipitation, rain, snowfall, probability, sunshine and wind_gusts_10m describe the PRECEDING hour
    (the value stamped 16:00 is the 15:00-16:00 interval); temperature, humidity, cape, visibility, code are instants.
  * minutely_15 precipitation is the preceding 15 minutes; outside the native domains it is interpolated hourly data.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import math

H = 3600
Q = 900

# Native 15-minute domains, approximated as boxes (Open-Meteo: HRRR for North America, ICON-D2 and AROME for
# Central Europe; everything else is hourly data interpolated to 15 minutes). On the watch this is a table of a few
# bytes. The boxes are deliberately conservative: a place near an edge counts as hourly.
NATIVE15 = [(25.0, 49.0, -125.0, -67.0),     # HRRR, CONUS
            (43.5, 55.5, -4.0, 19.5)]        # ICON-D2 / AROME France HD, Central Europe (approximate)

# Where pollen exists at all (CAMS Europe); elsewhere Open-Meteo returns null.
EUROPE = (34.0, 72.0, -25.0, 45.0)


def in_box(lat, lon, b):
    return b[0] <= lat <= b[1] and b[2] <= lon <= b[3]


def resolution_at(lat, lon):
    return "native15" if any(in_box(lat, lon, b) for b in NATIVE15) else "hourly"


@dataclass
class Hour:
    """Values stamped at time t (UTC epoch, top of the hour)."""
    t: int
    temp: float = 15.0          # °C, instant
    rh: float = 60.0            # %, instant
    wind: float = 10.0          # km/h, instant
    wdir: float = 225.0         # deg, instant
    gust: float = 20.0          # km/h, max of the preceding hour
    precip: float = 0.0         # mm, preceding hour (rain + showers + snow water)
    snow: float = 0.0           # cm, preceding hour
    prob: float = 0.0           # %, preceding hour (ensemble, ~27 km)
    code: int = 1               # WMO, instant
    cape: float = 0.0           # J/kg
    li: float = None            # lifted index (null in some models, e.g. Nordic)
    vis: float = 30000.0        # m (model value; weak outside AROME/HRRR)
    uv: float = 0.0
    cloud: float = 30.0         # %
    sun_s: float = 0.0          # s of sunshine in the preceding hour
    snow_h: float = None        # m, snowfall_height (Europe models only; null in NA)


@dataclass
class Fetch:
    ok: bool = True
    age_min: float = 15.0                 # minutes since the last successful fetch
    error: str = None                     # NO PHONE, NO GPS, ERR 503...
    hours: list = field(default_factory=list)
    m15: list = field(default_factory=list)       # (t, precip_mm) preceding 15 min
    grid_elev: float = 100.0
    daily: dict = field(default_factory=dict)     # tmax, tmin, uv_max, sunshine_s, tomorrow{...}, moonrise...
    aq: dict = None                               # {age_min, eaqi, usaqi, sub:{pm2_5:..}, dust, pollen:{...}}


@dataclass
class Baro:
    """Watch history: (t, hPa) and (t, m). Pressure history is ambient (station) pressure in Pa on the watch;
    here already in hPa. Elevation history gates any weather reading of a pressure change."""
    press: list = field(default_factory=list)
    elev: list = field(default_factory=list)


@dataclass
class Snapshot:
    name: str
    now: datetime                         # aware, local
    lat: float
    lon: float
    loc_age_min: float = 10.0
    fc_dist_km: float = 0.0               # distance between the forecast point and the watch's position
    altitude: float = None                # watch altitude, m
    fetch: Fetch = None
    baro: Baro = field(default_factory=Baro)
    sun: dict = None                      # rise, set, civil_dawn, civil_dusk (aware datetimes) or polar flag
    moon: dict = None                     # rise, set, phase 0-1 (from Open-Meteo daily)
    pollen_on: bool = False               # opt-in setting
    tz_fixed_offset: bool = False         # simulate the old fixed-offset formatting bug

    @property
    def ts(self):
        return int(self.now.timestamp())

    @property
    def res(self):
        return resolution_at(self.lat, self.lon)

    def local(self, t):
        """Local wall-clock time of epoch t, with the real tz rules (v2) or the fetch-time offset (v1)."""
        if self.tz_fixed_offset:
            return datetime.fromtimestamp(t, timezone(self.now.utcoffset()))
        return datetime.fromtimestamp(t, self.now.tzinfo)


# ---------------------------------------------------------------- helpers to build scenarios

def tz(name):
    return ZoneInfo(name)


def hours_from(now, n=30, start_back=2, **fns):
    """Hourly series from (now - start_back h) for n hours. fns map a field to f(dt_hours_from_now, local_dt)."""
    base = int(now.timestamp()) // H * H - start_back * H
    out = []
    for i in range(n):
        t = base + i * H
        dt = (t - now.timestamp()) / H
        loc = datetime.fromtimestamp(t, now.tzinfo)
        h = Hour(t=t)
        for k, f in fns.items():
            setattr(h, k, f(dt, loc) if callable(f) else f)
        out.append(h)
    return out


def m15_from_hours(hours, now, native=None):
    """15-minute precipitation for 2 h. Hourly regions: the hourly sum spread linearly (what Open-Meteo does);
    native regions: an explicit list may be given."""
    start = int(now.timestamp()) // Q * Q + Q
    if native is not None:
        return [(start + i * Q, v) for i, v in enumerate(native)]
    out = []
    for i in range(8):
        t = start + i * Q
        # the hour interval containing (t - Q, t]
        hr = next((h for h in hours if h.t - H < t <= h.t), None)
        out.append((t, (hr.precip / 4.0) if hr else 0.0))
    return out


def sun_for(now, rise, set_, dawn=None, dusk=None, polar=None):
    d = now.date()
    mk = lambda hm: datetime(d.year, d.month, d.day, hm[0], hm[1], tzinfo=now.tzinfo)
    if polar:
        return {"polar": polar}
    r, s = mk(rise), mk(set_)
    return {"rise": r, "set": s,
            "dawn": mk(dawn) if dawn else r - timedelta(minutes=32),
            "dusk": mk(dusk) if dusk else s + timedelta(minutes=32)}


def stationary_baro(now, drop_hpa=0.0, climb_m=0.0, hours=3, base=1012.0, alt=100.0):
    """3 h of 15-minute samples: pressure falls by drop_hpa (weather) and by the climb (about 0.12 hPa per m)."""
    t0 = int(now.timestamp()) - hours * H
    n = hours * 4 + 1
    press, elev = [], []
    for i in range(n):
        f = i / (n - 1)
        press.append((t0 + i * Q, base - drop_hpa * f - climb_m * f * 0.12))
        elev.append((t0 + i * Q, alt + climb_m * f))
    return Baro(press=press, elev=elev)


def heat_index_c(t, rh):
    """NWS heat index (Rothfusz with the NWS adjustments), in °C. Valid from about 27 °C (80 °F)."""
    f = t * 9 / 5 + 32
    simple = 0.5 * (f + 61.0 + (f - 68.0) * 1.2 + rh * 0.094)
    if (simple + f) / 2 < 80:
        hi = simple
    else:
        hi = (-42.379 + 2.04901523 * f + 10.14333127 * rh - 0.22475541 * f * rh - 6.83783e-3 * f * f
              - 5.481717e-2 * rh * rh + 1.22874e-3 * f * f * rh + 8.5282e-4 * f * rh * rh - 1.99e-6 * f * f * rh * rh)
        if rh < 13 and 80 <= f <= 112:
            hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(f - 95)) / 17)
        elif rh > 85 and 80 <= f <= 87:
            hi += ((rh - 85) / 10) * ((87 - f) / 5)
    return (hi - 32) * 5 / 9


def wind_chill_c(t, v_kmh):
    """North American / UK wind chill index. Defined for T <= 10 °C and wind >= 4.8 km/h; else None."""
    if t > 10 or v_kmh < 4.8:
        return None
    return 13.12 + 0.6215 * t - 11.37 * v_kmh ** 0.16 + 0.3965 * t * v_kmh ** 0.16
