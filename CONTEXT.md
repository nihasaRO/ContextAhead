# Context: rules (revision 2)

Nov 3, 2026. This is what `source/Context.mc` does. It replaces Draft 1 (Nov 2), which is kept in `tools/sim/` for comparison together with the audit decisions (`tools/sim/REPORT.md`). Thresholds are starting values chosen in the simulation. They are not official warning criteria, and the face never presents them as warnings.

## How a message is chosen

1. **Checks before ranking.** A message exists only when the data it needs is present and young enough. The limits, in minutes since the last successful fetch:

   | Tier | Max age |
   | --- | --- |
   | Act now | 90 |
   | Rain within 2 h | 90 |
   | Worth adapting | 240 |
   | Quiet | 720 |
   | Air quality | 180 |

   When the forecast point is more than 25 km from the watch's newest position, the act-now tier and the 2-hour rain timing are off.
2. **Ranking.** The tier decides first, then a fixed family order:

   > storm, ice, snow, fog, cold, heat, rain, temperature, gust, air, frost, UV, dust, pollen, hot night, barometer

   Inside the same tier and family, the stronger event wins, then the sooner one.
3. **One exception.** Rain within 30 minutes beats the last-30-minutes sunset countdown. This applies only where the model has native 15-minute data, and the sunset time moves to line 2.
4. **Composition.**
   - A storm absorbs the gusts it brings ("GUSTS TO 68 KMH").
   - A temperature drop shows its gusts in line 2.
   - Rain shows a nearby snow line in line 2.
5. **Hysteresis.**

   | Value | Act now: enter / leave | Worth adapting: enter / leave |
   | --- | --- | --- |
   | Gusts | 65 / 58 km/h | 50 / 45 km/h |
   | Effective heat | 40 / 38 °C | 33 / 31 °C |
6. **Cooldown.** Some worth-adapting messages repeat all day: UV, air, dust, pollen, heat, and steady strong gusts. After one hour with no material change, such a message gives way to Quiet. It comes back once two hours have passed since it was last on screen. A material change is 3 units of its severity (for example 3 °C, 3 km/h or 3 AQI). Act-now messages never give way.
7. **Hold.** A message stays for up to 15 minutes against a comparable one, so the face does not flip between them.
8. **Stale.** When a hazard drops out only because the data aged, the face says so, for example "GUST / 4H OLD, FCST 70 KMH". It never says CALM over an old warning.

## Precision

Open-Meteo has native 15-minute data only from HRRR (conterminous US) and ICON-D2 / AROME (Central Europe). Everywhere else, the 15-minute values are hourly data spread out. So the face uses minute countdowns ("~45 MIN") only inside those two areas. Elsewhere it gives hour-level times ("~15:00").

The two areas are approximate boxes, set on purpose a little inside the real domains.

The data follows Open-Meteo's own time conventions:

- **Rain and gusts:** hourly values describe the hour before their time stamp.
- **Weather codes:** these are instants.
- **Rain chance:** the hourly ensemble chance of more than 0.1 mm in that hour.

## Messages

| Tier | Signal | When |
| --- | --- | --- |
| 1 act now | GUST / 72 KMH | gusts 65+ km/h now or within the hour (leave under 58) |
| 1 | STORM / NOW, ~1 H | thunderstorm code (95-99) within the hour with 0.5+ mm of rain; otherwise tier 5 up to 6 h ahead. CAPE alone never makes a storm |
| 1 | FOG / 0.3 KM | a fog code (45, 48) with visibility under 400 m; with a code but more visibility: tier 5; "FREEZING" at code 48 or 0° and below. Visibility alone never makes fog |
| 1 | ICE / NOW, ~1 H | freezing rain or drizzle code (56, 57, 66, 67) now or within the hour; tier 5 up to 6 h |
| 1 | HEAT / FEELS 42°, AIR 43° | effective heat (the higher of air temperature and NWS heat index) 40+ °C (leave under 38) |
| 1 | COLD / FEELS -34° | wind chill -28 °C or lower (only where wind chill is defined: 10 °C or colder, wind 4.8+ km/h) |
| 1 | SNOW / GUST 70 | snow 1+ cm/h, gusts 56+ km/h, and visibility under 1 km or a heavy-snow code; less: SNOW / WINDY, tier 5 |
| 1 | AIR / EXTREME, HAZARD | EU AQI over 100 (Europe) or US AQI 301+ (elsewhere), with the pollutant that drives it |
| 2 | LIGHT / 0:25 LEFT | under 30 min to sunset; line 1 SUNSET, line 2 CIVIL DUSK |
| 3 | RAIN, SNOW / ~45 MIN or ~15:00 | a spell of 0.5+ mm with a chance of 30%+ starting within 2 h; line 2 when it stops, or the sunset when it lands before dark |
| 3 | DRY / ~30 MIN | the current rain stops within 2 h and stays away for 90+ min |
| 3 | RAIN / HEAVY | 7.6+ mm in an hour within 2 h |
| 4 | LIGHT / 1:20 LEFT | under 2 h to sunset |
| 5 | WIND / RISING | gusts rise by 20+ km/h within 3 h to 40+ |
| 5 | GUST / 55 KMH | gusts 50+ km/h (leave under 45) |
| 5 | HEAT | effective heat 33+ °C (leave under 31), daytime only |
| 5 | RAIN / +24 MM | 20+ mm in the next 6 h |
| 5 | SNOW / +7 CM | 5+ cm in the next 6 h |
| 5 | SNOW / ▲200 M | the model's snowfall height is less than 300 m above you, with rain or snow within 6 h (Europe models only; no inference from the freezing level) |
| 5 | TEMP / -8° ~15:00 | a fall of 5+ °C within 3 h with a wind shift of 45°+ or gusts rising 15+ km/h (not the evening cooling) |
| 5 | UV / VERY HIGH, EXTREME | UV 8+ now or within 2 h, in daylight |
| 5 | AIR / POOR, UNHEALTHY | EU AQI 60+ or US AQI 151+ |
| 5 | DUST / HIGH | dust 100+ µg/m³ without another air message |
| 5 | POLLEN / RAGWEED | opt-in (Europe): the highest type at the HIGH band from Solar Frontier's grain thresholds |
| 5 | FROST / TONIGHT | tonight's low 0 °C or below after a day of 5 °C or more; "CLEAR LIGHT WIND" only when the data says so |
| 5 | HOT / MIN 26° | the night stays at 25 °C or more (20-24 °C: a Quiet message) |
| 5 | BARO / FALLING | offline only: 4+ hPa in 3 h while the watch stayed within 30 m of height, with no gap over an hour |

### Quiet, by time of day

| When | Signal |
| --- | --- |
| Polar | POLAR / DAY or NIGHT |
| No usable forecast | BARO (only while still), else SUN, else NO FIX with the reason |
| 75 min before civil dawn | DAWN / ~40 MIN |
| First wrist raise of the morning | TODAY / HI 24° (once a day) |
| From sunset (not before 17:00) to 23:00 | HOT (a warm night), else TMRW with tomorrow's hourly times |
| Night | MOON / BELOW (clear sky, moon down), else NIGHT / LOW 14° |
| Day | RAIN / +5 MM (still raining), DRY / ~2H GAP (90-240 min dry), SUNNY / ~8H SUN (sunshine still to come and cloud under 40%), CALM / DRY 12H+ |

## Screen rules (Nov 3, revision 3)

- **One job per slot.** The Signal word says what, its detail when or how strong, line 1 how much or how likely, line 2 what happens next. No number or time appears twice on one screen (`tools/check/dups.cjs` checks every message).
- **A wrist raise adds, never replaces.** Lines 1 and 2 stay; line 2 moves up 4 px and one more fact appears under it in the small type: when it is heaviest, the peak gust, the wind direction, tonight's low, the reading behind an air index, the visibility in dust, or how the timing is known ("HOURLY FORECAST", "15-MIN FORECAST"). A message with nothing new to add shows no extra line.
- **Hourly rain onsets say "BY".** An hourly forecast only knows that rain falls somewhere in an hour, so the Signal says when it will have started ("BY 16:00") and a wrist raise adds the other end ("NOT BEFORE 15:00"). A clock window like "15-16:00" read as a one-hour shower, and a midpoint like "~15:30" would fake precision. Minute countdowns stay for native 15-minute data.
- **Totals say their period.** A shower that ends: "ABOUT 4 MM" (the whole shower, with "THEN DRY ~17:00"). No end in sight: "9 MM IN 12H" with "NO DRY BREAK". Large totals: "+24 MM" with "IN THE NEXT 6H".
- **Air and dust say when they ease**, from a 12-hour CAMS forecast of the index and dust ("BETTER ~22:00", "EASES ~20:00"). The index is European or US by setting (Auto: European inside Europe).

## Added in 1.4

- **Yesterday:** the app keeps each day's forecast high and rain total from that day's last fetch; the next day they are "yesterday". The morning briefing's raise line compares the highs (3 °C or more apart), else shows yesterday's rain (10 mm or more), else tonight's low. Calm and sunny days show yesterday's rain on a raise.
- **No storm signs from the watch's barometer:** Garmin's own Storm Alert (Notifications & Alerts > System Alerts > Barometer) watches the pressure fall, vibrates, and lets the wearer set the rate; a watch face can do none of that, so Context leaves it to the watch.
- **Snow line everywhere:** where `snowfall_height` is missing, the background estimates it as `freezing_level_height` minus 300 m and marks the hour (bit 30 of the third packed series). The face shows "~2100 M" and, on a raise, "0° LINE 2400 M". This reverses revision 2's "no inference from the freezing level", at the wearer's request, with the estimate always marked.

## Added in 1.5

- **Icy patches (F_ICE, tier 5, id 17).** Wet hours (0.3 mm or more) from the forecast, plus the last wet hour the face remembers (the app stores the fetch's first hour when it was wet; Context keeps past wet hours as the forecast ages). The first dry hour at 0 °C or below, now or in the next 6 hours, within 6 hours of the wet: "ICE / RISK" or its time. Wording is a risk, never a road state.
- **Steady wind (F_GUST, tier 5, id 84).** The lowest mean wind of the next 3 hours at 30 km/h or more, by day, when no gust message applies. Persistent.
- **Briefing raise order:** new snow (5 cm or more since yesterday: yesterday's `snowfall_sum` (daily slot 13), kept like the rain, plus today's minus what is still forecast to fall) > the 25° crossing on a 30° day > colder or warmer than yesterday > wet ground > tonight's low.
- **A smaller forecast:** 20 hours instead of 24 (16 after an out-of-memory reply). No rule looks further than 15 hours; tomorrow's rain seen from the evening reaches about mid-afternoon. `minutely_15` only inside the two native boxes, `freezing_level_height` only outside Central Europe.
- **Daily values after midnight:** when the forecast was fetched on an earlier day, daily slots 0 and 1 read its tomorrow (4 and 5), and today-only values (UV, sunshine, tomorrow, rain chance, rain and snow totals) are null.

## Not claimed

No official warnings. No lightning, route safety, flood risk, or measured visibility. Icy patches are a risk worked out from the rain and air temperature forecast, not measurements of the road. The forecast's age is always in the top line: "12 MIN AGO" means the last successful fetch, not the model's run time.
