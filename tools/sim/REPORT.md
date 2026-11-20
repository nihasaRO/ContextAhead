# Context judgment: verified facts, simulation and decisions

Nov 2, 2026. Review of `CONTEXT_JUDGMENT_AUDIT.md` against `CONTEXT.md` (Draft 1) and the Solar Frontier 1.9.3 code. No watch code was changed. The simulation (`engine.py`, `scenarios.py`, `run.py`) runs both rule sets side by side, and `results.md` holds every before/after row with the reasons behind each choice.

## 1. What is actually true (checked, not assumed)

### Provider and code path

The code uses **Open-Meteo**, not OpenWeather. `WeatherService.mc` calls `api.open-meteo.com/v1/forecast` and, only when an air or pollen slot is shown, `air-quality-api.open-meteo.com/v1/air-quality`. There is no OpenWeather call anywhere in the source.

Solar Frontier also has Garmin's own weather (`Toybox.Weather`), and that is its default source. Garmin weather has no CAPE, visibility, gust series or 15-minute data. So most of Context needs Open-Meteo, and the new face should make it the only weather source.

| Item | Fact | Source |
| --- | --- | --- |
| Request | current, hourly 25 h, daily 2 days, `minutely_15` 8 steps (2 h); unix time, `timezone=auto`, wind in m/s | `WeatherService.mc` |
| Refresh | user setting 5-60 min (default 60). After a 5xx error it retries every 5 min. Without a phone (-104) or position (-1) it keeps the normal interval | `SolarFrontierView.mc` `manageBackground` |
| Platform floor | Temporal events cannot run less than 5 min apart | Garmin `Toybox.Background` docs |
| Expiry in the code | current values: 2 intervals + 10 min; forecasts: 12 h, same day | Solar Frontier README |
| Fetch time | stored (`mResult[0]`), so "12 MIN AGO" means *last successful fetch*. The model run time is not in the response | code |
| Location | `Position.getInfo()` if the fix is under 2 h old; else Garmin's weather observation position; else the last activity position. Saved only when it moves more than 0.05° (about 5 km). **No timestamp is stored**, so the background fetch cannot know how old its position is | `updateSun`, `rememberLocation` |
| Pressure, live | `Activity.getActivityInfo().meanSeaLevelPressure`, or ambient pressure as a fallback | code |
| Pressure, history | `SensorHistory.getPressureHistory`: Pascals, kept up to the last power cycle, sample spacing "device dependent". The docs do not say whether it is ambient or sea-level pressure; Solar Frontier's tests found ambient (station) pressure | Garmin `SensorHistory` docs, companion brief |
| Elevation history | `getElevationHistory` exists (API 3.3.0). That makes the "was the watch climbing?" gate possible on the watch | Garmin docs |

### Live API test

I sent real requests on Nov 2, 2026 from the in-app browser, to 9 places: Bucharest, Omu (Bucegi), Munich, Lyon, Denver, Helsinki, Delhi, Nairobi and Alice Springs.

**Present everywhere:** all core hourly fields, including temperature, humidity, apparent temperature, code, probability, rain, showers, snowfall, CAPE, gusts, wind direction, visibility, UV, cloud, `is_day` and `sunshine_duration`.

**Missing in some places:**

- `lifted_index` and `freezing_level_height`: **null in Helsinki** (the Nordic model).
- `snowfall_height`: present in Bucharest, Omu, Munich and Lyon; **null in Denver, Helsinki, Delhi, Nairobi and Alice Springs**.
- `lightning_potential`: only in Munich and Lyon.

**Moon:** daily `moonrise`, `moonset` and `moon_phase` work. They are null on a day with no moonrise, which is correct.

**Air quality:**

- `european_aqi`, `us_aqi` and `dust` are returned for all three places tested (Bucharest, Denver, Delhi).
- Pollen is **null outside Europe**, and **0 in Bucharest out of season**. A real zero and "no data" are different things.
- The air-quality data is hourly.

**15-minute data:** Open-Meteo's documentation says native 15-minute data comes from HRRR (North America) and ICON-D2 / AROME (Central Europe), and that everything else is interpolated from hourly data. The live test agrees. Between whole hours, Bucharest's 15-minute temperature lies on a straight line 91% of the time, against 45% in Munich and 48% in Denver. This is a heuristic check, not a model label.

**Time conventions from the docs:**

- `precipitation_probability`: the preceding hour, more than 0.1 mm, from a 0.25° (about 27 km) ensemble.
- `wind_gusts_10m` hourly: the **maximum of the preceding hour**.
- `weather_code`: an **instant**.
- Thunderstorm codes: "96 and 99 are only reported by models with an explicit hail forecast, such as DWD ICON or UKMO. **All other models derive thunderstorms from instability parameters** and report codes 95 and 97."

## 2. Simulation results

Draft 1 is v1; the revision is v2. There are 50 scenario groups and 85 wrist raises: all 31 audit cases (adapted to real coordinates) plus sequences for hysteresis, cooldown, fetch ageing, event identity, DST and text widths.

| Acceptance gate | v1 | v2 |
| --- | --- | --- |
| No act-now storm from CAPE alone or a climb | fail | pass |
| No sub-hour rain timing from hourly data | fail (8 raises) | pass |
| No DRY for gaps under 90 min | fail | pass |
| No warning from missing or old data | fail | pass |
| Right AQI scale and real driving pollutant | fail | pass |
| Stable across small fluctuations (case 34) | fail (2 flips) | pass |
| Meaningful Quiet over a calm day | pass | pass |
| Offline fallback is astronomy, watch data or a reason | fail ("CALM DRY 12H+" with no data) | pass |
| Every chosen text fits the panel, measured with the real fonts | fail (3) | pass |
| Scenario checks | 9 of 31 | 31 of 31 |

**Read this with care.** The v2 checks encode the decisions in this report, so "31 of 31" proves the logic does what we decided, not that the decisions are right meteorologically. The next proof is a replay of archived real forecasts (section 6).

### Before and after, the examples that matter most

| Case | Draft 1 shows | Revised shows | Why |
| --- | --- | --- | --- |
| 05 Mountain climb, 600 m in 3 h | **STORM / SIGNS**, BARO ▼72.0 IN 3H | CALM / DRY 12H+ | The pressure fall is altitude; the elevation history proves it |
| 03 CAPE 1800, no storm code | STORM / ~12:00 | CALM | Instability is not a storm forecast |
| 04 Storm code next hour, gusts 68 | **GUST / 68 KMH**, GUST F8 | **STORM / ~1 H**, GUSTS TO 68 KMH | The storm explains the gust; one message |
| 09 Bucharest, rain 15-16 h | RAIN / ~45 MIN | RAIN / ~15:00 | Bucharest only has hourly data |
| 43 Bucharest, rain in 100 min | RAIN / ~100 MIN, 70% ABOUT **0 MM** | RAIN / ~15:00, 70% ABOUT 4 MM | Draft 1 counted only the 15-minute part of the amount |
| 14 Munich, rain in 15 min, sunset in 25 | LIGHT / 0:25 LEFT | RAIN / ~15 MIN, line 2 SUNSET 18:15 | Native data; the rain is sooner and changes the decision |
| 14b The same in Bucharest | LIGHT | LIGHT | Hourly data cannot resolve 15 minutes |
| 11 Drizzle, 15% probability | RAIN / ~75 MIN, 15% ABOUT 0 MM | CALM | Negligible and not confident |
| 12 Showers with a 20-min break | DRY / ~30 MIN | RAIN / +5 MM STILL RAINING | No false dry spell |
| 31 Alice Springs, 43° at 8% humidity | HEAT / **FEELS 39°** (tier 5) | HEAT / **AIR 43°** (act now) | The heat index reads below air temperature in dry heat |
| 21b Gusts 70, data 3 h old | **GUST** act-now | GUST tier 5 | Urgency needs fresh data |
| 42 The same data ageing: 30 / 100 / 250 / 800 min | act-now ×3, then BARO | act-now, tier 5, **GUST / 4H OLD, FCST 70 KMH**, then BARO | Urgency fades with the data; Quiet never says CALM over an old warning |
| 32b Light snow + gusts 60, visibility 5 km | SNOW / GUST 60 **BLOWING SNOW** (act now) | SNOW / WINDY (tier 5) | Not blowing snow |
| 17 EU AQI 75 from ozone | AIR / POOR, **PM10 20** | AIR / POOR, EU AQI 75 OZONE | Real driver, right scale |
| 22 Offline, no position | **CALM / DRY 12H+** | NO FIX / NO GPS | Never claim calm without data |
| 34 Gusts 66, 62, 59, 57, 63 | act, act, t5, t5, **act** | act, act, act, t5, t5 | Enter at 65, leave under 58 |
| 23 UV 9 for six hours | UV for 11 raises in a row | UV, then Quiet, reminders at 12:00 and 14:00 | No day-long lock-out |
| 40 Winter, 17:30, rain tomorrow | NIGHT / LOW 0° | TMRW / RAIN 70%, FROM ~09:00 ~7 MM | Evening follows the sun, not 19:00; times come from hourly data |
| 27 6° evening cooling | FRONT / -6°, NW WIND, GUSTS TO 70 (invented) | CALM | Daily cooling, no change of air |

## 3. Where I disagree with the audit

1. **A thunderstorm code is not independent evidence.** Open-Meteo says most models derive codes 95/97 from instability, the same physics as CAPE. I agree the code beats CAPE alone. But I classify it as *derived*, not direct, and I add a condition for act-now: at least 0.5 mm of rain forecast in that hour. A code with no rain stays tier 5.
2. **Position is available to the face.** The audit says watch-face code cannot use `Position` directly. `Position.getInfo()` is documented (with the Positioning permission), and Solar Frontier calls it from the face and shipped that way. What a face cannot do is start GPS or subscribe to location events. The real gap is that **the saved location has no timestamp**, so its age is unknown. That needs one more stored number.
3. **The snow line should not be paused everywhere.** The live test shows `snowfall_height` is returned for Bucharest and the Bucegi, and is null in North America and the Nordics. So use it where present, compare it with the watch's altitude, and give no message where it is null (case 33b). Never infer it from the freezing level.
4. **Act-now data age of 60 minutes is too tight at a 60-minute refresh.** A fetch at hour N would expire just before the fetch at N+1, so every warning would blink off for a few minutes each hour. I set 90 minutes, and recommend a 30-minute default refresh for this face. That is 48 calls a day per watch, far under the free limit; the battery cost still needs measuring.
5. **Pollen thresholds do exist in the code.** Solar Frontier already uses species-specific grain thresholds (trees vs grasses vs mugwort), so "no thresholds" is not accurate. But I could not find their source. So: opt-in, off by default, until the thresholds are sourced, as the audit says.
6. **Ambient heat (A1) is not a new message.** One HEAT family uses an *effective heat*: the higher of air temperature and heat index. That gives one message, one rule, and it fixes dry heat (cases 01, 31) without a seventh heat variant.
7. **The barometer still deserves one warning.** I agree with removing "CHANGE COMING" while online. But with no phone, the watch's own pressure is the only weather evidence a hiker has. So I keep tier 5 `BARO / FALLING` **offline only**: 4+ hPa in 3 h, with the elevation history showing under 30 m of movement and no gap over 30 min (case 06b). When the gate fails it gives the reason ("watch moved 600 m in height").
8. **Wind rising (A2): a 3-hour window, not 2.** Hourly gusts are hourly maxima, so 2 hours is only two samples. Three is steadier.
9. **The Sunset label: keep the word LIGHT.** "SUNSET" does not fit the Signal slot: it is 73 px against 67. So the Signal stays `LIGHT / 0:25 LEFT`, line 1 says `SUNSET 17:40` and line 2 `CIVIL DUSK 18:12`. The meaning becomes explicit without a new word.

## 4. Decision sheet

### Rules

| Proposal | Decision | Value used |
| --- | --- | --- |
| Data age per tier | **Adjust** | act-now 90, rain within 2 h 90, tier 5 240, Quiet 720, air quality 180 (min) |
| Forecast point far from the watch | **Accept** | over 25 km: no act-now and no 2-hour rain claims; needs the location timestamp |
| Precision follows the data | **Accept** | native boxes (HRRR, Central Europe) round to 15 min; elsewhere to the hour, and no "MIN" countdowns |
| Hysteresis | **Accept** | gusts 65/58 (act now), 50/45 (tier 5); heat 40/38, 33/31 |
| Minimum dry gap | **Accept** | 90 min |
| Rain onset quality gate | **Accept** | at least 0.5 mm in the spell and probability 30%+ |
| Event identity | **Accept** | family + local day/hour; a re-fetch keeps it (case 43) |
| One message per family, ranking inside a tier | **Accept** | fixed family order: storm, ice, snow, fog, cold, heat, rain, temp, gust, air... |
| Composition | **Accept** | storm absorbs gusts; TEMP absorbs rising wind; rain shows the snow line or sunset in line 2 |
| Cross-tier exception (rain beats sunset) | **Adjust** | only with native 15-min data and onset within 30 min |
| Cooldown for persistent tier 5 | **Accept** | after 60 min unchanged, yields to Quiet; a 2-hour reminder; never for act-now |
| Quiet as a scheduler | **Accept** | dawn, then TODAY (once a day), day (sunny, gap, calm), after sunset TMRW, night MOON/NIGHT; offline: baro, then sun, then the reason |
| Stale-forecast Quiet (new) | **Add** | after a hazard ages out, show "GUST / 4H OLD" instead of CALM |

### The 35 existing messages

| # | Message | Decision | Notes |
| --- | --- | --- | --- |
| 01 | GUST act now | **Accept** | km/h only, 65/58, the hourly maximum read correctly |
| 02 | STORM / SIGNS | **Adjust** | code + rain, within 1 h; pressure supports only; CAPE goes to evidence |
| 03 | FOG act now | **Adjust** | under 400 m **and** a fog code; 400-1000 m with a code is tier 5; visibility alone never |
| 04 | ICE | **Accept** | NOW only when the current code says so; otherwise ~1 H; tier 5 up to 6 h |
| 05 | HEAT act now | **Adjust** | effective heat 40/38; one HEAT family |
| 06 | COLD | **Accept** | wind chill only where defined (T ≤ 10°, wind ≥ 4.8 km/h); "MILDER" only when the data shows it |
| 07 | SNOW + gust | **Accept** | act-now needs 1+ cm/h, gusts 56+, and visibility under 1 km or a heavy-snow code; else SNOW / WINDY |
| 08 | AIR extreme | **Accept** | EU AQI above 100 / US AQI 301+, the driver named, scale by region |
| 09, 13 | LIGHT | **Accept, adjusted** | SUNSET and CIVIL DUSK labels; polar handled |
| 10 | RAIN/SNOW onset | **Accept** | quality gate and real precision |
| 11 | DRY | **Accept** | 90-min gap |
| 12 | HEAVY | **Adjust** | 7.6 mm/h (0.3 in/h, a commonly cited heavy-rain rate; I could not open the AMS glossary to confirm) |
| 14 | STORM tier 5 | **Adjust** | code within 6 h; no CAPE-only path |
| 15 | GUST tier 5 | **Accept** | 50/45 km/h |
| 16 | HEAT tier 5 | **Adjust** | 33/31 effective, daytime, with cooldown (case 44: shown, then Quiet) |
| 17 | UV | **Accept** | UV 8+ now or within 2 h; cooldown |
| 18 | AIR poor | **Accept** | EU 60+ / US 151+ |
| 19 | DUST | **Accept** | "DUST / HIGH", 100 µg/m³ as a starting value; folded into AIR when AIR is shown |
| 20 | POLLEN | **Accept (opt-in)** | off by default until the thresholds are sourced |
| 21 | SNOW LINE | **Adjust** | `snowfall_height` where returned, within 300 m above you |
| 22 | FRONT | **Adjust** | rename to TEMP; needs a 45°+ wind shift or a 15+ km/h gust rise |
| 23 | FROST | **Accept** | evening to dawn; "CLEAR LIGHT WIND" only when the data supports it; skipped after a cold day |
| 24 | HOT NIGHT | **Accept** | Quiet at 20°+, tier 5 at 25°+ |
| 25 | BARO tier 5 | **Adjust** | offline only, and only when the watch was stationary (see disagreement 7) |
| 26 | TODAY | **Accept** | once a day; "DRY 12H+", never "ALL DAY" |
| 27 | CLEAR ALL DAY | **Adjust** | SUNNY / ~8H SUN, only with cloud under 40% and no rain spell |
| 28 | DRY GAP | **Accept** | 90-240 min |
| 29 | CALM | **Accept** | wet totals go to RAIN, never to CALM |
| 30 | TMRW | **Accept** | from sunset (not before 17:00); times only from tomorrow's hourly data |
| 31 | DARK / NO MOON | **Adjust** | MOON / BELOW, cloud under 30%, from Open-Meteo moonrise/moonset |
| 32 | NIGHT | **Accept** | lowest temperature and its time, first light |
| 33 | BARO quiet | **Accept** | only with a stationary record; otherwise the reason |
| 34 | SUN offline | **Accept** | needs a valid position; otherwise NO FIX + reason |
| 35 | POLAR | **Accept** | NO SUNRISE TODAY / NO SUNSET TODAY |

### The six additions

| ID | Proposal | Decision | Result in the simulation |
| --- | --- | --- | --- |
| A1 | Ambient heat | **Merge into HEAT** | case 31 becomes act-now `AIR 43°`; case 01 tier 5 `AIR 39°` |
| A2 | Wind rising | **Accept, adjusted** | +20 km/h within 3 h, reaching 40+; case 07 fires, case 08 does not |
| A3 | Rain total | **Accept** | 20+ mm in 6 h, tier 5; heat outranks it in case 29 (Delhi, feels 40°) |
| A4 | Freezing fog | **Merge into FOG** | code 48 or a fog code at ≤0°; "FREEZING FOG -2°" in line 1 |
| A5 | Snow total | **Accept** | 5+ cm in 6 h; case 16 `SNOW / +7 CM` |
| A6 | Dawn | **Accept** | Quiet, from 75 min before civil dawn; case 02 at 04:40 |

## 5. Text on the panel

Every v2 message was measured with the face's real bitmap fonts:

| Slot | Limit |
| --- | --- |
| Signal word | 67 px |
| Detail | 66 px |
| Line 1 | 168 px |
| Line 2 | 134 px |

Findings from the measurements:

- **The small font has no comma.** All copy avoids it ("CLEAR LIGHT WIND").
- **Rejected words:** "SUNSET" (73 px), "COLDER" (71 px), "NO DATA" (82 px) and "OFFLINE" (76 px) are too wide for the Signal. That is why the copy uses LIGHT, TEMP and NO FIX.
- **Draft 1 overflowed three times:** "POLLEN" (70 px) and "DARK 18:47 FIRST 07:08" (149 px) twice.

## 6. What this does not prove yet, and what comes next

1. **Real-weather replay.** The scenarios are synthetic. Next I'd replay archived forecasts from Open-Meteo's historical forecast data for Bucharest, the Bucegi, Munich and Denver. That would show how often each message fires in a real July, November and January. The aim: about how many raises per day are not Quiet, and how often act-now fires per month. That is where thresholds like HEAT 33 and GUST 50 get tuned.
2. **On the watch:**
   - Check that `Gregorian.info` on a Moment applies the device's DST rules (case 20 shows why it matters).
   - Measure whether the pressure-history samples really are ambient, and how far apart they are.
   - Store a timestamp with the location.
3. **Memory.** The revision adds state: per-family hysteresis levels, the last shown event, cooldown records, and the location age. My estimate is 1-1.5 kB of code and under 0.3 kB of data. It is an estimate, to be measured in the skeleton build.
4. **Then** `CONTEXT.md` revision 2, after your approval of this sheet. The Draft 1 file stays for comparison.

## Files

| File | What it is |
| --- | --- |
| `data.py` | Inputs with Open-Meteo's time conventions; native-15 boxes, heat index, wind chill |
| `engine.py` | Both rule sets; each candidate and rejection carries its reason |
| `scenarios.py` | The 50 scenario groups |
| `run.py` | Gates, font widths, and writes `results.md` |
| `results.md` | Every raise, v1 against v2, with candidates and rejections |

Run it with:

    python3 run.py

The font check needs the mock-up tools: set `CF_DIR` to the folder with `cf.py`, `SF_TOOLS` to Solar Frontier's `tools/` and `SAIRA_FONT_DIR` to the fonts. Without them it is skipped and the rest still runs.
