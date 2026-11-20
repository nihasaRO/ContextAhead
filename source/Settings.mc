import Toybox.Application;
import Toybox.Lang;

// The face's settings: seven numbers stored as properties "k0".."k6" (phone and watch share them).
// Option counts, defaults and the menu texts (string resources) come from SetText.mc (tools/make_project.py).
module Cfg {
    const CIRCLE = 0;
    const BAR = 1;
    const TIMEFMT = 2;
    const UPDATE = 3;
    const POLLEN = 4;
    const THEME = 5;
    const AQI = 6;
    const N = 7;
    const MINUTES = [5, 10, 15, 20, 30, 45, 60, 90, 120]b;   // background fetch interval per option

    // Circle options
    const C_DATE = 0;
    const C_TEMP = 1;                // weather now: picture and temperature
    const C_PRESS = 2;
    const C_MOON = 3;
    const C_STEPS = 4;
    const C_INT_DAY = 5;
    const C_INT_WEEK = 6;
    const C_HR = 7;
    const C_BB = 8;
    const C_STRESS = 9;
    const C_ALT = 10;
    const C_BATT = 11;
    const C_SOLAR = 12;
    const C_NOTIF = 13;
    const C_SEC = 14;
    const C_OFF = 15;

    // Bar options
    const B_STEPS = 0;
    const B_FLOORS = 1;
    const B_INT_DAY = 2;
    const B_INT_WEEK = 3;
    const B_MOVE = 4;
    const B_BB = 5;
    const B_STRESS = 6;
    const B_BATT = 7;
    const B_SOLAR = 8;
    const B_OFF = 9;

    function loadAll() {
        var a = new [N];
        for (var i = 0; i < N; i += 1) {
            a[i] = get(i);
        }
        return a;
    }

    // A stored option, or the default when it is missing or out of range.
    function get(i) {
        var v = Application.Properties.getValue("k" + i);
        if (v instanceof Lang.Number && v >= 0 && v < SetText.COUNTS[i]) {
            return v;
        }
        return SetText.DEFAULTS[i];
    }

    function set(i, v) {
        Application.Properties.setValue("k" + i, v);
    }
}
