# Changelog

Store versions: 1.2.1 is the build of Nov 3, 2026; 1.3 and 1.4 are builds of Nov 12, 2026; 1.5 is the build of Nov 18, 2026. The store number is entered at upload (the manifest has no version field).

## 1.5 (Nov 18, 2026)
From an audit of who goes outside and what they need to know (runners, cyclists, skiers, dog walkers, photographers; hot ground and golden hour were built and dropped for memory), plus six fixes found by comparing with Solar Frontier's audit.

New messages:
- **Icy patches:** "ICE / RISK" (or the hour it starts), "ICY PATCHES -2°", "WET UNTIL ~18:00", raise "SHADE AND BRIDGES". Fires when the ground was wet (rain or snow in the last hours, or still to come) and the air then reaches 0° or below with nothing falling, within 6 hours. The face remembers the last wet hour across forecasts. Always a risk, never a claim about the road.
- **Steady wind:** "WIND / 34 KMH", "FROM THE NW", "EASING ~17:00", raise the gusts. For a steady 30 km/h (19 mph) or more over the next 3 hours by day, below the gust warnings.

New raise lines:
- **Cool hours on a hot day:** on 30° days the morning briefing's raise says when it gets warm ("25° BY ~10:00") or when it cools again ("UNDER 25° ~21:00").
- **New snow:** the morning briefing's raise shows "+13 CM NEW SNOW" when 5 cm or more fell since yesterday (yesterday's total plus what fell since midnight).
- **Tomorrow against today:** the evening forecast's raise says "10° COLDER" or "MUCH WARMER" when tomorrow's high is 5° or more from today's.

Fixes:
- After midnight, a forecast fetched the evening before no longer shows yesterday's high, UV and rain as today's: its "tomorrow" becomes today and the rest is left out until the next update.
- The temperature-drop message now reads "TEMP / ~15:00", "DOWN TO 5°  WIND NW", "9° DROP IN 2H", raise "NOW 14°".
- The snow line counts from 600 m above you (was 300 m).
- A smaller forecast to receive and store: 20 hours instead of 24 (every message looks 12 to 15 hours ahead), 15-minute rain only where it really exists (Central Europe, the US), and the freezing level only where the model gives no snowfall height of its own (outside Central Europe).
- Garmin's own temperature (for Weather now in the circle, once the forecast is over 2 hours old) is read outside the redraw.
- The morning briefing's UV and sunset line fits with a two-digit UV.
- Less code, same screens: one shared "when does it ease" search replaces five copies; the messages lose an always-empty argument; small helpers write repeated texts (sunset, first light, daily temperatures); the quiet messages and the circle are tightened. Every message was compared before and after on 80,000 random situations and the 85 test cases in both unit systems: identical. The circle's leap-year rule is now "every fourth year", exact until 2100.

Memory (simulator, heaviest settings, with a background update): code 35,192 B (1.4: 34,019), data 9,000 B (8,735), 55.9 kB in use (54.6), 57.1 kB peak (55.7), 58.3 kB peak stack trace (57.0) of 59.9 kB.

## 1.4 (Nov 12, 2026)
Three additions, all on the wrist-raise line or in the quiet messages. (Offline storm signs were built and then removed before release: Garmin's own barometer Storm Alert already does it, with vibration and a rate you choose.)
- **Colder or warmer than yesterday:** the morning briefing's raise line says "8° COLDER TODAY" when today's high is 3° or more from yesterday's (the app keeps each day's high from that day's last forecast). Otherwise yesterday's rain, otherwise tonight's low.
- **Snow line outside Europe:** where the model gives no snowfall height (North America, the Nordics), the snow line is estimated 300 m below the freezing level and marked "~"; the wrist raise shows the 0° line itself ("0° LINE 2400 M").
- **Wet ground:** after 10 mm or more of rain yesterday, the calm and sunny messages (and the briefing, when the temperature did not change much) add "25 MM YESTERDAY" on a wrist raise.
- Store cover: the topographic style.

## 1.3 (Nov 12, 2026)
Learnings from Solar Frontier 1.9.x.
A thunderstorm within 2 hours now ranks with rain timing and beats the rain it brings (it used to hide behind "RAIN BY 17:00"). Back from the settings menu, the face keeps its forecast in memory and leaves the sun times and the 3-hour pressure read to the next sleep, about 10 seconds later. The 24-hour flag is read outside the redraw, and the stress and Body Battery reads look at 30 minutes instead of 60.

## 1.2.1 (Nov 3, 2026, in the Connect IQ store)
The Nov 3 rounds, newest first.
The circle's dotted arc is now a full clockwise ring of 36 dots from 12 o'clock: the first dot lights at any value above 0, 100% closes the ring, for every reading that uses it. The readings' units move to the small type so the ring clears them, and 10,000 steps or more read "12.3" over "K STEPS".

The circle's Temperature becomes Weather now, after Solar Frontier: this hour's weather picture from the forecast (night versions after sunset) over the temperature; with a forecast over 2 hours old it falls back to the temperature alone. The dotted arc shows the highest rain chance of the next 3 hours (empty at 0%, full at 100%). About 0.4 kB of code in all, no new memory held.

No past times: heavy rain already falling says when it eases ("UNTIL ~18:00") instead of "FROM ~16:00"; the heaviest hour, the snow-line rain and the night's coolest hour say NOW when they have begun; and any coming event that rounds to a time already past reads SOON.

Memory fix after the simulator's out-of-memory stop on a background update: the second time zone is dropped, the menu texts are one string resource per setting loaded only while the menu is open, the packing tables are byte arrays, and the face frees fonts and old data before storing a new forecast (or skips storing it when memory is short).

The wrist raise now adds one more fact under line 2 instead of replacing both lines with model jargon, and no number or time repeats on the same screen (a new check enforces it across every message). Hourly rain onsets say when the rain will have started ("BY 16:00", with "NOT BEFORE 15:00" on a wrist raise) and keep the big rain icon, and totals state their period ("ABOUT 4 MM" for a shower that ends, "9 MM IN 12H" when it does not, "IN THE NEXT 6H" for large totals). Air quality and dust now say when they ease, from a 12-hour CAMS forecast, the raise line gives the reading behind the index, and a new setting picks the European or US index. The bar keeps its glyph and shows its value on the right; the act-now block runs edge to edge. The circle gains pressure, steps against the goal, intensity minutes today and this week, stress and solar intensity.

## Earlier (before 1.2.1)
The first versions.
- **Context, revision 2.** The tiers are act now, light, rain within 2 h, worth adapting, and Quiet. Every message is checked against the data before ranking, with:
  - honest timing: minutes only where the forecast is native 15-minute data;
  - urgency that fades as the forecast ages, then "OLD";
  - hysteresis for gusts and heat;
  - a cooldown for advisories that stay unchanged;
  - a Quiet schedule by time of day.
- **New compared with Solar Frontier's Context:** rising wind, dry heat (air temperature or heat index), cold (wind chill), rain and snow totals, freezing fog, snow line (where the model gives one), temperature drop with a wind shift, frost, hot nights, dawn, morning briefing, tomorrow, moon below the horizon, offline barometer while still, and stale-forecast notices.
- **Forecast age** in the top line ("12 MIN AGO") or the reason there is none.
- **Your own circle and bar**, never Context: 10 options each.
- **Act now inverts the clock**, with the bar drawn inside the white block.
- **On-watch settings** (6, including a dark or light theme) in one small Solar Frontier-style view, and the same settings in the Garmin Connect app.
- **Layout:** the forecast's age heads the Signal's text column, the Signal sits level with the circle, the bar is centred under the time with its glyph (or value, on a wrist raise) to its left, and lines 1 and 2 sit lower with more room between them. The Signal block sits 5 px lower, near the time. The age text stops before the circle's bezel; "NO NEW DATA" is now "NO UPDATE", and two long second lines are shorter ("NO DRY SPELL 12H", "WATCH STILL 3H"). The date circle shows the weekday and the day; the arc gives the month.
- **Weather update:** every 5, 10, 15, 20, 30 (default), 45, 60 or 90 minutes, or every 2 hours.
- **Lighter forecast in memory:** the hourly series are packed four to an array, air quality is stored apart, and the old forecast is dropped before a new one is written.
- **Checks without the SDK:** parser, lint, the engine transpiled and run on the simulation cases and on 80,000 random cases.
