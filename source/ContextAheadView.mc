import Toybox.Activity;
import Toybox.ActivityMonitor;
import Toybox.Application;
import Toybox.Background;
import Toybox.Graphics;
import Toybox.Lang;
import Toybox.Math;
import Toybox.Position;
import Toybox.SensorHistory;
import Toybox.System;
import Toybox.Time;
import Toybox.Time.Gregorian;
import Toybox.WatchUi;
import Toybox.Weather;

// Context Ahead: watch face for the Instinct 3 Solar (176 x 176 px, 1-bit MIP).
// Five zones: the forecast's age (top left), the Signal (icon, word, detail), the circle (the wearer's own:
// date by default), the large time with a meter bar under it (the wearer's own), and two lines below that
// say how much and when it changes. On a wrist raise the two lines show the evidence. When something needs
// acting on now, the clock inverts. Context (Context.mc) decides the message, outside the redraw.
class ContextAheadView extends WatchUi.WatchFace {

    private const DAYS = "SUNMONTUEWEDTHUFRISAT";
    private const MDAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]b;
    private const SYNODIC = 29.530588853;
    private const NEW_MOON = 947182440;        // 2000-01-06 18:14 UTC

    private var fTime;
    private var fWord;
    private var fSmall;
    private var fBig;
    private var fTiny;
    private var fMid;
    private var fMed;
    private var fIcons;
    private var cfg;
    private var ctx;
    private var msg;                           // the last Context result (see Context.pick)
    private var pickT = -10000;                // when Context last ran (seconds)
    private var awake = false;
    private var started = false;               // onShow ran once: later calls come back from the settings menu
    private var gTemp = null;                  // Garmin's temperature, read outside the redraw
    private var t24 = true;                    // 24-hour time, read outside the redraw (no device settings in it)
    private var shownToday = false;            // TODAY was on screen during this wrist raise
    var behindMenu = false;                    // the settings menu is open: skip redraws (set by the app)
    var skipOnce = false;                      // just left the menu: skip one more redraw (set by the menu)

    private var subCx = 145;
    private var subCy = 31;
    private var arcX;
    private var arcY;

    private var lastMinute = -1;
    private var regMinutes = -1;
    private var wxRetry = false;
    private var wx;                            // the weather array (see WeatherService.mc), or null
    private var aq;                            // the last air quality (see WeatherService.mc), or null
    private var wxErr;                         // the last fetch error, or null

    private var locLat;
    private var locLon;
    private var sunRead = -100000;
    private var riseM = -1;
    private var setM = -1;
    private var dawnM = -1;
    private var duskM = -1;
    private var polar = 0;

    private var pressRead = -100000;
    private var baroDrop;
    private var baroStill = false;
    private var bodyBattery;
    private var stress;

    function initialize() {
        WatchFace.initialize();
        cfg = Cfg.loadAll();
        ctx = new Context();
        var saved = Application.Storage.getValue("loc");
        if (saved instanceof Lang.Array && saved.size() >= 2) {
            locLat = saved[0];
            locLon = saved[1];
        }
    }

    function onLayout(dc as Dc) as Void {
        if (WatchUi has :getSubscreen) {
            var box = WatchUi.getSubscreen();
            if (box != null) {
                subCx = box.x + box.width / 2;
                subCy = box.y + box.height / 2;
            }
        }
        // 36 dots, one every 10 degrees clockwise from 12 o'clock: the first at 10 degrees, the last back at the top
        arcX = new [36]b;
        arcY = new [36]b;
        for (var i = 0; i < 36; i += 1) {
            var a = ((i + 1) * 10 - 90) * Math.PI / 180.0;
            var x = (subCx - 0.5 + 29 * Math.cos(a) + 0.5).toNumber();
            var y = (subCy - 0.5 + 29 * Math.sin(a) + 0.5).toNumber();
            arcX[i] = (x > subCx) ? x - 1 : x;
            arcY[i] = (y > subCy) ? y - 1 : y;
        }
    }

    // ------------------------------------------------------------------------------------------- show, hide, sleep

    // First start does everything. Back from the settings menu (the heaviest moment: fonts reload) the forecast is
    // still in memory, and the sun times and the 3-hour pressure read wait for the next sleep, about 10 s later.
    function onShow() as Void {
        behindMenu = false;
        reloadLight();
        if (!started || wx == null) {
            loadWeather();
        }
        if (!started) {
            updateSun();
            readPressure(true);
            started = true;
        } else {
            var now = Time.now().value();
            sunRead = now - 900;                         // due at the next onEnterSleep
            pressRead = now - 900;
        }
        readOutside();
        runContext();
    }

    // The settings menu needs the room: drop everything that can be reloaded.
    function onHide() as Void {
        fTime = null;
        fWord = null;
        fSmall = null;
        fBig = null;
        fTiny = null;
        fMid = null;
        fMed = null;
        fIcons = null;
    }

    function settingsChanged() as Void {
        onShow();
    }

    function onExitSleep() as Void {
        awake = true;
        shownToday = false;
        if (fSmall != null) {
            readOutside();
            runContext();
        }
        WatchUi.requestUpdate();
    }

    function onEnterSleep() as Void {
        awake = false;
        behindMenu = false;                              // the watch went idle, so no menu is open
        if (shownToday) {
            ctx.todaySeen = dayKey();                    // the morning briefing was seen: not again today
            shownToday = false;
        }
        if (fSmall != null) {
            var now = Time.now().value();
            if (now - sunRead >= 900) {
                updateSun();
            }
            readPressure(false);
            readOutside();
            runContext();
        }
        WatchUi.requestUpdate();
    }

    private function reloadLight() as Void {
        if (fSmall == null) {
            fTime = WatchUi.loadResource(Rez.Fonts.Time);
            fWord = WatchUi.loadResource(Rez.Fonts.Word);
            fSmall = WatchUi.loadResource(Rez.Fonts.Small);
            fBig = WatchUi.loadResource(Rez.Fonts.Big);
            fTiny = WatchUi.loadResource(Rez.Fonts.Tiny);
            fMid = WatchUi.loadResource(Rez.Fonts.Mid);
            fMed = WatchUi.loadResource(Rez.Fonts.Med);
            fIcons = WatchUi.loadResource(Rez.Fonts.Icons);
        }
        cfg = Cfg.loadAll();
        t24 = use24(System.getDeviceSettings());
        lastMinute = -1;
    }

    // ------------------------------------------------------------------------------------------- weather

    private function loadWeather() as Void {
        var o = Application.Storage.getValue("wx");
        wx = (o instanceof Lang.Array && o.size() == 13) ? o : null;
        o = Application.Storage.getValue("aq");
        aq = (o instanceof Lang.Array && o.size() == 11) ? o : null;
        var e = Application.Storage.getValue("wxErr");
        wxErr = (e instanceof Lang.Number) ? e : null;
    }

    // The app is about to store a new forecast: let go of what can be rebuilt (fonts reload on the next redraw).
    function dropWeather() as Void {
        wx = null;
        ctx.w = null;
        ctx.aq = null;
        msg = null;
        if (!behindMenu) {
            onHide();
        }
    }

    function airArrived(a) as Void {
        aq = (a.size() == 11) ? a : null;
    }

    // Called by the app when a background fetch (or its error) arrived, outside a redraw.
    function weatherArrived(data) as Void {
        // a server error: fetch again in 5 minutes until one succeeds; without phone or position keep the interval
        wxRetry = (data instanceof Lang.Number) && data >= 500;
        if (data instanceof Lang.Array && data.size() == 13) {
            wx = data;
            wxErr = null;
        } else if (data instanceof Lang.Number) {
            wxErr = data;
        }
        if (fSmall == null && !behindMenu) {
            reloadLight();                               // fonts were let go while the forecast was stored
        }
        if (fSmall != null) {
            runContext();
        }
    }

    private function errText(age) {
        var e = wxErr;
        if (e == null) {
            return (wx == null) ? "WAITING" : "NO UPDATE";
        }
        if (e == -104 || e == -2) {
            return "NO PHONE";
        }
        if (e == -1) {
            return "NO GPS";
        }
        if (e >= 500) {
            return "SERVER BUSY";
        }
        return "ERROR " + e.format("%d");
    }

    // The forecast's age, in words, or why there is none.
    private function freshText(now) {
        if (wx != null && wx[4] > 0) {
            var age = (now - wx[0]) / 60;
            if (age < 0) {
                age = 0;
            }
            if (age <= 720) {
                return (age < 60) ? age.format("%d") + " MIN AGO" : (age / 60).format("%d") + " H AGO";
            }
        }
        return errText(0);
    }

    private function inBox(la, lo, a, b, c, d) {
        return la >= a && la <= b && lo >= c && lo <= d;
    }

    // Fills Context's inputs and asks it for the message. Outside the redraw (or once in a few minutes in it).
    private function runContext() as Void {
        if (System.getSystemStats().freeMemory < 3000) {
            return;                                      // keep the last message rather than risk the redraw
        }
        var now = Time.now().value();
        var ct = System.getClockTime();
        var ds = System.getDeviceSettings();
        ctx.now = now;
        ctx.localMin = ct.hour * 60 + ct.min;
        var w = (wx != null && wx[4] > 0 && wx[3] != null) ? wx : null;
        ctx.w = w;
        ctx.aq = aq;
        // yesterday's high and rain (x10), kept by the app from yesterday's last forecast; only if it is yesterday's
        var yd = Application.Storage.getValue("yday");
        ctx.yday = (yd instanceof Lang.Array && yd.size() >= 3
                    && yd[0] == (now + System.getClockTime().timeZoneOffset) / 86400 - 1) ? yd : null;
        var wt = Application.Storage.getValue("wet");
        if (wt instanceof Lang.Number && wt > ctx.wetT) {
            ctx.wetT = wt;                               // the last wet hour, for icy patches
        }
        ctx.wAge = (w == null) ? 9999 : (now - w[0]) / 60;
        // Garmin's own temperature for the circle, read here rather than in the redraw (used once the forecast is old)
        gTemp = null;
        if (cfg[Cfg.CIRCLE] == Cfg.C_TEMP && (w == null || now - w[0] >= 7800) && (Toybox has :Weather)) {
            var cc = Weather.getCurrentConditions();
            gTemp = (cc != null) ? cc.temperature : null;
        }
        ctx.q15 = false;
        ctx.far = false;
        if (w != null) {
            var la = w[1];
            var lo = w[2];
            // native 15-minute data: HRRR (conterminous US) and ICON-D2 / AROME (Central Europe), approximated
            ctx.q15 = inBox(la, lo, 25.0, 49.0, -125.0, -67.0) || inBox(la, lo, 43.5, 55.5, -4.0, 19.5);
            if (locLat != null && locLon != null) {
                var dy = (locLat - la) * 111.0;
                var dx = (locLon - lo) * 111.0 * Math.cos(la * Math.PI / 180.0);
                ctx.far = dx * dx + dy * dy > 625.0;     // over 25 km from where the forecast is for
            }
        }
        ctx.riseM = riseM;
        ctx.setM = setM;
        ctx.dawnM = dawnM;
        ctx.duskM = duskM;
        ctx.polar = polar;
        ctx.baroDrop = baroDrop;
        ctx.baroStill = baroStill;
        ctx.baroNow = livePressure();
        var ai = Activity.getActivityInfo();
        ctx.alt = (ai != null && (ai has :altitude)) ? ai.altitude : null;
        ctx.tempF = (ds has :temperatureUnits) && ds.temperatureUnits == System.UNIT_STATUTE;
        ctx.distMi = (ds has :distanceUnits) && ds.distanceUnits == System.UNIT_STATUTE;
        ctx.elevFt = (ds has :elevationUnits) && ds.elevationUnits == System.UNIT_STATUTE;
        t24 = use24(ds);
        ctx.t24 = t24;
        ctx.pollenOn = cfg[Cfg.POLLEN] == 1;
        ctx.errText = errText(0);
        msg = ctx.pick();
        pickT = now;
    }

    private function livePressure() {
        var ai = Activity.getActivityInfo();
        if (ai != null) {
            if ((ai has :meanSeaLevelPressure) && ai.meanSeaLevelPressure != null) {
                return ai.meanSeaLevelPressure / 100.0;
            }
            if ((ai has :ambientPressure) && ai.ambientPressure != null) {
                return ai.ambientPressure / 100.0;
            }
        }
        return null;
    }

    private function manageBackground() as Void {
        if (!(Toybox has :Background)) {
            return;
        }
        var want = wxRetry ? 5 : Cfg.MINUTES[cfg[Cfg.UPDATE]];
        if (regMinutes < 0) {
            var r = Application.Storage.getValue("wxReg");
            regMinutes = (r instanceof Lang.Number) ? r : 0;
        }
        var registered = Background.getTemporalEventRegisteredTime();
        if (registered == null || regMinutes != want) {
            Background.registerForTemporalEvent(new Time.Duration(want * 60));
            regMinutes = want;
            Application.Storage.setValue("wxReg", want);
        }
    }

    // ------------------------------------------------------------------------------------------- sensors

    // Pressure over 3 h from the watch's history (station pressure), and whether the watch kept its height:
    // only then is a change weather. Every 15 minutes, outside the redraw.
    private function readPressure(force) as Void {
        var now = Time.now().value();
        if (!force && now - pressRead < 900) {
            return;
        }
        if (!(Toybox has :SensorHistory) || !(SensorHistory has :getPressureHistory)
                || System.getSystemStats().freeMemory < 3500) {
            return;                                      // skipped: keep the last values
        }
        pressRead = now;
        var it = SensorHistory.getPressureHistory({ :period => new Time.Duration(10800),
                                                    :order => SensorHistory.ORDER_OLDEST_FIRST });
        var cnt = 0;
        var first = 0.0;
        var last = 0.0;
        var t0 = 0;
        var t1 = 0;
        var gap = 0;
        if (it != null) {
            var s = it.next();
            while (s != null) {
                var pd = s.data;
                var pw = s.when;
                if (pd != null && pw != null && pd > 10000) {
                    var t = pw.value();
                    if (cnt == 0) {
                        first = pd.toFloat();
                        t0 = t;
                    } else if (t - t1 > gap) {
                        gap = t - t1;
                    }
                    last = pd.toFloat();
                    t1 = t;
                    cnt += 1;
                }
                s = it.next();
            }
        }
        it = null;
        if (cnt < 2 || t1 - t0 < 9000) {
            baroDrop = null;                             // under 2.5 h of record (for example after a restart)
            baroStill = false;
            return;
        }
        baroDrop = (first - last) / 100.0;
        var moved = 9999.0;
        if (SensorHistory has :getElevationHistory) {
            var ie = SensorHistory.getElevationHistory({ :period => new Time.Duration(10800) });
            if (ie != null) {
                var lo = 99999.0;
                var hi = -99999.0;
                var e = ie.next();
                while (e != null) {
                    var ed = e.data;
                    if (ed != null) {
                        if (ed < lo) {
                            lo = ed.toFloat();
                        }
                        if (ed > hi) {
                            hi = ed.toFloat();
                        }
                    }
                    e = ie.next();
                }
                if (hi >= lo) {
                    moved = hi - lo;
                }
            }
        }
        baroStill = moved <= 30 && gap <= 3600;
    }

    // Body Battery and stress: the newest value of the last 30 minutes. A skipped or empty read keeps the last value.
    private function readOutside() as Void {
        var b = cfg[Cfg.BAR];
        var c = cfg[Cfg.CIRCLE];
        if (b == Cfg.B_BB || c == Cfg.C_BB) {
            var vb = newest(true);
            bodyBattery = (vb != null) ? vb : bodyBattery;
        }
        if (b == Cfg.B_STRESS || c == Cfg.C_STRESS) {
            var vs = newest(false);
            stress = (vs != null) ? vs : stress;
        }
    }

    private function newest(bb) {
        if (!(Toybox has :SensorHistory) || System.getSystemStats().freeMemory < 2500) {
            return null;
        }
        var opts = { :period => new Time.Duration(1800), :order => SensorHistory.ORDER_NEWEST_FIRST };   // 30 min: a smaller read
        var it = null;
        if (bb && (SensorHistory has :getBodyBatteryHistory)) {
            it = SensorHistory.getBodyBatteryHistory(opts);
        } else if (!bb && (SensorHistory has :getStressHistory)) {
            it = SensorHistory.getStressHistory(opts);
        }
        if (it == null) {
            return null;
        }
        var s = it.next();
        while (s != null) {
            var sd = s.data;
            if (sd != null && sd >= 0 && sd <= 100) {
                return sd;
            }
            s = it.next();
        }
        return null;
    }

    // Position (the watch's own fix under 2 hours old, else Garmin's weather position, else the last activity's)
    // and today's sun times with the face's own formula (within about 2 minutes of NOAA's).
    private function updateSun() as Void {
        var now = Time.now();
        sunRead = now.value();
        var loc = null;
        if (Toybox has :Position) {
            var pi = Position.getInfo();
            if (pi != null && pi.position != null && pi.when != null && now.value() - pi.when.value() < 7200
                    && pi.accuracy != Position.QUALITY_NOT_AVAILABLE) {
                loc = pi.position;
            }
        }
        if (loc == null && (Toybox has :Weather)) {
            var cc = Weather.getCurrentConditions();
            if (cc != null) {
                loc = cc.observationLocationPosition;
            }
        }
        if (loc == null) {
            var ai = Activity.getActivityInfo();
            if (ai != null && (ai has :currentLocation)) {
                loc = ai.currentLocation;
            }
        }
        if (loc != null) {
            rememberLocation(loc.toDegrees(), now.value());
        }
        if (locLat == null || locLon == null) {
            riseM = -1;
            setM = -1;
            dawnM = -1;
            duskM = -1;
            return;
        }
        var g = Gregorian.info(now, Time.FORMAT_SHORT);
        var n = dayOfYear(g.year, g.month, g.day);
        var tz = System.getClockTime().timeZoneOffset / 3600.0;
        var r = sunEvent(n, locLat, locLon, tz, true, 90.833);
        var s = sunEvent(n, locLat, locLon, tz, false, 90.833);
        if (r != null && s != null) {
            polar = 0;
            riseM = r;
            setM = s;
            var a = sunEvent(n, locLat, locLon, tz, true, 96.0);
            var b = sunEvent(n, locLat, locLon, tz, false, 96.0);
            dawnM = (a == null) ? r : a;
            duskM = (b == null) ? s : b;
        } else {
            var dec = 23.44 * Math.sin(2 * Math.PI * (284 + n) / 365.0);
            polar = (90.0 - (locLat - dec).abs() > 0) ? 1 : -1;
            riseM = -1;
            setM = -1;
            dawnM = -1;
            duskM = -1;
        }
    }

    private function rememberLocation(deg, t) as Void {
        if (deg == null || deg.size() < 2) {
            return;
        }
        var la = deg[0].toFloat();
        var lo = deg[1].toFloat();
        if (la < -90.0 || la > 90.0 || lo < -180.0 || lo > 180.0 || (la == 0.0 && lo == 0.0)) {
            return;
        }
        var moved = locLat == null || (la - locLat).abs() > 0.05 || (lo - locLon).abs() > 0.05;
        locLat = la;
        locLon = lo;
        if (moved) {
            Application.Storage.setValue("loc", [ la, lo ]);
            Application.Storage.setValue("locT", t);
        }
    }

    private function dayOfYear(year, month, day) {
        var n = day;
        for (var m = 1; m < month; m += 1) {
            n += MDAYS[m - 1];
        }
        if (month > 2 && year % 4 == 0) {                // every 4th year is a leap year until 2100
            n += 1;
        }
        return n;
    }

    // Local minutes of the moment the sun crosses a zenith angle (90.833 rise/set, 96 civil twilight), or null.
    private function sunEvent(n, lat, lon, tz, rising, zen) {
        var d2r = Math.PI / 180.0;
        var lngHour = lon / 15.0;
        var t = n + ((rising ? 6.0 : 18.0) - lngHour) / 24.0;
        var m = 0.9856 * t - 3.289;
        var l = wrap(m + 1.916 * Math.sin(m * d2r) + 0.020 * Math.sin(2.0 * m * d2r) + 282.634, 360.0);
        var ra = wrap(Math.atan2(0.91764 * Math.sin(l * d2r), Math.cos(l * d2r)) / d2r, 360.0) / 15.0;
        var sinDec = 0.39782 * Math.sin(l * d2r);
        var cosDec = Math.cos(Math.asin(sinDec));
        var cosH = (Math.cos(zen * d2r) - sinDec * Math.sin(lat * d2r)) / (cosDec * Math.cos(lat * d2r));
        if (cosH > 1.0 || cosH < -1.0) {
            return null;
        }
        var h = Math.acos(cosH) / d2r;
        if (rising) {
            h = 360.0 - h;
        }
        var local = wrap(h / 15.0 + ra - 0.06571 * t - 6.622 - lngHour + tz, 24.0);
        return (local * 60.0 + 0.5).toNumber() % 1440;
    }

    private function wrap(v, range) {
        while (v < 0) {
            v += range;
        }
        while (v >= range) {
            v -= range;
        }
        return v;
    }

    private function dayKey() {
        var g = Gregorian.info(Time.now(), Time.FORMAT_SHORT);
        return g.year * 400 + g.month * 32 + g.day;
    }

    private function use24(ds) {
        var f = cfg[Cfg.TIMEFMT];
        return (f == 1) ? true : ((f == 2) ? false : ds.is24Hour);
    }

    // ------------------------------------------------------------------------------------------- redraw

    function onUpdate(dc as Dc) as Void {
        if (behindMenu) {
            return;
        }
        if (skipOnce) {
            skipOnce = false;                            // just left the menu: draw on the next pass, once it is freed
            WatchUi.requestUpdate();
            return;
        }
        if (fSmall == null) {
            reloadLight();
        }
        var now = Time.now().value();
        var clock = System.getClockTime();
        if (clock.min != lastMinute) {
            lastMinute = clock.min;
            manageBackground();
            // safety nets for a watch that never wakes: sun every 6 h, Context every 5 minutes (every minute while
            // a countdown in minutes is shown)
            if (now - sunRead >= 21600) {
                updateSun();
            }
            var fam = (msg == null) ? -1 : msg[9];
            if (msg == null || now - pickT >= 300 || fam == 16 || fam == 6) {
                runContext();
            }
        }
        // Theme: dark (white on black) or light (black on white); the inverted block takes the ink colour
        var fg = (cfg[Cfg.THEME] == 1) ? Graphics.COLOR_BLACK : Graphics.COLOR_WHITE;
        var bg = (cfg[Cfg.THEME] == 1) ? Graphics.COLOR_WHITE : Graphics.COLOR_BLACK;
        dc.setColor(fg, bg);
        dc.clear();
        dc.setColor(fg, Graphics.COLOR_TRANSPARENT);
        if (msg == null) {
            drawTime(dc, clock, false);
            return;
        }
        if (awake && msg[10] == 206) {
            shownToday = true;
        }
        var inv = msg[7];
        drawSignal(dc, msg[0], msg[1], msg[2], freshText(now));
        drawCircle(dc, clock);
        if (inv) {
            dc.fillRectangle(0, 74, 176, 51);             // edge to edge, so the bar's value fits inside it
            dc.setColor(bg, Graphics.COLOR_TRANSPARENT);
        }
        drawTime(dc, clock, inv);
        drawBar(dc, inv ? 119 : 118);
        dc.setColor(fg, Graphics.COLOR_TRANSPARENT);
        var l1 = msg[3];
        var f1 = (dc.getTextWidthInPixels(l1, fBig) > 166) ? fSmall : fBig;
        dc.drawText(88, 128, f1, l1, Graphics.TEXT_JUSTIFY_CENTER);
        // wrist raise adds one fact under line 2 (which moves up 4 px); nothing on screen is replaced
        var more = awake && !msg[5].equals("");
        dc.drawText(88, more ? 146 : 150, fSmall, msg[4], Graphics.TEXT_JUSTIFY_CENTER);
        if (more) {
            dc.drawText(88, 160, fTiny, msg[5], Graphics.TEXT_JUSTIFY_CENTER);
        }
    }

    // The Signal: the forecast's age, the word and the detail share one left edge (the text column), with the
    // icon beside them; the block sits just below the circle's centre and clear of its bezel (x 102 on).
    private function drawSignal(dc as Dc, icon, word, detail, fresh) as Void {
        var w = dc.getTextWidthInPixels(word, fWord);
        var d = dc.getTextWidthInPixels(detail, fSmall);
        if (d > w) {
            w = d;
        }
        var tx = 34;
        if (icon >= 0 && Ic.W[icon] >= 20 && w <= 58) {
            drawIcon(dc, icon, 12, 47 - Ic.H[icon] / 2); // a weather picture beside the word and detail
            tx = 42;
        } else {
            var sm = smallIcon(icon);
            var cx = 20;
            if (w > 66) {
                tx = 28;
                cx = 13;
            }
            if (sm >= 0) {
                drawIcon(dc, sm, cx - Ic.W[sm] / 2, 47 - Ic.H[sm] / 2);
            }
        }
        var fx = 102 - dc.getTextWidthInPixels(fresh, fTiny);   // the age ends by x 101, clear of the circle's bezel
        if (tx < fx) {
            fx = (tx < 32) ? 32 : tx;
        }
        dc.drawText(fx, 19, fTiny, fresh, Graphics.TEXT_JUSTIFY_LEFT);
        dc.drawText(tx, 31, fWord, word, Graphics.TEXT_JUSTIFY_LEFT);
        dc.drawText(tx, 53, fSmall, detail, Graphics.TEXT_JUSTIFY_LEFT);
    }

    // The 11 px version of a weather picture, when the words leave no room for the large one.
    private function smallIcon(icon) {
        if (icon < 0 || Ic.W[icon] < 20) {
            return icon;
        }
        if (icon == Ic.W_SUN) {
            return Ic.I_SUNHZ;
        } else if (icon == Ic.W_MOON) {
            return Ic.N_MOON;
        } else if (icon == Ic.W_RAIN) {
            return Ic.N_RAIN;
        } else if (icon == Ic.W_SNOW) {
            return Ic.N_SNOW;
        } else if (icon == Ic.W_STORM) {
            return Ic.S_STORM;
        } else if (icon == Ic.W_FOG) {
            return Ic.N_EYE;
        }
        return Ic.N_CLOUD;
    }

    // Hours end 6 px left of the colon and minutes start 6 px right of it, measured on the digits' ink (TimeInk).
    private function drawTime(dc as Dc, clock, inv) as Void {
        var y = inv ? 75 : 74;
        var h = clock.hour;
        var two = t24;
        if (!two) {
            h = h % 12;
            if (h == 0) {
                h = 12;
            }
            two = h >= 10;
        }
        var hu = h % 10;
        var mt = clock.min / 10;
        var hx = 81 - (two ? TimeInk.A[h / 10] : 0) - TimeInk.X[hu] - TimeInk.W[hu];
        var mx = 95 - TimeInk.X[mt];
        dc.drawText(hx, y, fTime, h.format(two ? "%02d" : "%d"), Graphics.TEXT_JUSTIFY_LEFT);
        dc.drawText(mx, y, fTime, clock.min.format("%02d"), Graphics.TEXT_JUSTIFY_LEFT);
        dc.fillRectangle(86, y + 12, 4, 4);
        dc.fillRectangle(86, y + 26, 4, 4);
    }

    // ------------------------------------------------------------------------------------------- bar

    // The wearer's meter: ten cells centred under the time (x 34-142), its glyph to their left and, after a wrist
    // raise, its value to their right.
    private function drawBar(dc as Dc, y) as Void {
        var b = cfg[Cfg.BAR];
        if (b == Cfg.B_OFF) {
            return;
        }
        var v = barValue(b);
        var g = Ic.BAR[b];
        if (g != 255) {
            drawIcon(dc, g, 30 - Ic.W[g], y + 2 - Ic.H[g] / 2);
        }
        if (awake && v != null) {
            var n = v.toNumber();
            if (n > 999) {
                n = 999;
            }
            dc.drawText(146, y - 1, fTiny, (b == Cfg.B_BB || b == Cfg.B_STRESS) ? n.format("%d") : n.format("%d") + "%",
                        Graphics.TEXT_JUSTIFY_LEFT);
        }
        var lit = (v == null) ? 0 : ((v + 5) / 10).toNumber();
        if (lit > 10) {
            lit = 10;
        }
        for (var i = 0; i < 10; i += 1) {
            var x = 34 + i * 11;
            if (i < lit) {
                dc.fillRectangle(x, y, 10, 4);
            } else {
                dc.fillRectangle(x, y + 3, 10, 1);
            }
        }
    }

    private function pct(a, b) {
        return (a == null || b == null || b <= 0) ? null : a * 100.0 / b;
    }

    private function barValue(b) {
        var info = ActivityMonitor.getInfo();
        if (b == Cfg.B_STEPS) {
            return pct(info.steps, info.stepGoal);
        }
        if (b == Cfg.B_FLOORS) {
            return ((info has :floorsClimbed) && (info has :floorsClimbedGoal)) ? pct(info.floorsClimbed, info.floorsClimbedGoal) : null;
        }
        if (b == Cfg.B_INT_DAY || b == Cfg.B_INT_WEEK) {
            if (!(info has :activeMinutesWeek) || !(info has :activeMinutesWeekGoal) || info.activeMinutesWeekGoal == null) {
                return null;
            }
            if (b == Cfg.B_INT_WEEK) {
                return (info.activeMinutesWeek == null) ? null : pct(info.activeMinutesWeek.total, info.activeMinutesWeekGoal);
            }
            return ((info has :activeMinutesDay) && info.activeMinutesDay != null)
                ? pct(info.activeMinutesDay.total, info.activeMinutesWeekGoal / 7.0) : null;
        }
        if (b == Cfg.B_MOVE) {
            return ((info has :moveBarLevel) && info.moveBarLevel != null) ? info.moveBarLevel * 20 : null;
        }
        if (b == Cfg.B_BB) {
            return bodyBattery;
        }
        if (b == Cfg.B_STRESS) {
            return stress;
        }
        var st = System.getSystemStats();
        if (b == Cfg.B_BATT) {
            return st.battery;
        }
        return (st has :solarIntensity) ? st.solarIntensity : null;
    }

    // ------------------------------------------------------------------------------------------- circle

    private function drawCircle(dc as Dc, clock) as Void {
        var mode = cfg[Cfg.CIRCLE];
        if (mode == Cfg.C_OFF) {
            return;
        }
        if (mode == Cfg.C_SEC && !awake) {
            mode = Cfg.C_DATE;                           // seconds only after a wrist raise; the date at rest
        }
        var cx = subCx;
        var y0 = subCy - 31;
        var C = Graphics.TEXT_JUSTIFY_CENTER;
        if (mode == Cfg.C_DATE) {
            var g = Gregorian.info(Time.now(), Time.FORMAT_SHORT);
            var dw = g.day_of_week - 1;
            // weekday over the day of the month; the arc shows how far through the month it is
            dc.drawText(cx, y0 + 14, fSmall, DAYS.substring(dw * 3, dw * 3 + 3), C);
            dc.drawText(cx, y0 + 29, fMid, g.day.format("%d"), C);
            drawArc(dc, g.day * 100 / (MDAYS[g.month - 1] + ((g.month == 2 && g.year % 4 == 0) ? 1 : 0)));
            return;
        }
        if (mode == Cfg.C_SEC) {
            dc.drawText(cx, y0 + 19, fMid, clock.sec.format("%02d"), C);
            drawArc(dc, clock.sec * 100 / 59);
            return;
        }
        if (mode == Cfg.C_TEMP) {
            // weather now: the forecast's picture for this hour over the temperature (the picture only while the
            // forecast is fresh; then the temperature alone, from Garmin's weather)
            var t = currentTemp();
            var tx = (t == null) ? "--" : num(ctx.tempF ? t * 1.8 + 32 : t);
            var wi = nowIcon();
            if (wi < 0) {
                dc.drawText(cx, y0 + 14, fWord, tx + "\u00b0", C);
                dc.drawText(cx, y0 + 42, fTiny, "NOW", C);
                return;
            }
            drawIcon(dc, wi, cx - Ic.W[wi] / 2, y0 + 17 - Ic.H[wi] / 2);
            var tf = (tx.length() >= 3) ? fMed : fMid;   // digits centred, the degree sign hangs to the right
            dc.drawText(cx - dc.getTextWidthInPixels(tx, tf) / 2, y0 + ((tf == fMed) ? 34 : 31), tf, tx + "\u00b0",
                        Graphics.TEXT_JUSTIFY_LEFT);
            drawArc(dc, rainChance());
            return;
        }
        var icon = -1;
        var value = null;
        var unit = "";
        var arc = null;
        if (mode == Cfg.C_HR) {
            icon = Ic.I_HEART;
            var ai = Activity.getActivityInfo();
            value = (ai != null) ? ai.currentHeartRate : null;
            unit = "BPM";
        } else if (mode == Cfg.C_BB) {
            icon = Ic.I_BOLT;
            value = bodyBattery;
            unit = "BB";
            arc = bodyBattery;
        } else if (mode == Cfg.C_ALT) {
            icon = Ic.F_MOUNT;
            var aa = Activity.getActivityInfo();
            var a = (aa != null && (aa has :altitude)) ? aa.altitude : null;
            value = (a == null) ? null : (ctx.elevFt ? a * 3.281 : a);
            unit = ctx.elevFt ? "FT" : "M";
        } else if (mode == Cfg.C_MOON) {
            icon = Ic.N_MOON;
            var age = (Time.now().value() - NEW_MOON) / 86400.0;
            age = age - (age / SYNODIC).toNumber() * SYNODIC;
            value = (1.0 - Math.cos(2.0 * Math.PI * age / SYNODIC)) * 50.0;
            unit = "LIT %";
            arc = age * 100 / SYNODIC;
        } else if (mode == Cfg.C_BATT) {
            icon = Ic.F_BATT;
            var st = System.getSystemStats();
            value = (st has :batteryInDays) ? st.batteryInDays : null;
            unit = "DAYS";
            arc = st.battery;
        } else if (mode == Cfg.C_NOTIF) {
            icon = Ic.F_MAIL;
            value = System.getDeviceSettings().notificationCount;
            unit = "NEW";
        } else if (mode == Cfg.C_STEPS) {
            icon = Ic.G_STEPS;
            var im = ActivityMonitor.getInfo();
            value = im.steps;
            unit = "STEPS";
            arc = pct(im.steps, im.stepGoal);
        } else if (mode == Cfg.C_INT_DAY || mode == Cfg.C_INT_WEEK) {
            var week = mode == Cfg.C_INT_WEEK;
            icon = week ? Ic.F_WEEK : Ic.G_INT;
            unit = week ? "WEEK" : "TODAY";
            var ia = ActivityMonitor.getInfo();
            var goal = (ia has :activeMinutesWeekGoal) ? ia.activeMinutesWeekGoal : null;
            var am = week ? ((ia has :activeMinutesWeek) ? ia.activeMinutesWeek : null)
                          : ((ia has :activeMinutesDay) ? ia.activeMinutesDay : null);
            value = (am == null) ? null : am.total;
            arc = (goal == null) ? null : pct(value, week ? goal : goal / 7.0);
        } else if (mode == Cfg.C_STRESS) {
            icon = Ic.G_STRESS;
            value = stress;
            unit = "STRESS";
            arc = stress;
        } else if (mode == Cfg.C_SOLAR) {
            icon = Ic.G_SOLAR;
            var ss = System.getSystemStats();
            value = (ss has :solarIntensity) ? ss.solarIntensity : null;
            unit = "SOLAR";
            arc = value;
        } else if (mode == Cfg.C_PRESS) {
            icon = Ic.F_BARO;
            value = livePressure();
            unit = ctx.tempF ? "INHG" : "HPA";
        }
        if (icon >= 0) {
            drawIcon(dc, icon, cx - Ic.W[icon] / 2, y0 + 7);
        }
        var vt = (value == null) ? "--" : num(value);
        if (mode == Cfg.C_PRESS && value != null && ctx.tempF) {
            vt = (value * 0.02953).format("%.2f");
        }
        if (mode == Cfg.C_STEPS && value != null && value >= 10000) {
            vt = (value / 1000.0).format("%.1f");        // five digits would touch the ring
            unit = "K STEPS";
        }
        var f = (vt.length() >= 4) ? fMed : fMid;
        dc.drawText(cx, y0 + ((f == fMed) ? 21 : 19), f, vt, C);
        dc.drawText(cx, y0 + 42, fTiny, unit, C);   // tiny: the full ring clears it
        if (arc != null) {
            drawArc(dc, arc);
        }
    }

    // This hour's weather picture from the forecast's WMO code (bits 18-24 of the first packed series), or -1 when
    // the forecast is over 2 hours old. Clear and partly cloudy turn to their night pictures after sunset.
    private function nowIcon() {
        var now = Time.now().value();
        if (wx == null || wx[4] <= 0 || wx[5] == null || now - wx[0] >= 7800) {
            return -1;
        }
        var i = (now - wx[3] + 1800) / 3600;
        if (i < 0 || i >= wx[5].size()) {
            return -1;
        }
        var c = (wx[5][i] >> 18) & 127;
        if (c == 127) {
            return -1;
        }
        var ct = System.getClockTime();
        var m = ct.hour * 60 + ct.min;
        var night = (riseM >= 0) ? (m < riseM || m >= setM) : polar < 0;
        if (c <= 1) {
            return night ? Ic.W_MOON : Ic.W_SUN;
        }
        if (c == 2) {
            return night ? Ic.W_CLOUD : Ic.W_PARTLY;
        }
        if (c == 45 || c == 48) {
            return Ic.W_FOG;
        }
        if (c >= 95) {
            return Ic.W_STORM;
        }
        if ((c >= 71 && c <= 77) || c == 85 || c == 86) {
            return Ic.W_SNOW;
        }
        return (c >= 51) ? Ic.W_RAIN : Ic.W_CLOUD;
    }

    // The highest rain chance of the next 3 hours (the low 7 bits of the second packed series; each hour's chance is
    // for the hour before its stamp), or null. Only called while nowIcon() found a fresh forecast.
    private function rainChance() {
        var a = wx[6];
        if (a == null) {
            return null;
        }
        var b = (Time.now().value() - wx[3] + 3599) / 3600;
        var best = -1;
        for (var k = (b < 0) ? 0 : b; k < b + 3 && k < a.size(); k += 1) {
            var p = a[k] & 127;
            if (p != 127 && p > best) {
                best = p;
            }
        }
        return (best < 0) ? null : best;
    }

    // The current temperature: the forecast's instant value while fresh, else Garmin's own weather.
    private function currentTemp() {
        if (wx != null && wx[4] > 0 && wx[5] != null && Time.now().value() - wx[0] < 7800) {
            var i = (Time.now().value() - wx[3] + 1800) / 3600;
            if (i >= 0 && i < wx[5].size()) {
                var v = wx[5][i] & 2047;                 // temperature: the low 11 bits, x10 C + 1000
                if (v != 2047) {
                    return (v - 1000) / 10.0;
                }
            }
        }
        return gTemp;                                    // read in runContext, outside the redraw
    }

    private function drawArc(dc as Dc, pct) as Void {
        if (pct == null || arcX == null) {
            return;
        }
        // any value above 0 lights the first dot; 100 % closes the ring
        var lit = (pct <= 0) ? 0 : (pct * 36 / 100.0 + 0.999).toNumber();
        if (lit > 36) {
            lit = 36;
        }
        for (var i = 0; i < lit; i += 1) {
            dc.fillRectangle(arcX[i], arcY[i], 2, 2);
        }
    }

    private function num(v) {
        return ((v < 0) ? (v - 0.5) : (v + 0.5)).toNumber().format("%d");
    }

    private function drawIcon(dc as Dc, idx, x, y) as Void {
        dc.drawText(x, y, fIcons, (65 + idx).toChar().toString(), Graphics.TEXT_JUSTIFY_LEFT);
    }
}
