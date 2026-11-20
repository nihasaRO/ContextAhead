import Toybox.Lang;
import Toybox.Math;
import Toybox.System;
import Toybox.Time;
import Toybox.Time.Gregorian;

// Context: the one weather or light message most likely to change what you do next.
// The rules are CONTEXT.md revision 2, tested first in tools/sim (Python): evidence and precision checks come
// before ranking, one rain timeline at the resolution that is real at this place, hysteresis for gusts and heat,
// a cooldown for advisories that do not change, and a Quiet schedule when nothing needs attention.
// The face fills the inputs, calls pick() outside its redraw, and draws the result:
//   [icon, word, detail, line 1, line 2, evidence 1, evidence 2, invert, tier, family, id]
// (id 206 is the morning briefing TODAY; the face marks it seen after a wrist raise)
class Context {
    // hourly fields (see WeatherService.mc), unpacked by hv()
    private const T = 0;
    private const RH = 1;
    private const CODE = 2;
    private const PROB = 3;
    private const PR = 4;
    private const SN = 5;
    private const WS = 6;
    private const WD = 7;
    private const GU = 8;
    private const VI = 9;
    private const UV = 10;
    private const CL = 11;
    private const SH = 12;
    private const SU = 13;      // sunshine minutes in the preceding hour
    private const NUL = -9999;
    private const P_SLOT = [0, 0, 0, 1, 2, 2, 1, 3, 1, 3, 2, 1, 3, 0]b;
    private const P_SHIFT = [0, 11, 18, 0, 0, 12, 7, 0, 15, 8, 22, 24, 19, 25]b;
    private const P_BITS = [11, 7, 7, 7, 12, 10, 8, 8, 9, 11, 8, 7, 12, 6]b;
    private const P_OFF = [1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 100, 0];
    private const P_UNIT = [1, 1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 10, 1]b;
    private const DRIVERS = ["PM2.5", "PM10", "NO2", "OZONE", "SO2"];
    private const POLLENS = ["ALDER", "BIRCH", "GRASS", "MUGWORT", "OLIVE", "RAGWEED"];
    private const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

    // families, also their rank inside a tier (lower = usually changes the next decision more)
    const F_STORM = 0;
    const F_ICE = 1;
    const F_SNOW = 2;
    const F_FOG = 3;
    const F_COLD = 4;
    const F_HEAT = 5;
    const F_RAIN = 6;
    const F_TEMP = 7;
    const F_GUST = 8;
    const F_AIR = 9;
    const F_FROST = 10;
    const F_UV = 11;
    const F_DUST = 12;
    const F_POLLEN = 13;
    const F_HOT = 14;
    const F_BARO = 15;
    const F_LIGHT = 16;
    const F_QUIET = 20;

    // candidate layout
    private const K = 0;        // tier x 10 after adjustments
    private const FAM = 1;
    private const SEV = 2;
    private const ONS = 3;      // minutes until it starts
    private const ID = 11;
    private const RAIN3 = 61;
    private const SNOWLINE = 23;
    private const WINDUP = 82;

    // ---- inputs, set by the face before pick()
    var now = 0;               // seconds
    var localMin = 0;          // minutes since local midnight
    var w = null;              // the weather array, or null
    var wAge = 9999;           // minutes since the fetch
    var aq = null;             // air quality (see WeatherService.mc), or null
    var yday = null;           // yesterday [day, high x10 C, rain x10 mm, snow x10 cm] from its last forecast, or null
    var wetT = 0;              // the end of the last wet hour seen (stored by the face; kept up to date here)
    var q15 = false;        // native 15-minute data here (HRRR, ICON-D2/AROME)
    var far = false;           // the forecast point is more than 25 km from the watch
    var riseM = -1;            // sun times today, local minutes (-1 unknown)
    var setM = -1;
    var dawnM = -1;
    var duskM = -1;
    var polar = 0;             // 1 polar day, -1 polar night
    var baroDrop = null;       // hPa lost in 3 h (watch history), or null
    var baroStill = false;     // the watch stayed within 30 m of height and the record has no gap
    var baroNow = null;        // hPa now
    var alt = null;            // m
    var tempF = false;
    var distMi = false;
    var elevFt = false;
    var t24 = true;
    var pollenOn = false;
    var errText = "NO DATA";   // why there is no forecast

    // ---- memory across runs
    private var gustLvl = 0;
    private var heatLvl = 0;
    private var newGust = 0;
    private var newHeat = 0;
    private var lastId = -1;
    private var lastT = 0;
    private var coolFirst;
    private var coolLast;
    private var coolSev;
    private var coolDay = -1;
    var todaySeen = -1;        // the day TODAY was last seen on a wrist raise

    // ---- per run
    private var best = null;
    private var prevC = null;
    private var gustC = null;
    private var snowLine = null;
    private var hasLight2 = false;
    private var shadow = false;
    private var hotQuiet = null;
    private var wetLong = null;
    private var sp0 = null;    // first meaningful wet spell [start, end, mm x10, snow x10, prob]
    private var sp1 = null;    // the next one
    private var spAny = null;  // first wet spell before the quality gate
    private var dShift = false; // the forecast was fetched on an earlier day: its "today" is yesterday

    function initialize() {
        coolFirst = new [17];
        coolLast = new [17];
        coolSev = new [17];
    }

    // =============================================================================================== pick

    function pick() {
        best = null;
        prevC = null;
        gustC = null;
        snowLine = null;
        hotQuiet = null;
        wetLong = null;
        hasLight2 = false;
        if (w != null && (w[3] == null || w[4] == null || w[4] <= 0 || w[0] == null)) {
            w = null;                                    // an incomplete reply counts as no forecast
        }
        newGust = 0;
        newHeat = 0;
        var day = dayKey(now);
        dShift = w != null && dayKey(w[0]) != day;
        if (day != coolDay) {
            coolDay = day;
            coolFirst = new [17];
            coolLast = new [17];
            coolSev = new [17];
        }
        light();
        hazards();
        rain();
        heavyAndTotal();
        uvAir();
        temps();
        icy();
        baro();
        gustLvl = newGust;
        heatLvl = newHeat;
        var c = best;
        if (c != null && c[K] >= 60) {
            c = null;
        }
        if (c == null) {
            c = staleOrQuiet();
        } else {
            compose(c);
        }
        // hold: do not alternate between comparable messages within 15 minutes
        if (prevC != null && c != prevC && prevC[K] == c[K] && prevC[SEV] >= c[SEV] * 0.9 && now - lastT < 900) {
            c = prevC;
        }
        var f = c[FAM];
        if (f < 17 && c[K] == 50) {
            var s = c[SEV].toNumber();
            if (coolFirst[f] == null || ab(coolSev[f] - s) >= 3) {
                coolFirst[f] = now;
                coolSev[f] = s;
            }
            coolLast[f] = now;
        }
        if (c[ID] != lastId) {
            lastId = c[ID];
            lastT = now;
        }
        return [ c[4], c[5], c[6], c[7], c[8], c[9], c[10], c[K] == 10, (c[K] == 19) ? 3 : c[K] / 10, c[FAM], c[ID] ];
    }

    private function hazards() {
        gusts();
        storm();
        fog();
        ice();
        heat();
        cold();
        snow();
    }

    // A candidate. Ranking: tier, then family, then severity, then the sooner one.
    private function add(tier, fam, sev, ons, icon, word, detail, l1, l2, e1, id) {
        var k = tier * 10;
        if (id == RAIN3 && q15 && ons <= 30 && hasLight2) {
            k = 19;                                      // imminent rain beats the sunset countdown
        }
        if (tier == 5 && isPersistent(fam, id) && coolFirst[fam] != null
                && now - coolFirst[fam] >= 3600 && now - coolLast[fam] < 7200 && ab(coolSev[fam] - sev.toNumber()) < 3) {
            k = 65;                                      // shown an hour unchanged: Quiet speaks, reminder after 2 h
        }
        var c = [ k, fam, sev.toFloat(), ons, icon, word, detail, l1, l2, e1, "", id ];
        if (shadow) {
            if (tier <= 5 && better(c, best)) {
                best = c;
            }
            return;
        }
        if (id == lastId) {
            prevC = c;
        }
        if (fam == F_GUST && (gustC == null || c[SEV] > gustC[SEV])) {
            gustC = c;
        }
        if (better(c, best)) {
            best = c;
        }
    }

    private function isPersistent(fam, id) {
        return fam == F_UV || fam == F_AIR || fam == F_DUST || fam == F_POLLEN || fam == F_HEAT
            || (fam == F_GUST && id != WINDUP);
    }

    private function better(a, b) {
        if (b == null) {
            return true;
        }
        if (a[K] != b[K]) {
            return a[K] < b[K];
        }
        if (a[FAM] != b[FAM]) {
            return a[FAM] < b[FAM];
        }
        if (a[SEV] != b[SEV]) {
            return a[SEV] > b[SEV];
        }
        return a[ONS] < b[ONS];
    }

    // A stronger family absorbs a gust it explains; rain shows the snow line.
    private function compose(c) {
        if (gustC != null && gustC != c && gustC[SEV] >= 50) {
            if (c[FAM] == F_STORM && c[7].find("GUST") == null) {
                c[7] = "GUSTS TO " + spd(gustC[SEV]);
            } else if (c[FAM] == F_TEMP) {
                c[8] = "GUSTS TO " + spd(gustC[SEV]);
            }
        }
        if (snowLine != null && c[ID] == RAIN3) {
            if (c[8].find("THEN DRY") == 0) {
                c[9] = c[8];                             // the dry time moves to the wrist-raise line
            }
            c[8] = snowLine;
        }
    }

    // Data age per tier: act now 90, rain within 2 h 90, worth adapting 240, quiet 720 (minutes).
    private function ok(tier) {
        if (w == null) {
            return false;
        }
        var lim = shadow ? 720 : ((tier <= 3) ? 90 : ((tier == 5) ? 240 : 720));
        if (wAge > lim) {
            return false;
        }
        return !(far && tier <= 3 && !shadow);
    }

    // =============================================================================================== data access

    private function hours() {
        return (w == null) ? 0 : w[4];
    }

    private function t0() {
        return w[3];
    }

    private function stamp(i) {
        return w[3] + i * 3600;
    }

    // value i of hourly series f, or null. The 14 series travel packed into 4 arrays of whole numbers
    // (WeatherService.mc): field f sits in w[5 + P_SLOT[f]] at bit P_SHIFT[f], P_BITS[f] wide, all ones = null,
    // stored as value / P_UNIT + P_OFF.
    private function hv(f, i) {
        if (w == null || i < 0 || i >= w[4]) {
            return null;
        }
        var a = w[5 + P_SLOT[f]];
        if (a == null || i >= a.size()) {
            return null;
        }
        var v = a[i];
        if (v == null) {
            return null;
        }
        var m = (1 << P_BITS[f]) - 1;
        var x = (v >> P_SHIFT[f]) & m;
        return (x == m) ? null : (x - P_OFF[f]) * P_UNIT[f];
    }

    // the first hour from i on where series f is under lim, or -1
    private function under(f, i, lim) {
        while (i < hours()) {
            if (hz(f, i) < lim) {
                return i;
            }
            i += 1;
        }
        return -1;
    }

    private function ab(x) {
        return (x < 0) ? -x : x;
    }

    private function hz(f, i) {
        var v = hv(f, i);
        return (v == null) ? 0 : v;
    }

    // the stamp nearest to now (instant values)
    private function iNow() {
        var i = ((now - w[3] + 1800) / 3600);
        return (i < 0) ? 0 : ((i >= w[4]) ? w[4] - 1 : i);
    }

    // the stamp whose preceding hour contains t (precipitation, gusts)
    private function iBlock(t) {
        var d = t - w[3];
        var i = (d <= 0) ? 0 : (d + 3599) / 3600;
        return i;
    }

    private function daily(k) {
        if (w == null || w[11] == null) {
            return null;
        }
        if (dShift) {
            // after midnight an older forecast's tomorrow is today; what it had for its own day is gone
            if (k < 2) {
                k += 4;
            } else if (k < 7 || k == 12 || k == 13) {
                return null;
            }
        }
        if (k >= w[11].size()) {
            return null;                                 // a forecast stored by an older version
        }
        var v = w[11][k];
        return (v == null || (v instanceof Lang.Number && v <= NUL)) ? null : v;
    }

    private function tC(i) {
        var v = hv(T, i);
        return (v == null) ? null : v / 10.0;
    }

    // =============================================================================================== text

    private function num(v) {
        return ((v < 0) ? (v - 0.5) : (v + 0.5)).toNumber().format("%d");
    }

    private function deg(c) {
        return (c == null) ? "--" : num(tempF ? c * 1.8 + 32 : c) + "\u00b0";
    }

    // a daily x10 C value: "4°", "--" when missing
    private function dg(v) {
        return (v == null) ? "--" : deg(v / 10.0);
    }

    // pre + the daily x10 C value + post, or "" when missing
    private function lab(pre, v, post) {
        return (v == null) ? "" : pre + deg(v / 10.0) + post;
    }

    // pre + a local clock time, or "" when unknown (-1)
    private function ev(pre, m) {
        return (m >= 0) ? pre + clk(m) : "";
    }

    private function degD(d) {
        return num(tempF ? d * 1.8 : d) + "\u00b0";
    }

    private function spdN(kmh) {
        return num(distMi ? kmh / 1.609 : kmh);
    }

    private function spd(kmh) {
        return spdN(kmh) + (distMi ? " MPH" : " KMH");
    }

    private function mm(x10) {
        if (tempF) {
            return (x10 / 254.0).format((x10 < 25) ? "%.2f" : "%.1f") + " IN";
        }
        return num(x10 / 10.0) + " MM";
    }

    private function cm(x10) {
        if (tempF) {
            return (x10 / 25.4).format("%.1f") + " IN";
        }
        return (x10 < 100) ? (x10 / 10.0).format("%.1f") + " CM" : num(x10 / 10.0) + " CM";
    }

    private function elev(m) {
        return num(elevFt ? m * 3.281 : m) + (elevFt ? " FT" : " M");
    }

    private function vis(m) {
        return (distMi ? (m / 1609.0).format("%.1f") + " MI" : (m / 1000.0).format("%.1f") + " KM");
    }

    // local clock text of minutes since midnight
    function clk(m) {
        var h = (m / 60) % 24;
        if (!t24) {
            h = h % 12;
            if (h == 0) {
                h = 12;
            }
        }
        return h.format(t24 ? "%02d" : "%d") + ":" + (m % 60).format("%02d");
    }

    private function localOf(t) {
        var g = Gregorian.info(new Time.Moment(t), Time.FORMAT_SHORT);
        return g.hour * 60 + g.min;
    }

    // A forecast time at its real precision: the nearest quarter with native data, else the nearest hour.
    // A coming event that rounds to a time already past says SOON, never a past time.
    private function at(t) {
        var step = q15 ? 900 : 3600;
        var r = (t + step / 2) / step * step;
        if (t > now && r <= now) {
            return "SOON";
        }
        return "~" + clk(localOf(r));
    }

    private function dayKey(t) {
        var g = Gregorian.info(new Time.Moment(t), Time.FORMAT_SHORT);
        return g.year * 400 + g.month * 32 + g.day;
    }

    // what the timing is based on, in plain words
    private function src() {
        return q15 ? "15-MIN FORECAST" : "HOURLY FORECAST";
    }

    // =============================================================================================== light

    private function light() {
        if (riseM < 0 || setM < 0 || polar != 0) {
            return;
        }
        var left = setM - localMin;
        if (left > 0 && left <= 120) {
            var tier = (left <= 30) ? 2 : 4;
            hasLight2 = tier == 2;
            add(tier, F_LIGHT, 120 - left, left, Ic.I_SUNHZ, "LIGHT", (left / 60).format("%d") + ":" + (left % 60).format("%02d") + " LEFT",
                "SUNSET " + clk(setM), ev("CIVIL DUSK ", duskM), "HILLS MAY HIDE IT", 160 + tier);
        }
    }

    // =============================================================================================== hazards

    private function gusts() {
        if (!ok(5)) {
            return;
        }
        var b = iBlock(now + 1);
        var gNow = hz(GU, b);
        var g1 = gNow;
        if (hz(GU, b + 1) > g1) {
            g1 = hz(GU, b + 1);
        }
        var lvl = 0;
        if (g1 >= 65 || (gustLvl == 1 && g1 >= 58)) {
            lvl = 1;
        } else if (g1 >= 50 || (gustLvl != 0 && g1 >= 45)) {
            lvl = 5;
        }
        if (lvl == 1 && !ok(1)) {
            lvl = 5;
        }
        if (!shadow) {
            newGust = lvl;
        }
        if (lvl != 0) {
            var out = (lvl == 1) ? 58 : 45;
            var u = under(GU, b + 2, out);
            var l2 = (u < 0) ? "NO EASING IN 12H" : "EASING " + at(stamp(u) - 3600);
            var pk0 = b;
            for (var k0 = b; k0 < b + 6 && k0 < hours(); k0 += 1) {
                if (hz(GU, k0) > hz(GU, pk0)) {
                    pk0 = k0;
                }
            }
            add(lvl, F_GUST, g1, 0, Ic.N_GUST, "GUST", spd(g1), "STEADY WIND " + spdN(hz(WS, iNow())), l2,
                (hz(GU, pk0) > g1) ? "PEAK " + spdN(hz(GU, pk0)) + " " + at(stamp(pk0) - 3600) : "", 80 + lvl);
            return;
        }
        if (gNow >= 50 || shadow) {
            return;
        }
        // a steady wind under gust level, by day (cyclists, paddlers): 30 km/h or more for the next 3 hours
        var ws = 999;
        for (var k2 = b; k2 < b + 3 && k2 < hours(); k2 += 1) {
            if (hz(WS, k2) < ws) {
                ws = hz(WS, k2);
            }
        }
        if (ws >= 30 && ws < 999 && localMin >= riseM && localMin < setM) {
            var u2 = under(WS, b + 3, 25);
            add(5, F_GUST, ws - 20, 0, Ic.N_GUST, "WIND", spd(ws), "FROM THE " + compass(hz(WD, b)),
                (u2 < 0) ? "NO EASING IN 12H" : "EASING " + at(stamp(u2)),
                "GUSTS " + spdN(gNow), 84);
        }
        var pk = -1;
        for (var k1 = b + 1; k1 <= b + 3 && k1 < hours(); k1 += 1) {
            if (pk < 0 || hz(GU, k1) > hz(GU, pk)) {
                pk = k1;
            }
        }
        if (pk >= 0 && hz(GU, pk) - gNow >= 20 && hz(GU, pk) >= 40) {
            add(5, F_GUST, hz(GU, pk) - 10, (stamp(pk) - 3600 - now) / 60, Ic.N_GUST, "WIND", "RISING",
                "GUSTS " + spdN(gNow) + " TO " + spdN(hz(GU, pk)), "STRONGER " + at(stamp(pk) - 3600),
                "FROM THE " + compass(hz(WD, pk)), WINDUP);
        }
    }

    private function isStorm(c) {
        return c == 95 || c == 96 || c == 97 || c == 99;
    }

    // Weather codes are instants: with hourly data a change seen at the next stamp began in the hour before it.
    private function codeOnset(i) {
        var m = (stamp(i) - now) / 60 - (q15 ? 0 : 30);
        return (m < 0) ? 0 : m;
    }

    private function storm() {
        if (!ok(5)) {
            return;
        }
        var i0 = iNow();
        var idx = -1;
        var ons = 0;
        if (isStorm(hz(CODE, i0)) && ab(now - stamp(i0)) <= 1800) {
            idx = i0;
        } else {
            for (var i = i0; i < hours() && stamp(i) <= now + 6 * 3600; i += 1) {
                if (stamp(i) > now && isStorm(hz(CODE, i))) {
                    idx = i;
                    ons = codeOnset(i);
                    break;
                }
            }
        }
        if (idx < 0) {
            return;                                      // CAPE alone is not a storm forecast: no message
        }
        var wet = hz(PR, idx);
        if (hz(PR, idx + 1) > wet) {
            wet = hz(PR, idx + 1);
        }
        // act now within the hour; within 2 h a storm ranks with rain timing (and, as the first family, beats the
        // rain it brings: a storm code also counts as wet); up to 6 h worth adapting to
        var tier = (ons <= 60 && wet >= 5 && ok(1)) ? 1 : ((ons <= 120 && ok(3)) ? 3 : 5);
        var l1 = "FCST THUNDERSTORM";
        if (baroStill && baroDrop != null && baroDrop >= 2) {
            l1 = "BARO \u00a6" + baroDrop.format("%.1f") + " IN 3H";
        }
        var l2 = "FOR HOURS";
        for (var k1 = idx + 1; k1 < hours(); k1 += 1) {
            if (!isStorm(hz(CODE, k1))) {
                l2 = "UNTIL " + at(stamp(k1));
                break;
            }
        }
        var detail = (ons <= 10) ? "NOW" : ((ons <= 60) ? "~1 H" : at(now + ons * 60));
        var pb = hv(PROB, idx);
        add(tier, F_STORM, 8 + ((hz(CODE, idx) == 96 || hz(CODE, idx) == 99) ? 1 : 0), ons, Ic.S_STORM, "STORM", detail,
            l1, l2, (wet <= 0) ? "" : mm(wet) + "/H" + ((pb == null) ? "" : "  " + pb + "%"), tier);
    }

    private function fog() {
        if (!ok(5)) {
            return;
        }
        var i = iNow();
        var code = hz(CODE, i);
        if (code != 45 && code != 48) {
            return;                                      // model visibility alone never raises fog
        }
        var v = hv(VI, i);
        var vm = (v == null) ? null : v * 10;
        var tc = tC(i);
        var freezing = code == 48 || (tc != null && tc <= 0);
        var dense = vm != null && vm < 400;
        var tier = (dense && ok(1)) ? 1 : 5;
        var l2 = "NO CLEARING IN 12H";
        for (var j = i + 1; j < hours(); j += 1) {
            var c2 = hz(CODE, j);
            if (c2 != 45 && c2 != 48 && hz(VI, j) >= 100) {
                l2 = "LIFTS " + at(stamp(j));
                break;
            }
        }
        var detail = (freezing && !dense) ? "FREEZING" : ((vm == null) ? "FCST" : vis(vm));
        var clear = "";
        for (var j2 = i + 1; j2 < hours(); j2 += 1) {
            if (hz(VI, j2) >= 500) {
                clear = "VIS " + vis(hz(VI, j2) * 10) + " " + at(stamp(j2));
                break;
            }
        }
        add(tier, F_FOG, (vm == null) ? 0 : 1000 - vm, 0, Ic.N_EYE, "FOG", detail,
            freezing ? "FREEZING FOG " + deg(tc) : "HUMIDITY " + hz(RH, i) + "%", l2, clear, 30 + tier);
    }

    private function isIce(c) {
        return c == 56 || c == 57 || c == 66 || c == 67;
    }

    private function ice() {
        if (!ok(5)) {
            return;
        }
        var i0 = iNow();
        var idx = -1;
        var ons = 0;
        if (isIce(hz(CODE, i0)) && ab(now - stamp(i0)) <= 1800) {
            idx = i0;
        } else {
            for (var i = i0; i < hours() && stamp(i) <= now + 6 * 3600; i += 1) {
                if (stamp(i) > now && isIce(hz(CODE, i))) {
                    idx = i;
                    ons = codeOnset(i);
                    break;
                }
            }
        }
        if (idx < 0) {
            return;
        }
        var tier = (ons <= 60 && ok(1)) ? 1 : 5;
        var l2 = "";
        var amt = 0;
        for (var k1 = idx; k1 < hours() && k1 < idx + 6; k1 += 1) {
            if (k1 > idx && !isIce(hz(CODE, k1))) {
                l2 = "UNTIL " + at(stamp(k1));
                break;
            }
            amt += hz(PR, k1 + 1);
        }
        var detail = (idx == i0 && ons == 0) ? "NOW" : ((ons <= 60) ? "~1 H" : at(now + ons * 60));
        add(tier, F_ICE, 9, ons, Ic.N_FREEZE, "ICE", detail, "FREEZING RAIN " + deg(tC(idx)), l2,
            (amt < 1) ? "" : "ABOUT " + mm(amt), 10 + tier);
    }

    // NWS heat index (Rothfusz, with the NWS adjustments), C. Below 26.7 C the air temperature itself.
    private function heatIndex(t, rh) {
        if (t < 26.7) {
            return t;
        }
        var f = t * 1.8 + 32;
        var hi = -42.379 + 2.04901523 * f + 10.14333127 * rh - 0.22475541 * f * rh - 0.00683783 * f * f
                 - 0.05481717 * rh * rh + 0.00122874 * f * f * rh + 0.00085282 * f * rh * rh
                 - 0.00000199 * f * f * rh * rh;
        if (rh < 13 && f >= 80 && f <= 112) {
            hi -= ((13 - rh) / 4.0) * Math.sqrt((17 - (f - 95).abs()) / 17.0);
        } else if (rh > 85 && f >= 80 && f <= 87) {
            hi += ((rh - 85) / 10.0) * ((87 - f) / 5.0);
        }
        return (hi - 32) / 1.8;
    }

    // Effective heat: the higher of air temperature and heat index (dry heat reads low on the heat index).
    private function effHeat(i) {
        var t = tC(i);
        if (t == null) {
            return null;
        }
        var hi = heatIndex(t, hz(RH, i));
        return (hi > t) ? hi : t;
    }

    private function heat() {
        if (!ok(5)) {
            return;
        }
        var i0 = iNow();
        var bi = -1;
        var e = -99.0;
        for (var i = i0; i <= i0 + 3 && i < hours(); i += 1) {
            var x = effHeat(i);
            if (x != null && x > e) {
                e = x;
                bi = i;
            }
        }
        if (bi < 0) {
            return;
        }
        var lvl = 0;
        if (e >= 40 || (heatLvl == 1 && e >= 38)) {
            lvl = 1;
        } else if (e >= 33 || (heatLvl != 0 && e >= 31)) {
            lvl = 5;
        }
        if (!shadow) {
            newHeat = lvl;
        }
        if (lvl == 0) {
            return;
        }
        var tier = (lvl == 1 && ok(1)) ? 1 : 5;
        if (tier == 5 && (localMin < 360 || localMin >= 1260)) {
            return;                                      // evenings and nights: the hot-night message instead
        }
        var t = tC(bi);
        var hi = heatIndex(t, hz(RH, bi));
        var out = (tier == 1) ? 38 : 31;
        var l2 = "NO EASING IN 12H";
        for (var k1 = bi + 1; k1 < hours(); k1 += 1) {
            var y = effHeat(k1);
            if (y != null && y < out) {
                l2 = "EASES " + at(stamp(k1));
                break;
            }
        }
        var feels = hi >= t + 1;
        var rh = hz(RH, bi);
        var tn = daily(5);
        add(tier, F_HEAT, e, 0, Ic.N_THERMO, "HEAT", feels ? "FEELS " + deg(hi) : "AIR " + deg(t),
            (feels ? "AIR " + deg(t) + "  " : ((rh < 20) ? "VERY DRY  " : "")) + "HUMIDITY " + rh + "%", l2,
            lab("NIGHT LOW ", tn, ""), 50 + tier);
    }

    // North American / UK wind chill, defined for T <= 10 C and wind >= 4.8 km/h; else null.
    private function windChill(i) {
        var t = tC(i);
        var v = hz(WS, i);
        if (t == null || t > 10 || v < 4.8) {
            return null;
        }
        var p = Math.pow(v, 0.16);
        return 13.12 + 0.6215 * t - 11.37 * p + 0.3965 * t * p;
    }

    private function cold() {
        if (!ok(5)) {
            return;
        }
        var i0 = iNow();
        var bi = -1;
        var wc = 99.0;
        for (var i = i0; i <= i0 + 1 && i < hours(); i += 1) {
            var x = windChill(i);
            if (x != null && x < wc) {
                wc = x;
                bi = i;
            }
        }
        if (bi < 0 || wc > -28) {
            return;
        }
        var l2 = "";
        for (var k1 = bi + 1; k1 < hours(); k1 += 1) {
            var y = windChill(k1);
            if (y == null || y > -28) {
                l2 = "MILDER " + at(stamp(k1));
                break;
            }
        }
        var tier = ok(1) ? 1 : 5;
        var dx = daily(0);
        add(tier, F_COLD, -wc, 0, Ic.N_THERMO, "COLD", "FEELS " + deg(wc), deg(tC(bi)) + " WIND " + spd(hz(WS, bi)), l2,
            (dg(dx).equals(deg(tC(bi))) ? "NO WARMER TODAY" : lab("HIGH ", dx, " TODAY")), 40 + tier);
    }

    private function snow() {
        if (!ok(5)) {
            return;
        }
        var b = iBlock(now + 1);
        // falling snow with wind
        var bi = -1;
        for (var i = b; i <= b + 1 && i < hours(); i += 1) {
            if (hz(SN, i) > 0 && (bi < 0 || hz(GU, i) > hz(GU, bi))) {
                bi = i;
            }
        }
        if (bi >= 0 && hz(GU, bi) >= 45) {
            var g = hz(GU, bi);
            var v = hv(VI, bi);
            var strong = hz(SN, bi) >= 10 && g >= 56 && ((v != null && v < 100) || hz(CODE, bi) == 75 || hz(CODE, bi) == 86);
            var tier = (strong && ok(1)) ? 1 : 5;
            var l2 = "";
            for (var k1 = bi + 1; k1 < hours(); k1 += 1) {
                if (hz(SN, k1) < 2 || hz(GU, k1) < 45) {
                    l2 = "EASES " + at(stamp(k1) - 3600);
                    break;
                }
            }
            add(tier, F_SNOW, g, 0, Ic.N_SNOW, "SNOW", strong ? "GUST " + spdN(g) : "WINDY",
                strong ? "BLOWING SNOW " + cm(hz(SN, bi)) + "/H" : cm(hz(SN, bi)) + "/H  GUSTS " + spdN(g), l2,
                (v == null) ? "" : "VIS " + vis(v * 10), 20 + tier);
        }
        if (shadow) {
            return;
        }
        // new snow over the next 6 hours
        var tot = 0;
        var rate = 0;
        for (var k2 = b; k2 < b + 6 && k2 < hours(); k2 += 1) {
            tot += hz(SN, k2);
            if (hz(SN, k2) > rate) {
                rate = hz(SN, k2);
            }
        }
        if (tot >= 50) {
            var k4 = under(SN, b + 1, 2);
            add(5, F_SNOW, tot / 10.0, 0, Ic.W_SNOW, "SNOW", "+" + cm(tot), "IN THE NEXT 6H",
                (k4 < 0) ? "" : "EASES " + at(stamp(k4) - 3600),
                "UP TO " + cm(rate) + "/H", 26);
        }
        // the snow line just above you (model snowfall height, where the model gives one)
        if (alt != null) {
            for (var k3 = b; k3 < b + 6 && k3 < hours(); k3 += 1) {
                if (hz(PR, k3) >= 3) {
                    var sh = hv(SH, k3);
                    if (sh != null) {
                        var margin = sh - alt;
                        if (margin > 0 && margin <= 600) {
                            var wet6 = 0;
                            for (var k6 = k3; k6 < k3 + 6 && k6 < hours(); k6 += 1) {
                                wet6 += hz(PR, k6);
                            }
                            // estimated from the freezing level (bit 30 of the third packed series): "~", and the
                            // raise shows the 0 C line itself
                            var p3 = w[7];
                            var est = p3 != null && k3 < p3.size() && ((p3[k3] >> 30) & 1) == 1;
                            add(5, F_SNOW, 600 - margin, (stamp(k3) - 3600 - now) / 60, Ic.N_SNOW, "SNOW",
                                (est ? "~" : "AT ") + elev(sh),
                                "RAIN " + ((stamp(k3) - 3600 <= now) ? "NOW" : at(stamp(k3) - 3600)) + "  " + mm(wet6),
                                "SNOW ABOVE IT",
                                est ? "0\u00b0 LINE " + elev(sh + 300) : "ALTITUDE " + elev(alt), SNOWLINE);
                            snowLine = (est ? "SNOWLINE ~" : "SNOW FROM ") + elev(sh);
                        }
                    }
                    break;
                }
            }
        }
    }

    // =============================================================================================== rain

    // One rain truth: wet spells at the resolution that is real here. Native 15-minute blocks for 2 hours where
    // the model has them, then hourly blocks. A block is wet from 0.1 mm (15 min) or 0.3 mm (hour); spells less
    // than 90 minutes apart are one spell. Sets sp0 and sp1 (meaningful spells) and spAny.
    private function timeline() {
        sp0 = null;
        sp1 = null;
        spAny = null;
        var cur = [ 0, 0, 0, 0, null ];
        var open = false;
        var spells = 0;
        var qEnd = now;
        var qa = w[10];                                  // not "q": that is a function of this class
        var n = 0;
        if (q15 && qa != null && w[9] != null) {
            n = qa.size();
        }
        for (var k = 0; k < n + 13; k += 1) {
            var s;
            var e;
            var amt;
            var sn;
            var prob;
            var wet;
            if (k < n) {
                e = w[9] + k * 900;
                s = e - 900;
                amt = (qa[k] <= NUL) ? 0 : qa[k];
                var hb = iBlock(e);
                sn = hz(SN, hb) / 4;
                prob = hv(PROB, hb);
                wet = amt >= 1;
                qEnd = e;
            } else {
                var i = iBlock(qEnd + 1) + (k - n);
                if (i >= hours() || stamp(i) > now + 13 * 3600) {
                    break;
                }
                e = stamp(i);
                s = e - 3600;
                if (e <= qEnd) {
                    continue;
                }
                amt = hz(PR, i);
                sn = hz(SN, i);
                prob = hv(PROB, i);
                wet = amt >= 3;
            }
            if (!wet) {
                continue;
            }
            if (open && s - cur[1] >= 5400) {
                spells = keep(cur, spells);
                open = false;
                if (spells >= 2) {
                    break;
                }
            }
            if (!open) {
                cur = [ s, e, amt, sn, prob ];
                open = true;
            } else {
                cur[1] = e;
                cur[2] += amt;
                cur[3] += sn;
                if (prob != null && (cur[4] == null || prob > cur[4])) {
                    cur[4] = prob;
                }
            }
        }
        if (open && spells < 2) {
            keep(cur, spells);
        }
    }

    private function keep(sp, n) {
        if (spAny == null) {
            spAny = sp;
        }
        if (sp[0] > now + 60 && (sp[2] < 5 || (sp[4] != null && sp[4] < 30))) {
            return n;                                    // a coming spell under 0.5 mm, or not a confident one
        }
        if (n == 0) {
            sp0 = sp;
        } else {
            sp1 = sp;
        }
        return n + 1;
    }

    private function isSnow(sp) {
        return sp[3] > 0 && sp[3] * 10 >= sp[2] * 5;     // snow cm >= half the water mm (about 1:10)
    }

    private function rain() {
        if (w == null) {
            return;
        }
        timeline();
        if (!ok(3) || sp0 == null) {
            return;
        }
        var word = isSnow(sp0) ? "SNOW" : "RAIN";
        var icon = isSnow(sp0) ? Ic.W_SNOW : Ic.W_RAIN;
        var prob = (sp0[4] == null) ? "" : sp0[4].format("%d") + "%  ";
        if (sp0[0] <= now + 60) {
            var left = (sp0[1] - now) / 60;
            if (left <= 120) {
                var gap = (sp1 == null) ? 999 : (sp1[0] - sp0[1]) / 60;
                var detail = (q15 && left < 100) ? "~" + ((left + 7) / 15 * 15) + " MIN" : at(sp0[1]);
                add(3, F_RAIN, 3, left, Ic.W_PARTLY, "DRY", detail, mm(sp0[2]) + " STILL TO FALL",
                    (gap >= 720) ? "DRY 12H+" : "DRY ~" + (gap / 60) + "H AFTER", src(), 62);
            } else {
                wetLong = sp0;
            }
            return;
        }
        var m = (sp0[0] - now) / 60;
        if (m > 120) {
            return;
        }
        // when: minutes where the forecast has 15-minute steps; else the end of the hour it starts in ("BY 16:00"),
        // since an hourly forecast only knows that rain falls somewhere in that hour
        var det2 = (q15 && m < 100) ? "~" + (((m + 7) / 15 * 15 < 15) ? 15 : (m + 7) / 15 * 15) + " MIN"
                                    : (q15 ? at(sp0[0]) : "BY " + clk(localOf(sp0[0] + 3600)));
        var ends = sp0[1] - sp0[0] < 12 * 3600 && sp0[1] < now + 12 * 3600;
        var l1 = prob + "ABOUT " + mm(sp0[2]);           // a shower that ends: its whole amount
        var l2 = "THEN DRY " + at(sp0[1]);
        var lim = ends ? sp0[1] : now + 12 * 3600;
        var tot = 0;
        var pk = -1;
        for (var i = iBlock(sp0[0] + 1); i < hours() && stamp(i) <= lim; i += 1) {
            tot += hz(PR, i);
            if (pk < 0 || hz(PR, i) > hz(PR, pk)) {
                pk = i;
            }
        }
        if (!ends) {
            l1 = prob + mm(tot) + " IN 12H";             // no end in sight: the amount over a stated period
            l2 = "NO DRY BREAK";
        }
        // raise: the other end of the hour, so "BY 16:00" and "NOT BEFORE 15:00" give the window without a repeat
        var x = q15 ? src() : "NOT BEFORE " + clk(localOf(sp0[0]));
        if (pk >= 0 && stamp(pk) - 3600 >= sp0[0] + 7200) {
            x = "HEAVIEST " + at(stamp(pk) - 3600);
        }
        if (setM >= 0 && localMin < setM && setM - localMin <= 120 && (sp0[0] - now) / 60 < setM - localMin + 30) {
            if (ends) {
                x = l2;                                  // the sunset takes line 2; the dry time moves to the raise
            }
            l2 = "SUNSET " + clk(setM);
        }
        add(3, F_RAIN, 3 + sp0[2] / 100.0, m, icon, word, det2, l1, l2, x, RAIN3);
    }

    // Heavy rain (7.6 mm/h) and a large total (20 mm in 6 h), from the same hourly series.
    private function heavyAndTotal() {
        if (w == null || !ok(3)) {
            return;
        }
        var b = iBlock(now + 1);
        var tot = 0;
        var pk = b;
        var pmax = 0;
        for (var k1 = b; k1 < b + 6 && k1 < hours(); k1 += 1) {
            tot += hz(PR, k1);
            if (hz(PR, k1) > hz(PR, pk)) {
                pk = k1;
            }
            if (hz(PROB, k1) > pmax) {
                pmax = hz(PROB, k1);
            }
        }
        for (var i = b; i <= b + 2 && i < hours(); i += 1) {
            if (hz(PR, i) >= 76) {
                var hl2 = "FROM " + at(stamp(i) - 3600);
                if (stamp(i) - 3600 <= now) {                // already falling: say when it eases, not when it began
                    var k5 = under(PR, i + 1, 76);
                    hl2 = (k5 < 0) ? "FOR HOURS" : "UNTIL " + at(stamp(k5) - 3600);
                }
                add(3, F_RAIN, 5, (stamp(i) - 3600 - now) / 60, Ic.W_RAIN, "RAIN", "HEAVY", "~" + mm(hz(PR, i)) + "/H",
                    hl2, (tot > hz(PR, i)) ? mm(tot) + " IN 6H" : "", 63);
                break;
            }
        }
        if (tot >= 200 && ok(5)) {
            add(5, F_RAIN, tot / 10.0, 0, Ic.W_RAIN, "RAIN", "+" + mm(tot), "IN THE NEXT 6H",
                (stamp(pk) - 3600 <= now) ? "HEAVIEST NOW" : "HEAVIEST " + at(stamp(pk) - 3600),
                (pmax > 0) ? "CHANCE " + pmax + "%" : "", 64);
        }
    }

    // =============================================================================================== UV, air

    private function uvAir() {
        if (ok(5) && riseM >= 0 && localMin >= riseM && localMin < setM) {
            var i0 = iNow();
            var hit = false;
            for (var i = i0; i <= i0 + 2 && i < hours(); i += 1) {
                if (hz(UV, i) >= 80) {
                    hit = true;
                }
            }
            if (hit) {
                var k1 = under(UV, i0 + 1, 80);
                var l1 = (k1 < 0) ? "UV 8+" : "UV 8+ UNTIL " + at(stamp(k1));
                var mx = daily(2);
                var peak = (mx == null) ? hz(UV, i0) : mx;
                var uvNow = num(hz(UV, i0) / 10.0);
                add(5, F_UV, peak / 10.0, 0, Ic.N_UV, "UV", (peak >= 110) ? "EXTREME" : "VERY HIGH", l1,
                    "PEAK TODAY " + num(peak / 10.0), uvNow.equals(num(peak / 10.0)) ? "" : "UV " + uvNow + " NOW", 110);
            }
        }
        var a = aq;
        if (a == null || now - a[0] > 10800 || a[2] == null || a[2] <= NUL) {
            return;
        }
        var eu = a[1] == 0;
        var v = a[2];
        var scale = eu ? "EU AQI " : "US AQI ";
        var drv = DRIVERS[a[3]];
        var t1 = eu ? v > 100 : v >= 301;
        var t5 = eu ? v >= 60 : v >= 151;
        var dust = (a[4] == null || a[4] <= NUL) ? 0 : a[4];
        if (t1 || t5) {
            var word = t1 ? (eu ? "EXTREME" : "HAZARD") : (eu ? "POOR" : "UNHEALTHY");
            var lo = t1 ? (eu ? 101 : 301) : (eu ? 60 : 151);
            add(t1 ? 1 : 5, F_AIR, v, 0, Ic.N_AIR, "AIR", word, scale + v + "  " + drv, aqWhen(a, false, lo, "BETTER "),
                (a[7] == null || a[7] <= 0) ? "" : a[7].format("%d") + " UG/M3 NOW", 90 + (t1 ? 1 : 5));
        } else if (dust >= 100) {
            var vv = (w == null) ? null : hv(VI, iNow());
            add(5, F_DUST, dust, 0, Ic.N_AIR, "DUST", "HIGH", "DUST " + dust + " UG/M3", aqWhen(a, true, 100, "EASES "),
                (vv == null) ? "" : "VISIBILITY " + vis(vv * 10), 120);
        }
        if (pollenOn && a[5] != null && a[5] >= 3) {
            add(5, F_POLLEN, a[5], 0, Ic.N_POLLEN, "POLLEN", POLLENS[a[6]], (a[5] >= 4) ? "LEVEL VERY HIGH" : "LEVEL HIGH",
                "", (a[8] == null || a[8] <= 0) ? "" : a[8].format("%d") + " GRAINS/M3", 130);
        }
    }

    // When the index (or dust) first drops under lo in the 12-hour air forecast: "BETTER ~22:00"; "" without one.
    private function aqWhen(a, dust, lo, head) {
        var h0 = a[9];
        var hp = a[10];
        if (h0 == null || hp == null) {
            return "";
        }
        for (var j = 0; j < hp.size(); j += 1) {
            var t = h0 + j * 3600;
            var x = hp[j];
            if (t > now && x != null) {
                var y = dust ? x / 1024 : x % 1024;
                if ((dust || y != 1023) && y < lo) {
                    return head + at(t);
                }
            }
        }
        return dust ? "NO EASING IN 12H" : "NO CHANGE IN 12H";
    }

    // =============================================================================================== temperatures

    private function temps() {
        if (!ok(5)) {
            return;
        }
        var i0 = iNow();
        // a fast drop with a change of air (wind shift or rising gusts), not the evening cooling
        var found = false;
        for (var i = i0; i <= i0 + 6 && i < hours() && !found; i += 1) {
            for (var j = i + 1; j <= i + 3 && j < hours(); j += 1) {
                var a = tC(i);
                var b2 = tC(j);
                if (a != null && b2 != null && a - b2 >= 5) {
                    found = true;
                    var shift = ab((hz(WD, j) - hz(WD, i) + 540) % 360 - 180);
                    var rise = hz(GU, j) - hz(GU, i);
                    if (shift >= 45 || rise >= 15) {
                        var tn0 = tC(i0);
                        add(5, F_TEMP, a - b2, (stamp(i) - now) / 60, Ic.N_THERMO, "TEMP", at(stamp(j)),
                            "DOWN TO " + deg(b2) + ((shift >= 45) ? "  WIND " + compass(hz(WD, j)) : ""),
                            (rise >= 15) ? "GUSTS TO " + spd(hz(GU, j)) : degD(a - b2) + " DROP IN " + (j - i) + "H",
                            (tn0 == null || deg(tn0).equals(deg(b2))) ? "" : "NOW " + deg(tn0), 70);
                    }
                    break;
                }
            }
        }
        // the coming night: frost after a mild day, or a hot night
        var evening = (setM >= 0 && localMin >= setM - 120) || localMin < 360;
        if (!evening) {
            return;
        }
        var low = 99.0;
        var li = -1;
        for (var k1 = i0; k1 < hours() && stamp(k1) <= now + 15 * 3600; k1 += 1) {
            var hm = localOf(stamp(k1));
            if (stamp(k1) > now && (hm <= 540 || stamp(k1) <= now + (1440 - localMin) * 60)) {
                var t = tC(k1);
                if (t != null && t < low) {
                    low = t;
                    li = k1;
                }
            }
        }
        if (li < 0) {
            return;
        }
        var dmax = daily(0);
        if (low <= 0 && (dmax == null || dmax >= 50)) {
            var calm = hz(CL, li) < 30 && hz(WS, li) < 10;
            add(5, F_FROST, -low, 0, Ic.N_FREEZE, "FROST", (localMin >= 720) ? "TONIGHT" : "BY DAWN",
                "LOW " + deg(low) + " " + at(stamp(li)), calm ? "CLEAR  LIGHT WIND" : "", "GROUND COLDER", 100);
        }
        if (low >= 25) {
            add(5, F_HOT, low, 0, Ic.W_MOON, "HOT", "MIN " + deg(low), "TROPICAL NIGHT", "COOLEST " + at(stamp(li)),
                "HUMIDITY " + hz(RH, li) + "%", 140);
        } else if (low >= 20) {
            hotQuiet = [ 60, F_QUIET, 0.0, 0, Ic.W_MOON, "HOT", "MIN " + deg(low), "TROPICAL NIGHT",
                         "COOLEST " + at(stamp(li)), "HUMIDITY " + hz(RH, li) + "%", "", 214 ];
        }
    }

    private function compass(b) {
        var i = ((b + 22.5) / 45).toNumber() % 8;
        return COMPASS[i];
    }

    // Icy patches: wet ground (rain or snow in the last hours, or in the hours ahead) and then air at 0 C or below
    // with nothing falling. A risk, never a certainty: the forecast cannot see the road.
    private function icy() {
        if (!ok(5)) {
            return;
        }
        var i0 = iNow();
        var wt = wetT;
        for (var i = 0; i < hours() && i <= i0 + 6; i += 1) {
            var wet = hz(PR, i) >= 3;
            if (wet && stamp(i) > wt) {
                wt = stamp(i);
                if (wt <= now) {
                    wetT = wt;                           // remembered: a later forecast no longer has this hour
                }
            }
            var t = tC(i);
            if (i >= i0 && !wet && t != null && t <= 0 && wt > 0 && stamp(i) - wt <= 6 * 3600) {
                add(5, F_ICE, 1 - t, (stamp(i) <= now) ? 0 : (stamp(i) - now) / 60, Ic.N_FREEZE, "ICE",
                    (stamp(i) <= now + 1800) ? "RISK" : at(stamp(i)), "ICY PATCHES " + deg(t),
                    "WET UNTIL " + at(wt),
                    "SHADE AND BRIDGES", 17);
                return;
            }
        }
    }

    // =============================================================================================== barometer

    // Offline only, and only when the watch stayed at the same height: the watch's own pressure is then the
    // only weather evidence there is.
    private function baro() {
        if (ok(6) || !baroStill || baroDrop == null || baroNow == null || baroDrop < 4) {
            return;
        }
        add(5, F_BARO, baroDrop, 0, Ic.F_BARO, "BARO", "FALLING", num(baroNow) + " HPA \u00a6" + baroDrop.format("%.1f") + " IN 3H",
            "SAME HEIGHT", "WATCH SENSOR ONLY", 150);
    }

    // =============================================================================================== quiet

    private function q(icon, word, detail, l1, l2, e1, id) {
        return [ 60, F_QUIET, 0.0, 0, icon, word, detail, l1, l2, e1, "", id ];
    }

    // A hazard dropped only because the data aged: say so, never CALM.
    private function staleOrQuiet() {
        if (w != null && wAge > 90 && wAge <= 720) {
            shadow = true;
            best = null;
            gusts();
            storm();
            ice();
            heat();
            cold();
            snow();
            fog();
            shadow = false;
            var o = best;
            best = null;
            if (o != null) {
                var h = wAge / 60;
                return q(o[4], o[5], h.format("%d") + "H OLD", "FCST " + o[6], "LAST UPDATE " + clk(localOf(w[0])), errText,
                         300 + o[FAM]);
            }
        }
        return quiet();
    }

    private function quiet() {
        if (polar != 0) {
            return q(Ic.I_SUNHZ, "POLAR", (polar > 0) ? "DAY" : "NIGHT", (polar > 0) ? "NO SUNSET TODAY" : "NO SUNRISE TODAY",
                     "", "SUN CALCULATED", 201);
        }
        if (!ok(6)) {
            if (baroStill && baroDrop != null && baroNow != null) {
                var word = (baroDrop <= -1) ? "RISING" : ((baroDrop >= 1) ? "FALLING" : "STEADY");
                var arrow = (baroDrop > 0) ? "\u00a6" : "\u00a5";
                return q(Ic.F_BARO, "BARO", word, num(baroNow) + " HPA " + arrow + baroDrop.abs().format("%.1f") + " IN 3H",
                         ev("SUNSET ", setM), "WATCH SENSOR ONLY", 202);
            }
            if (riseM >= 0) {
                var day = localMin < setM && localMin >= riseM;
                var len = setM - riseM;
                return q(Ic.I_SUNHZ, "SUN", day ? "SETS " + clk(setM) : "RISES " + clk(riseM),
                         "DAYLIGHT " + (len / 60).format("%d") + "H " + (len % 60).format("%02d") + "M",
                         day ? ev("FIRST LIGHT ", dawnM) : ev("CIVIL DUSK ", duskM),
                         errText, 203);
            }
            return q(-1, "NO FIX", errText, "START A GPS ACTIVITY", "", "", 204);
        }
        var tmax = daily(0);
        var next = (sp0 != null) ? word0() + " " + at(sp0[0]) : "DRY 12H+";
        var sunset = ev("SUNSET ", setM);
        // dawn
        if (dawnM >= 0 && localMin >= dawnM - 75 && localMin < dawnM) {
            var m = (dawnM - localMin + 2) / 5 * 5;
            return q(Ic.I_SUNHZ, "DAWN", "~" + ((m < 5) ? 5 : m) + " MIN", "SUNRISE " + clk(riseM), next,
                     lab("HIGH ", tmax, " TODAY"), 205);
        }
        var uvx = daily(2);
        var uv = (uvx == null) ? "--" : num(uvx / 10.0);
        // the morning briefing, once a day
        if (todaySeen != dayKey(now) && riseM >= 0 && localMin >= riseM - 60 && localMin < 720) {
            return q(Ic.I_SUNHZ, "TODAY", "HI " + dg(tmax), next,
                     "UV " + uv + ((uvx != null && uvx >= 95) ? " " : "  ") + sunset, briefing(tmax), 206);
        }
        // evening: tomorrow; night
        var eve = setM >= 0 && localMin >= ((setM > 1020) ? setM : 1020) && localMin < 1380;
        if (eve || (duskM >= 0 && (localMin >= duskM || localMin < dawnM))) {
            return (hotQuiet != null) ? hotQuiet : (eve ? tomorrow() : night());
        }
        var hiUv = "HIGH " + dg(tmax) + "  UV " + uv;
        // day
        if (wetLong != null) {
            return q(Ic.W_RAIN, word0Of(wetLong), "+" + mm(wetLong[2]), "STILL " + ((word0Of(wetLong).equals("SNOW")) ? "SNOWING" : "RAINING"),
                     (wetLong[1] - now > 12 * 3600) ? "NO DRY BREAK" : "DRY " + at(wetLong[1]), src(), 207);
        }
        if (sp0 != null) {
            var gap = (sp0[0] - now) / 60;
            if (gap >= 90 && gap <= 240) {
                return q(Ic.W_PARTLY, "DRY", "~" + (gap / 60) + "H GAP", word0() + " BACK " + at(sp0[0]),
                         "THEN " + mm(sp0[2]) + ((sp0[4] == null) ? "" : "  " + sp0[4] + "%"), src(), 208);
            }
            return q(Ic.W_PARTLY, "DRY", "~" + (gap / 60) + "H", word0() + " " + at(sp0[0]),
                     sunset, src(), 209);
        }
        // sunshine still to come today (hourly), and the mean cloud cover until sunset
        var sun = 0;
        var cloud = 0;
        var n = 0;
        for (var i = iNow() + 1; i < hours() && localOf(stamp(i) - 3600) >= localMin - 60 && localOf(stamp(i) - 3600) < setM; i += 1) {
            sun += hz(SU, i);
            cloud += hz(CL, i);
            n += 1;
        }
        if (sun >= 300 && n > 0 && cloud / n < 40) {
            var wg = wetGround();
            return q(Ic.W_SUN, "SUNNY", "~" + (sun / 60) + "H SUN", hiUv, "DRY 12H+",
                     wg.equals("") ? "CLOUD " + (cloud / n) + "%" : wg, 210);
        }
        var wg2 = wetGround();
        return q(Ic.W_SUN, "CALM", "DRY 12H+", hiUv, sunset,
                 wg2.equals("") ? tonight(tmax) : wg2, 211);
    }

    // The morning briefing's extra line: today against yesterday's high when 3 C or more apart, else yesterday's
    // rain when the ground is still wet, else tonight's low.
    private function briefing(tmax) {
        // fresh snow first (skiers), then the cool hours of a hot day (runners), then the change from yesterday
        var fs = (yday != null && yday.size() > 3 && yday[3] != null && yday[3] > 0) ? yday[3] : 0;
        var st = daily(13);
        if (st != null) {
            var mid = now + (1440 - localMin) * 60;
            for (var i = iNow(); i < hours() && stamp(i) <= mid; i += 1) {
                if (stamp(i) > now) {
                    st -= hz(SN, i);                     // what is still to fall today is not on the ground yet
                }
            }
            fs += (st > 0) ? st : 0;
        }
        if (fs >= 50) {
            return "+" + cm(fs) + " NEW SNOW";
        }
        if (tmax != null && tmax >= 300) {
            var i0 = iNow();
            var t = tC(i0);
            for (var k = i0 + 1; t != null && k < hours() && k <= i0 + 16; k += 1) {
                var x = tC(k);
                if (x != null && (t < 25) != (x < 25)) {
                    return (t < 25) ? deg(25.0) + " BY " + at(stamp(k)) : "UNDER " + deg(25.0) + " " + at(stamp(k));
                }
            }
        }
        if (yday != null && tmax != null && yday[1] != null && yday[1] > NUL) {
            var d = (tmax - yday[1]) / 10.0;
            if (ab(d) >= 3) {
                var by = degD(ab(d));
                // the high is on screen already ("HI 4°"): a drop of the same number would read as a repeat
                return (by.equals(dg(tmax)) ? "" : by + " ") + ((d < 0) ? "COLDER TODAY" : "WARMER TODAY");
            }
        }
        var wg = wetGround();
        return wg.equals("") ? tonight(tmax) : wg;
    }

    // Yesterday's rain when 10 mm or more fell: trails and grass are still wet. "" otherwise.
    private function wetGround() {
        if (yday == null || yday[2] == null || yday[2] < 100) {
            return "";
        }
        return mm(yday[2]) + " YESTERDAY";
    }

    // tonight's low from the daily forecast (tomorrow's minimum, which falls before dawn)
    private function tonight(tmax) {
        var tn = daily(5);
        if (tn == null || dg(tn).equals(dg(tmax))) {
            return "";                                   // a low equal to the high on screen says nothing new
        }
        return lab("LOW ", tn, " TONIGHT");
    }

    private function word0() {
        return word0Of(sp0);
    }

    private function word0Of(sp) {
        return isSnow(sp) ? "SNOW" : "RAIN";
    }

    private function tomorrow() {
        var mid = now + (1440 - localMin) * 60;          // next local midnight (to the minute)
        var first = -1;
        var tot = 0;
        var pmax = 0;
        for (var i = 0; i < hours(); i += 1) {
            if (stamp(i) > mid && hz(PR, i) >= 3) {
                if (first < 0) {
                    first = i;
                }
                tot += hz(PR, i);
                if (hz(PROB, i) > pmax) {
                    pmax = hz(PROB, i);
                }
            }
        }
        var tx = daily(4);
        var tn = daily(5);
        var high = "HIGH " + dg(tx);
        if (first >= 0) {
            return q(Ic.N_RAIN, "TMRW", "RAIN " + pmax + "%", "FROM " + at(stamp(first) - 3600) + " " + mm(tot), high,
                     lab("LOW ", tn, ""), 212);
        }
        var pp = daily(6);
        // tomorrow against today when 5 C or more apart (the number left out when it equals a value on screen)
        var x = "";
        var td = daily(0);
        if (tx != null && td != null && ab(tx - td) >= 50) {
            var by = degD(ab(tx - td) / 10.0);
            x = (by.equals(dg(tx)) || by.equals(dg(tn)))
                ? ((tx < td) ? "MUCH COLDER" : "MUCH WARMER") : by + ((tx < td) ? " COLDER" : " WARMER");
        }
        return q(Ic.N_CLOUD, "TMRW", "DRY", high + "  LOW " + dg(tn),
                 "RAIN " + ((pp == null) ? "--" : pp.format("%d") + "%"), x, 213);
    }

    private function night() {
        var i0 = iNow();
        // the moon from Open-Meteo's rise and set times (today and tomorrow): below the horizon on a clear night
        var lr = -1;
        var ls = -1;
        var nr = -1;
        for (var k5 = 7; k5 <= 11; k5 += 1) {
            var ev = daily(k5);
            if (ev != null && k5 != 9) {
                var isRise = k5 == 7 || k5 == 10;
                if (ev <= now) {
                    if (isRise && ev > lr) {
                        lr = ev;
                    } else if (!isRise && ev > ls) {
                        ls = ev;
                    }
                } else if (isRise && (nr < 0 || ev < nr)) {
                    nr = ev;
                }
            }
        }
        var ph = daily(9);
        var up = lr >= 0 && lr > ls;
        if (!up && nr >= 0 && nr - now < 12 * 3600 && hz(CL, i0) < 30) {
            return q(Ic.N_MOON, "MOON", "BELOW", "RISES " + clk(localOf(nr)) + ((ph == null) ? "" : "  " + lit(ph) + "%"),
                     ev("FIRST LIGHT ", dawnM), "CLOUD " + hz(CL, i0) + "%", 215);
        }
        var low = 99.0;
        var li = i0;
        for (var i = i0; i < hours() && i <= i0 + 12; i += 1) {
            var t = tC(i);
            if (t != null && t < low) {
                low = t;
                li = i;
            }
        }
        return q(Ic.W_MOON, "NIGHT", "LOW " + deg(low), "COOLEST " + ((stamp(li) <= now) ? "NOW" : at(stamp(li))),
                 ev("FIRST LIGHT ", dawnM), "CLOUD " + hz(CL, i0) + "%", 216);
    }

    // share of the moon lit from Open-Meteo's phase (0 new, 50 full, 100 new again), percent
    private function lit(ph) {
        return num((1.0 - Math.cos(2.0 * Math.PI * ph / 100.0)) * 50.0);
    }
}
