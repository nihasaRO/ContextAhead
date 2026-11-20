import Toybox.Application;
import Toybox.Background;
import Toybox.Communications;
import Toybox.Lang;
import Toybox.PersistedContent;
import Toybox.System;
import Toybox.Time;

// Background process: fetches the forecast from Open-Meteo (free, no key; data CC BY 4.0, open-meteo.com) for the
// remembered location, and air quality (CAMS via Open-Meteo) at most once an hour. Hands the face one array:
//  0 fetch time  1 lat  2 lon  3 first hourly stamp  4 number of hours
//  5..8 the 14 hourly series packed four ways into whole numbers (Context.hv unpacks them), with these scales:
//        temp x10 C, humidity %, WMO code, probability %, precipitation x10 mm (preceding hour), snowfall x10 cm,
//        wind km/h, direction deg (2 deg steps), gusts km/h (max of the preceding hour), visibility /10 m (up to
//        20 km), UV x10, cloud %, snowfall height m (10 m steps), sunshine minutes (preceding hour).
//        One array per number instead of fourteen: about a third of the memory on the watch and in storage.
//  9 first 15-minute stamp  10 15-minute precipitation x10 mm (8 steps; asked for only where it is native:
//     Central Europe and the conterminous US)
//  11 daily [tmax x10, tmin x10, UV max x10, sunshine min, tomorrow tmax x10, tmin x10, rain chance %,
//            moonrise, moonset, moon phase x100, moonrise tomorrow, moonset tomorrow, today's rain x10 mm,
//            today's snowfall x10 cm]
//  Bit 30 of the third packed series (slot 2) marks an hour whose snow line is estimated from the freezing level.
//  12 air [time, scale 0 EU / 1 US, index, driver 0 PM2.5 1 PM10 2 NO2 3 OZONE 4 SO2, dust ug/m3,
//          pollen level 0-4 or null, pollen type 0-5, the driver's concentration ug/m3, pollen grains/m3,
//          first hourly stamp, 12 hours of index + dust x 1024 (index 1023 = none)] or null when not fetched this
//          time (the app stores it apart). The scale follows the setting: Auto (European in Europe), European, US.
// An error is sent as its number alone.
(:background)
class WeatherService extends System.ServiceDelegate {
    private var mLat;
    private var mLon;
    private var mResult;
    private var mEurope = true;
    private var mPollenArea = true;

    private const H_NAMES = [ "temperature_2m", "relative_humidity_2m", "weather_code", "precipitation_probability",
                              "precipitation", "snowfall", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
                              "visibility", "uv_index", "cloud_cover", "snowfall_height", "sunshine_duration" ];
    private const H_SCALE = [ 10.0, 1.0, 1.0, 1.0, 10.0, 10.0, 1.0, 1.0, 1.0, 0.1, 10.0, 1.0, 1.0, 0.016666667 ];
    // where each series sits in the packed arrays: slot, bit shift, width (all ones = null), offset, unit
    private const P_SLOT = [0, 0, 0, 1, 2, 2, 1, 3, 1, 3, 2, 1, 3, 0]b;
    private const P_SHIFT = [0, 11, 18, 0, 0, 12, 7, 0, 15, 8, 22, 24, 19, 25]b;
    private const P_BITS = [11, 7, 7, 7, 12, 10, 8, 8, 9, 11, 8, 7, 12, 6]b;
    private const P_OFF = [1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 100, 0];
    private const P_UNIT = [1, 1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 10, 1]b;
    private const SUBS = [ "_pm2_5", "_pm10", "_nitrogen_dioxide", "_ozone", "_sulphur_dioxide" ];
    private const CONC = [ "pm2_5", "pm10", "nitrogen_dioxide", "ozone", "sulphur_dioxide" ];
    private const POLLEN = [ "alder_pollen", "birch_pollen", "grass_pollen", "mugwort_pollen", "olive_pollen",
                             "ragweed_pollen" ];

    function initialize() {
        ServiceDelegate.initialize();
    }

    function onTemporalEvent() as Void {
        var loc = Application.Storage.getValue("loc");
        if (!(loc instanceof Lang.Array) || loc.size() < 2) {
            Background.exit(-1);                         // no position yet: the face shows NO GPS
            return;
        }
        mLat = ((loc[0] as Lang.Float) * 100.0).toNumber() / 100.0;   // about 1 km: all the forecast needs
        mLon = ((loc[1] as Lang.Float) * 100.0).toNumber() / 100.0;
        // 20 hours (every message looks 12 to 15 hours ahead; tomorrow's rain from the evening still fits); after an
        // out-of-memory reply (-403) the face asks for 16
        var hours = (Application.Storage.getValue("wxSmall") == true) ? 16 : 20;
        // Central Europe (ICON-D2 / AROME): native 15-minute rain and the model's own snowfall height
        var inner = (mLat >= 25.0 && mLat <= 49.0 && mLon >= -125.0 && mLon <= -67.0) ? 1
                    : ((mLat >= 43.5 && mLat <= 55.5 && mLon >= -4.0 && mLon <= 19.5) ? 2 : 0);
        var p = { "latitude" => mLat, "longitude" => mLon, "timeformat" => "unixtime", "timezone" => "auto",
                  "forecast_hours" => hours, "forecast_days" => 2,
                  "hourly" => join(H_NAMES, 0, H_NAMES.size()) + ((inner == 2) ? "" : ",freezing_level_height"),
                  "daily" => "temperature_2m_max,temperature_2m_min,uv_index_max,sunshine_duration,"
                             + "precipitation_probability_max,moonrise,moonset,moon_phase,precipitation_sum,snowfall_sum" };
        // 15-minute rain only where the models really run in 15-minute steps (1 HRRR in the conterminous US,
        // 2 Central Europe); elsewhere it would be hourly data cut in four. The freezing level (for the estimated snow
        // line) is left out in Central Europe, where the model gives the snowfall height itself. Same boxes as the face.
        if (inner > 0) {
            p.put("forecast_minutely_15", 8);
            p.put("minutely_15", "precipitation");
        }
        Communications.makeWebRequest(
            "https://api.open-meteo.com/v1/forecast", p,
            { :method => Communications.HTTP_REQUEST_METHOD_GET,
              :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON },
            method(:onWeather));
    }

    function onWeather(code as Lang.Number, data as Lang.Dictionary or Lang.String or PersistedContent.Iterator or Null) as Void {
        if (code != 200 || !(data instanceof Lang.Dictionary)) {
            Background.exit(code);
            return;
        }
        var d = data as Lang.Dictionary;
        var r = new [13];
        r[0] = Time.now().value();
        r[1] = mLat;
        r[2] = mLon;
        r[4] = 0;
        var h = d["hourly"];
        if (h instanceof Lang.Dictionary) {
            var t = h["time"];
            if (t instanceof Lang.Array && t.size() > 0) {
                r[3] = t[0];
                r[4] = t.size();
            }
            h.remove("time");
            var n = r[4];
            for (var s = 0; s < 4; s += 1) {
                var z = new [n];
                for (var i = 0; i < n; i += 1) {
                    z[i] = 0;
                }
                r[5 + s] = z;
            }
            // where the model gives no snowfall height (outside Europe), the snow line is estimated from the
            // freezing level: snow usually reaches about 300 m below the 0 C level. Bit 30 of the third packed
            // series marks such an hour, so the face can say "~" and show the 0 C line itself.
            var fl = h["freezing_level_height"];
            h.remove("freezing_level_height");
            var fn = (fl instanceof Lang.Array) ? (fl as Lang.Array).size() : 0;
            for (var k = 0; k < H_NAMES.size(); k += 1) {
                var a = h[H_NAMES[k]];
                var an = (a instanceof Lang.Array) ? (a as Lang.Array).size() : 0;
                var out = r[5 + P_SLOT[k]] as Lang.Array;
                for (var j = 0; j < n; j += 1) {
                    var v = (j < an) ? sc((a as Lang.Array)[j], H_SCALE[k]) : -9999;
                    if (k == 12 && v <= -9999 && j < fn && (fl as Lang.Array)[j] != null) {
                        v = sc((fl as Lang.Array)[j], 1.0) - 300;
                        var est = r[7] as Lang.Array;
                        est[j] = est[j] | (1 << 30);
                    }
                    out[j] = out[j] | (store(v, k) << P_SHIFT[k]);
                }
                a = null;
                h.remove(H_NAMES[k]);                    // free each list as soon as it is packed
            }
        }
        h = null;
        var m = d["minutely_15"];
        if (m instanceof Lang.Dictionary) {
            var mt = m["time"];
            r[9] = (mt instanceof Lang.Array && mt.size() > 0) ? mt[0] : null;
            r[10] = pack(m["precipitation"], 10.0);
        }
        m = null;
        var dl = d["daily"];
        if (dl instanceof Lang.Dictionary) {
            r[11] = [ sc(at(dl["temperature_2m_max"], 0), 10.0), sc(at(dl["temperature_2m_min"], 0), 10.0),
                      sc(at(dl["uv_index_max"], 0), 10.0), sc(at(dl["sunshine_duration"], 0), 1.0 / 60.0),
                      sc(at(dl["temperature_2m_max"], 1), 10.0), sc(at(dl["temperature_2m_min"], 1), 10.0),
                      sc(at(dl["precipitation_probability_max"], 1), 1.0),
                      at(dl["moonrise"], 0), at(dl["moonset"], 0), sc(at(dl["moon_phase"], 0), 100.0),
                      at(dl["moonrise"], 1), at(dl["moonset"], 1),
                      sc(at(dl["precipitation_sum"], 0), 10.0),        // 12: today's rain x10 mm (kept as "yesterday")
                      sc(at(dl["snowfall_sum"], 0), 10.0) ];               // 13: today's snow x10 cm
        }
        dl = null;
        d = null;
        mResult = r;
        // air quality at most once an hour (the face keeps the last one for 3 hours)
        var aqT = Application.Storage.getValue("aqT");
        if (aqT instanceof Lang.Number && r[0] - aqT < 3300) {
            Background.exit(mResult);
            return;
        }
        // the index scale: the setting (Auto, European, US); Auto is European inside Europe. Pollen exists only there.
        mPollenArea = mLat >= 34.0 && mLat <= 72.0 && mLon >= -25.0 && mLon <= 45.0;
        var k6 = Application.Properties.getValue("k6");
        mEurope = (k6 == 1) || (k6 != 2 && mPollenArea);
        var pre = mEurope ? "european_aqi" : "us_aqi";
        var cur = pre + ",dust," + join(CONC, 0, 5);
        for (var q = 0; q < 5; q += 1) {
            cur = cur + "," + pre + SUBS[q];
        }
        if (mPollenArea && Application.Properties.getValue("k4") == 1) {
            cur = cur + "," + join(POLLEN, 0, POLLEN.size());
        }
        Communications.makeWebRequest(
            "https://air-quality-api.open-meteo.com/v1/air-quality",
            { "latitude" => mLat, "longitude" => mLon, "current" => cur, "hourly" => pre + ",dust",
              "forecast_hours" => 12, "timeformat" => "unixtime" },
            { :method => Communications.HTTP_REQUEST_METHOD_GET,
              :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON },
            method(:onAir));
    }

    function onAir(code as Lang.Number, data as Lang.Dictionary or Lang.String or PersistedContent.Iterator or Null) as Void {
        var r = mResult as Lang.Array;
        if (code == 200 && data instanceof Lang.Dictionary) {
            var dd = data as Lang.Dictionary;
            var c = dd["current"];
            if (c instanceof Lang.Dictionary) {
                var pre = mEurope ? "european_aqi" : "us_aqi";
                var best = 0;
                var bestV = -1.0;
                for (var i = 0; i < 5; i += 1) {
                    var v = c[pre + SUBS[i]];
                    if (v != null && v > bestV) {
                        bestV = v;
                        best = i;
                    }
                }
                var lvl = -1;
                var type = 0;
                var grains = 0;
                if (mPollenArea) {
                    // grains/m3, Solar Frontier's bands: trees (alder, birch, olive) high from 100, very high above
                    // 500; grasses and weeds high from 30 (mugwort 50), very high above 100
                    for (var p = 0; p < 6; p += 1) {
                        var g = c[POLLEN[p]];
                        if (g != null) {
                            var tree = p == 0 || p == 1 || p == 4;
                            var hi = tree ? 100 : ((p == 3) ? 50 : 30);
                            var vh = tree ? 500 : 100;
                            var l = (g < 1) ? 0 : ((g < 10) ? 1 : ((g < hi) ? 2 : ((g <= vh) ? 3 : 4)));
                            if (l > lvl) {
                                lvl = l;
                                type = p;
                                grains = sc(g, 1.0);
                            }
                        }
                    }
                }
                // the next 12 hours: index + dust x 1024 in one number each (index 1023 = none)
                var h0 = null;
                var hp = null;
                var h = dd["hourly"];
                if (h instanceof Lang.Dictionary) {
                    var ht = h["time"];
                    var hi2 = h[pre];
                    var hd = h["dust"];
                    if (ht instanceof Lang.Array && hi2 instanceof Lang.Array && ht.size() > 0) {
                        var n = ht.size();
                        h0 = ht[0];
                        var arr = new [n];
                        for (var j = 0; j < n; j += 1) {
                            var x = (j < hi2.size()) ? sc(hi2[j], 1.0) : -9999;
                            var y = (hd instanceof Lang.Array && j < hd.size()) ? sc(hd[j], 1.0) : 0;
                            arr[j] = ((x < 0 || x > 1022) ? 1023 : x) + ((y < 0) ? 0 : y) * 1024;
                        }
                        hp = arr;
                    }
                }
                r[12] = [ Time.now().value(), mEurope ? 0 : 1, sc(c[pre], 1.0), best, sc(c["dust"], 1.0),
                          (lvl < 0) ? null : lvl, type, sc(c[CONC[best]], 1.0), grains, h0, hp ];
            }
        }
        Background.exit(r);
    }

    // "a,b,c" from part of an array of names.
    private function join(a, from, to) {
        var s = a[from];
        for (var i = from + 1; i < to; i += 1) {
            s = s + "," + a[i];
        }
        return s;
    }

    // A list of numbers scaled to whole numbers (null -> -9999), or null.
    private function pack(a, s) {
        if (!(a instanceof Lang.Array)) {
            return null;
        }
        var n = a.size();
        var out = new [n];
        for (var i = 0; i < n; i += 1) {
            out[i] = sc(a[i], s);
        }
        return out;
    }

    // A scaled value in its packed form: value / unit (rounded) + offset, kept below the null pattern.
    private function store(v, f) {
        var m = (1 << P_BITS[f]) - 1;
        if (v <= -9999) {
            return m;
        }
        var u = P_UNIT[f];
        var x = ((v >= 0) ? v + u / 2 : v - u / 2) / u + P_OFF[f];
        return (x < 0) ? 0 : ((x >= m) ? m - 1 : x);
    }

    // One value scaled and rounded to a whole number; null stays -9999.
    private function sc(v, s) {
        if (v == null) {
            return -9999;
        }
        var x = v * s;
        return (x >= 0) ? (x + 0.5).toNumber() : (x - 0.5).toNumber();
    }

    private function at(a, i) {
        return (a instanceof Lang.Array && a.size() > i) ? a[i] : null;
    }
}
