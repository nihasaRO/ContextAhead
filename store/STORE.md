# Context Ahead: Connect IQ Store listing

## App name
Context Ahead

## Type and category
Watch face. Device: Instinct 3 Solar (Connect IQ ID `instinct3solar45mm`). Price: free.

## Short description
The one weather or light message that changes your next move. Calm when nothing does.

## Description (paste into the store, about 3955 characters)

Your watch already knows the weather. Context Ahead tells you what it means for the next few hours, in one line.

No wall of icons and percentages. One message, chosen from the forecast and your watch's own sensors: the weather or light condition most likely to change what you do next. When nothing needs you, it says CALM. When something does, it says exactly what, when and how much.

A DAY WITH CONTEXT AHEAD
06:10  DAWN ~40 MIN · first light soon, sunrise 07:20, dry all day
07:15  TODAY HI 24° (75°F) · raise your wrist: 8° COLDER TODAY
11:00  UV VERY HIGH · UV 8+ until ~16:00, peak 9
14:15  RAIN BY 15:00 · 70%, about 4 mm (0.16 in), then dry ~17:00
15:20  STORM ~1 H · the clock inverts: gusts to 68 km/h (42 mph), over ~19:00
18:05  LIGHT 0:25 LEFT · sunset 18:30, civil dusk 19:02
20:30  TMRW RAIN 70% · from ~09:00, 7 mm (0.28 in), high 6° (43°F)
23:40  MOON BELOW · rises 04:00, clear sky

WHAT IT WATCHES FOR
Act now (the clock inverts so you can't miss it)
• Thunderstorm within the hour • Gusts of 65 km/h (40 mph) or more
• Dense fog • Freezing rain • Blowing snow
• Dangerous heat (feels like 40°C / 104°F) or cold (wind chill -28°C / -18°F)
• Extreme air quality

Light running out
• The last 2 hours of daylight, counted down; the final 30 minutes come first

Rain or snow within 2 hours
• When it starts, how likely, how much, when it stops
• Heavy rain, a dry break between showers, rain still to fall

Worth adapting to
• Icy patches: wet ground, then freezing air
• Steady wind for cyclists • Wind building • Heat • UV 8+
• Poor air, dust, pollen (Europe, optional)
• A sharp drop with a wind shift • Frost tonight • A hot night
• Big rain or snow totals • A snow line just above you

Quiet moments
• Dawn, a morning briefing, sunshine still to come
• Tomorrow after sunset, the moon or tonight's low at night

RAISE YOUR WRIST FOR MORE
One extra fact appears without anything disappearing: when the rain is heaviest, the peak gust, new snow overnight, the cool hours of a hot day, tomorrow against today, the reading behind an air index. Your bar shows its value too.

HONEST BY DESIGN
• Always shows how old the forecast is (12 MIN AGO) or why there is none (NO PHONE)
• Minute countdowns only where the forecast really runs in 15-minute steps (Central Europe, the US). Elsewhere: RAIN BY 16:00, never a made-up minute
• An old forecast loses its urgency and says it is old. It never shows CALM over a warning it can no longer check
• Calm by default. The message changes when the weather does, not every time you look

THE TIME AND THE REST ARE YOURS
Big, clear digits. Beside them, a circle and a bar you fill:
• Circle: date with a month ring, weather now with the rain chance, pressure, moon, steps, intensity minutes, heart rate, Body Battery, stress, altitude, battery days, solar, notifications, seconds
• Bar: steps, floors, intensity, move, Body Battery, stress, battery, solar
• Dark or light theme, European or US air index, weather updates every 5 minutes to 2 hours
Change it all on the watch (hold MENU > Watch Face > Customize) or in Garmin Connect.

WORKS WHEN YOUR PHONE DOESN'T
The last forecast stays, with its age. Sun times are calculated on the watch, and the barometer reports falling pressure while you stay at the same height.

Made for Europe and North America. Metric or imperial (°C or °F, km/h or mph, mm or inches, metres or feet) and 24- or 12-hour time, all following your watch's settings.

Weather data by Open-Meteo.com (CC BY 4.0), free, no account needed. Air quality and pollen: Copernicus Atmosphere Monitoring Service (CAMS) via Open-Meteo.

A watch face cannot vibrate. Messages come from forecasts and your barometer, not official weather warnings.

Permissions: location (rounded to about 1 km, sent to Open-Meteo), sensor history (barometer, elevation), background internet (the weather update). No data is collected.

A personal project, built with the help of AI and shared for free.

## What's new
1.5:
- Icy patches: a warning when wet ground meets freezing air.
- Steady wind for cyclists, new snow in the morning, and the cool hours of a hot day.
- Fixes: yesterday's values no longer show after midnight on an old forecast; a clearer temperature-drop message.

1.4:
- Morning briefing: raise your wrist to see if today is colder or warmer than yesterday.
- Snow line now outside Europe too, estimated from the freezing level, with the 0° line on a wrist raise.
- Wet ground: after a rainy day, calm mornings tell you how much fell yesterday.

## Support text
Questions and feedback: (your support email or page).

## Store assets in this folder
Regenerate them with `SAIRA_FONT_DIR=... python3 tools/store_assets.py` (after `node tools/check/extract.cjs ...`, see the script's header).

| File | Use |
| --- | --- |
| `app-icon-125.png` | App icon, 125 x 125 px (the store's maximum): the Signal's rain cloud, the circle, the bar |
| `cover-500.png` | Cover image (web and mobile), 500 x 500 px: the storm face (clock inverted) in a drawn watch case with orange rim and lens accents, centred on a dark background with an orange glow, no title |
| `hero-1440x720.png` | Hero: a calm day, rain in 15 minutes (light theme), act now |
| `anatomy-1440x900.png` | The face with numbered zones and what each one does |
| `screenshot-01-make-it-yours.png` | Dark and light themes, the circle's options, the bar's options |
| `screenshot-02-spring.png` | Showers with honest timing, wind building on the lake, a snow line on the trail |
| `screenshot-03-summer.png` | Storm (inverted clock), dry heat, very high UV |
| `screenshot-04-autumn-winter.png` | Daylight left, freezing fog (inverted), snow totals |

Every message in these pictures is the face's own engine output for that situation (the transpiled `Context.mc` run on the simulation cases), drawn with the face's fonts and coordinates. Compare them once with the simulator before uploading.

## Upload checklist
1. Build and test in the simulator. Record Peak Memory with the heaviest settings (circle Body Battery, bar Stress, pollen on, updates every 5 minutes).
2. Test on the watch: a day of messages, a wrist raise, the settings menu, both themes, airplane mode.
3. Run `.\build.ps1 -Export`, which writes `bin\ContextAhead.iq`, signed with your developer key.
4. At apps.garmin.com: Developer Dashboard > Upload an app > `ContextAhead.iq`.
5. Fill in the listing:
   - name, short description, description, what's new;
   - category Watch Faces, price free;
   - app icon, hero image, anatomy and the four screenshots from this folder;
   - support contact.
6. Keep `bin\ContextAhead.prg.debug.xml` from this exact build, to read crash reports later.
