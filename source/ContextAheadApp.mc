import Toybox.Application;
import Toybox.Lang;
import Toybox.System;
import Toybox.Time;
import Toybox.WatchUi;

// Annotated for the background process too, which runs the Open-Meteo fetch.
(:background)
class ContextAheadApp extends Application.AppBase {
    private var mView;

    function initialize() {
        AppBase.initialize();
    }

    function getInitialView() {
        mView = new ContextAheadView();
        return [ mView ];
    }

    // Settings changed in the Garmin Connect app.
    function onSettingsChanged() {
        Application.Storage.deleteValue("aqT");          // the air index scale may have changed: refetch it
        if (mView != null) {
            mView.settingsChanged();
        }
        WatchUi.requestUpdate();
    }

    // On-watch settings: hold MENU > Watch Face > Customize (in the simulator: Settings > Trigger App Settings is
    // the phone's version; the watch's own menu opens from the face's menu). One small view, no stacked menus.
    function getSettingsView() {
        if (mView != null) {
            mView.onHide();                              // free the face's fonts before the menu is built
            mView.behindMenu = true;                     // and don't draw it while the menu covers the screen
        }
        var menu = new MenuView(mView);
        return [ menu, new MenuDelegate(menu) ];
    }

    function getServiceDelegate() {
        return [ new WeatherService() ];
    }

    // Today's forecast high, rain and snow totals, kept under "day"; when the date changes, the kept day becomes
    // "yday" (yesterday), which the morning briefing compares with and the quiet messages use for wet ground.
    private function remember(dl) as Void {
        if (!(dl instanceof Lang.Array) || dl.size() < 13) {
            return;
        }
        var today = (Time.now().value() + System.getClockTime().timeZoneOffset) / 86400;
        var kept = Application.Storage.getValue("day");
        if (kept instanceof Lang.Array && kept[0] != today) {
            if (kept[0] == today - 1) {
                Application.Storage.setValue("yday", kept);
            } else {
                Application.Storage.deleteValue("yday");
            }
        }
        Application.Storage.setValue("day", [ today, dl[0], dl[12], (dl.size() > 13) ? dl[13] : null ]);
    }

    // A fetch arrived. Storage serialises what it writes, which briefly needs room for a copy, so the face first lets
    // go of everything it can rebuild (the old forecast and air data, its fonts, the last message). Air quality is
    // stored apart (it arrives at most hourly).
    function onBackgroundData(data) {
        if (data instanceof Lang.Array && data.size() == 13) {
            if (mView != null) {
                mView.dropWeather();
            }
            var a = data[12];
            data[12] = null;
            if (a instanceof Lang.Array) {
                if (System.getSystemStats().freeMemory > 3000) {
                    Application.Storage.setValue("aq", a);
                }
                Application.Storage.setValue("aqT", a[0]);
                if (mView != null) {
                    mView.airArrived(a);
                }
            }
            a = null;
            remember(data[11]);
            // the hour just past was wet (0.3 mm or more): kept for icy patches, since the next forecast starts later
            var p = data[7];
            if (p instanceof Lang.Array && p.size() > 0 && (p[0] & 4095) >= 3 && (p[0] & 4095) != 4095) {
                Application.Storage.setValue("wet", data[3]);
            }
            // the copy storage makes needs a few kB; with less free the forecast stays in memory only this time
            // (the face keeps working; after a restart it waits for the next fetch)
            if (System.getSystemStats().freeMemory > 5000) {
                Application.Storage.setValue("wx", data);
            }
            Application.Storage.deleteValue("wxErr");
        } else if (data instanceof Lang.Number) {
            Application.Storage.setValue("wxErr", data);
            if (data == -403) {
                Application.Storage.setValue("wxSmall", true);   // out of memory: ask for 16 hours from now on
            }
        }
        if (mView != null && data != null) {
            mView.weatherArrived(data);
        }
        WatchUi.requestUpdate();
    }
}
