import Toybox.Graphics;
import Toybox.Lang;
import Toybox.WatchUi;

// On-watch settings, in the style of Solar Frontier's: one plain view with two levels (the six settings with their
// current values, then the options of one setting). No Menu2, no stacked views and no cached labels, so it fits
// beside the face. UP/DOWN move, GPS opens or saves, BACK cancels or goes up; BACK at the top closes the settings.
class MenuView extends WatchUi.View {
    private var mFace;           // the watch face, told when the settings close
    private var mLevel = 0;      // 0 settings, 1 options
    private var mItem = 0;
    private var mOption = 0;
    private var mHead = "";
    private var mEntry = "";
    private var mValue = "";     // level 0: the current value; level 1: CURRENT when it is the stored one

    function initialize(face) {
        View.initialize();
        mFace = face;
        show();
    }

    private function count() {
        return (mLevel == 0) ? Cfg.N : SetText.COUNTS[mItem];
    }

    function step(d) as Void {
        var n = count();
        if (mLevel == 0) {
            mItem = (mItem + d + n) % n;
        } else {
            mOption = (mOption + d + n) % n;
        }
        show();
    }

    private function show() as Void {
        var cur = Cfg.get(mItem);
        if (mLevel == 0) {
            mHead = "CONTEXT AHEAD";
            mEntry = SetText.text(mItem, 0);
            mValue = SetText.text(mItem, cur + 1);
        } else {
            mHead = SetText.text(mItem, 0);
            mEntry = SetText.text(mItem, mOption + 1);
            mValue = (mOption == cur) ? "CURRENT" : "";
        }
        WatchUi.requestUpdate();
    }

    function select() as Void {
        if (mLevel == 0) {
            mOption = Cfg.get(mItem);
            mLevel = 1;
        } else {
            Cfg.set(mItem, mOption);
            mLevel = 0;
        }
        show();
    }

    // BACK in the options cancels without saving; at the top, false lets the watch close the settings.
    function back() as Lang.Boolean {
        if (mLevel == 0) {
            return false;
        }
        mLevel = 0;
        show();
        return true;
    }

    function onHide() as Void {
        if (mFace != null) {
            mFace.behindMenu = false;              // the face draws again, after one skipped redraw
            mFace.skipOnce = true;                 // so the settings are released first
        }
    }

    // Centred text; the main line takes the largest system font that fits 150 px.
    private function line(dc as Graphics.Dc, y, big, text) as Void {
        var f = big ? Graphics.FONT_SMALL : Graphics.FONT_XTINY;
        if (big && dc.getTextWidthInPixels(text, f) > 150) {
            f = Graphics.FONT_TINY;
        }
        if (big && dc.getTextWidthInPixels(text, f) > 150) {
            f = Graphics.FONT_XTINY;
        }
        dc.drawText(88, y, f, text, Graphics.TEXT_JUSTIFY_CENTER);
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        var light = Cfg.get(Cfg.THEME) == 1;
        var fg = light ? Graphics.COLOR_BLACK : Graphics.COLOR_WHITE;
        var bg = light ? Graphics.COLOR_WHITE : Graphics.COLOR_BLACK;
        dc.setColor(fg, bg);
        dc.clear();
        line(dc, 62, false, mHead);      // below the round sub-screen
        dc.drawLine(26, 81, 150, 81);
        line(dc, 92, true, mEntry);
        line(dc, 122, false, mValue);
        dc.drawLine(30, 148, 146, 148);
        var pos = (mLevel == 0) ? mItem : mOption;
        dc.drawText(88, 151, Graphics.FONT_XTINY, (pos + 1).format("%d") + "/" + count().format("%d"),
                    Graphics.TEXT_JUSTIFY_CENTER);
    }
}

class MenuDelegate extends WatchUi.BehaviorDelegate {
    private var mMenu;

    function initialize(menu) {
        BehaviorDelegate.initialize();
        mMenu = menu;
    }

    function onNextPage() {
        mMenu.step(1);
        return true;
    }

    function onPreviousPage() {
        mMenu.step(-1);
        return true;
    }

    function onSelect() {
        mMenu.select();
        return true;
    }

    function onBack() {
        return mMenu.back();
    }
}
