# Handoff — the storm-delta map (what a storm changed, city and watershed)

_Written 2026-10-03 by the cloud session, after the Oct 1–2 storm. For whoever builds the map, local or cloud.
It turns the "Flood anatomy, per event" row of [`IDEAS.md`](IDEAS.md) into a concrete layer on the water map
(`app/index.html`, `app/map.js`), fed by a new deterministic tool. Rules in [`AGENTS.md`](AGENTS.md) apply: raw
before interpretation, missing is never zero, no color that reads as a verdict about a place, no forecast._

## 0. The picture in one minute

The map today shows **state**: the latest reading at each gauge, well and lake. The storm-delta map shows
**change over a storm window**: how much rain fell at each gauge, how far each creek and river rose above where it
started, how that peak ranks in the station's own record, what the springs and wells did, and what the lakes
gained. Every symbol is a before/after pair from data already on file. The Oct 1–2, 2026 storm is the first
case, and the numbers below are its worked example.

What the Oct 1–2 case looks like in words (every figure from the record on 2026-10-03):

- Rain fell on the upper Llano (7–8 in at Junction), not on Austin (city median 1.5 in).
- Paved Austin creeks spiked and emptied within hours (Shoal 0 → 541 cfs, Walnut 0 → 650); limestone creeks
  barely moved (Barton at Loop 360 0 → 0.1; Bull Creek 0 → 14.9, back to 0.45 by morning).
- The Llano near Junction peaked at 35,000 cfs, the top 0.1% of daily means since 1915 but a tenth of the 2018 record.
- Springs: Barton 16.5 → 26.5 cfs (still the 17th percentile of its record); Comal did not respond (136 cfs, falling).
- Aquifer: J-17 jumped 1.7 ft in a day to 640.07; the 36 EAA wells reporting had a median 7-day change of 0.05 ft.
- Lakes: Travis +0.2 ft so far; ~16,600 acre-ft had passed Llano by Thursday morning with the pulse still running.

## 1. What already exists (nothing here needs a new source)

| Need | Where it is | Notes |
|---|---|---|
| Rain per gauge, 1-week and 30-day accumulations | bundle `hydromet.sites[*].rain_in` (335 gauges) | From the LCRA Hydromet all-sites feed, captured daily. The feed's own accumulations; not recomputed. |
| 15-minute flow and stage before, during, after | `data/normalized/water.sqlite` tables `observations` (USGS, from the daily two-day captures) and `hydromet_readings` (City and LCRA priority sites) | Instantaneous values; daily means hide the peak. |
| Each station's whole daily-mean record | `data/history/<station>-00060-daily-mean.csv` (68 flow stations) | For ranking a peak against the station's own history. |
| Event thresholds | `data/model/<station>-event-ledger.json` → `event_definition.high_threshold` | P95 of the record; "crossed its threshold" is a defined event, not a judgment. |
| Springs | `eaa_springflow_daily` (Comal, San Marcos daily means) and USGS 08155500 (Barton Springs, 15-minute) | |
| Wells | `app/eaa.json` (`change_7d_ft`, `percentile_13mo`, zone, county); `app/groundwater.json` (TWDB, ft below surface) | EAA wells come from the detail pages since 2026-10-03. |
| Lakes | `reservoir_levels` (TWDB daily) and `hydromet_readings` param `lakelevel` (LCRA, 15-minute) | |
| Map | `app/map.js` layers `stations, wells, lakes, eaa, hydromet`; `BASES` USGS topo + hydro | Add a sixth layer; do not change the existing cards. |

## 2. Define the storm window deterministically

A storm is a window `[t0, t1]` chosen by a rule, never by hand:

- **Trigger:** any day on which at least 20% of Hydromet rain gauges in the region report ≥ 1.0 in in `rainfall1Day`
  (the feed's field), or any flow station crosses its ledger high threshold.
- **t0:** 24 h before the first trigger reading. **t1:** 72 h after the last gauge that crossed its threshold drops
  back below it, capped at 10 days. (Lakes lag; see §4 for the lake window.)
- **Baseline:** the last reading before t0 at each station ("start"). **Peak:** the maximum between t0 and t1, with
  its time. **Now:** the latest reading.
- The window is written to `data/model/storms/<yyyy-mm-dd>.json` with the rule that chose it and the readings that
  triggered it, so a reader can see why those dates. The Oct 1–2 window by this rule: t0 = 2026-09-30T12:00Z,
  trigger = Williamson at Jimmy Clay crossing 21 cfs at 2026-10-01T17:30Z (verify against the captures; the date
  in this handoff is from the session's probe, not from the tool).

## 3. Build `tools/storm_delta.py`

Stdlib only, deterministic, raw-first. Subcommands:

- `detect [--since YYYY-MM-DD]` → finds windows by the §2 rule from what is in sqlite; writes
  `data/model/storms/<date>.json`. Never overwrites an existing window file (a window is a record).
- `compute --storm <date>` → `app/storm-delta.json` with one block per storm and these per-site records:

```
rain:     {site: {agency, name, lat, lon, inches_window, inches_30d, source: 'hydromet feed accumulations'}}
flow:     {station: {name, lat, lon, start_cfs, peak_cfs, peak_at, now_cfs, ratio: peak/max(start, 0.1),
                     threshold_cfs, crossed: bool, hours_rain_to_peak, hours_peak_to_half,
                     rank: {percentile_of_daily_means, record_daily_mean, days_at_or_above, years_at_or_above, last_such_day},
                     response_class}}
springs:  {site: {start, peak, now, same_season_median, percentile_of_record}}
wells:    {site: {level_before, level_after, change_ft, zone, county, aquifer, days_between}}
lakes:    {lake: {elevation_t0, elevation_now, change_ft, percent_full_now, inflow_acre_ft_so_far (Llano at Llano, LCRA 2641, trapezoid over the window)}}
window:   {t0, t1, rule, triggered_by}
caveats:  [...]
```

`response_class` is a label on the *measurement*, from the ratio and the recession, never on a place:
`no response` (peak < 2× start and < 1 cfs), `flash` (ratio ≥ 10 and back below 2× start within 24 h),
`sustained` (ratio ≥ 10 and still above 2× start at t1), `modest` (everything else). Write the thresholds into
the JSON next to the class so the reader can disagree.

`rank` uses the daily-mean record and says so: an instantaneous peak compared with daily means is a conservative
comparison and the card must say "against daily means".

Tests (`tests/test_storm_delta.py`): a fixture window with three synthetic stations (flash, sustained, no
response) and one well pair; the window rule on a fixture feed; a station with no history gets `rank: null`, not
a number; `missing is never zero` (a station with no reading before t0 gets `start: null` and no ratio).

## 4. The map layer

Add layer `storm` to `app/map.js` (checkbox `l-storm`, off by default) reading `bundle.storm_delta` (publish it
through `publish_bundle.py` as an additive block, schema stays 1). One storm at a time, chosen in a small select
in the panel; default the newest.

Symbols, all from the record:

- **Rain gauges:** circle scaled by `inches_window` (sqrt scale, 0 to 8 in → 4 to 22 px), single sequential
  blue ramp. A gauge with no window total is drawn hollow, not small.
- **Flow stations:** triangle, size by `ratio` on a log scale, fill by `response_class` (four categorical colors
  from the dataviz palette, none of them red/green/yellow so it does not read as a swim verdict). A station that
  crossed its threshold gets a thin dark ring. Tooltip: `start → peak (time) → now; rank`.
- **Springs:** the three spring symbols get a small bar: start, peak, now, with the same-season median as a tick.
- **Wells:** diverging ramp on `change_ft` (brown falling, blue rising, white ±0.25 ft), capped at ±3 ft so two
  15-ft pumping artifacts do not own the scale; a well with `days_between > 10` is drawn hollow.
- **Lakes:** square with `change_ft` as text and the inflow volume on the Travis card.

Card for a flow station (plain words, every number with its time):

> Shoal Creek at W 12th: 0 cfs at 10-01 12:00 → 541 cfs at 10-01 19:50 → 47 cfs at 10-02 11:15. Peak is the
> 99.9th percentile of this station's daily means since 1983 (19 days in 13 years were as high; last 2025-07-05).
> Crossed its event threshold (29.8 cfs). Response: flash. Rain to peak: about 2 h at the nearest gauge.

A panel paragraph above the map states the window and the rule that chose it, and ends with the standing line:
"Changes at gauges, as the operators published them. Not a flood map, not a swim map, not a forecast."

## 5. Hypotheses the map may show, labeled as hypotheses

Show these in a collapsible "What this suggests" box, each with the readings it rests on, so a reader can
check them. They are not computed by the tool; they are text in `data/model/storms/<date>.json` under
`hypotheses`, written by whoever reviews the storm, with a date and initials.

For Oct 1–2, 2026:

1. One wet week on the upper Llano fills reservoirs more than it refills the Edwards. Rests on: Comal flat,
   Barton at the 17th percentile after the rise, recharge-zone wells −0.11 ft median, Llano volume.
2. J-17's one-day rise is pressure, not storage; the 10-day average that sets the critical-period stage was 639
   on Oct 2 (Stage 3). Rests on: J-17 daily highs Sep 18 – Oct 1.
3. Paved watersheds answer in hours and are dry in a day; limestone creeks answered only where the rain exceeded
   about 2 in. Rests on: the `response_class` column and the City rain gauges.
4. Travis will show its gain days after the storm. Rests on: 16,600 acre-ft past Llano by Oct 2 11:00Z with
   17,000 cfs still passing; the TWDB daily elevation is the thing to watch.

Each hypothesis gets a `check_by` date and a `status` (`open`, `held`, `failed`) that a later session fills in
from the record. That is the crowd-sourceable list Saul asked for on 2026-10-01, applied to storms.

## 6. Wire it into the day

- README chain: after `hydro_context.py`, add `python3 tools/storm_delta.py detect && python3 tools/storm_delta.py compute --all-open`.
- Routine (PART A): the same two commands; PART C gets one line: "storm window open since <t0>" or nothing.
- `publish_bundle.py`: additive `storm_delta` block; `CHANGELOG.md` entry; `hill-country-hydro-system.md` layer
  table gains the tool under L2.

## 7. Known gaps to state on the card, not hide

- The Hydromet rain accumulations are the feed's; the tool does not recompute them from the 15-minute records,
  so "window total" is `rainfall1Week` or `rainfall30Days`, whichever brackets the window, and the card says which.
- EAA rain gauges carry no data (door closed since 2026-10-01); Hill Country rain is LCRA only.
- Two Bexar artesian wells (BDT614, BDE608) showed +15 ft in 7 days on 2026-10-03; treat as pumping or data until checked.
- Stations without a daily history (the San Antonio River sites, the North Llano) rank as `null`.
- Everything after Sept 30 is provisional at every provider.

## 8. How extreme was it — the measures that answer "how bad" (added 2026-10-03 after Saul asked)

The response class and the daily-mean percentile say "unusual"; they do not by themselves say "catastrophic".
Four measures do, and three are already on file:

1. **Rank among annual maxima** (on file). For each station take the largest daily mean of every year in its
   record and rank this storm's peak among them: "the 3rd-largest year in 41". This is the number a reader
   understands. From the record as of 2026-10-03, July 2026 ranked: Guadalupe at Comfort #2 of 88 years
   (52,900 cfs daily mean on 07-16; record 74,200), Guadalupe at Kerrville #3 of 41 (29,400), Llano at Llano
   #7 of 88 (53,600), Pedernales near Johnson City #15 of 88, Llano near Junction #14 of 109. The Oct 1–2 storm,
   by contrast, is a top-year event at Junction and nowhere else. `compute` writes `annual_rank: {rank, years,
   record_daily_mean, record_year}` for every station with a history; the card shows it first.
2. **NWS flood category** (on file for the forecast gauges in `app/hazards-status.json`; 59 gauges carry an
   observed stage, a subset carry the action/minor/moderate/major thresholds). Compare peak stage to the
   thresholds: "crested 4.2 ft above major flood stage". Where a gauge has no thresholds, say so.
3. **Rate of rise** (on file for every 15-minute station from the day the daily captures began; for July 2026
   only the daily means are on file, which flatten a wall of water). Max stage change per 15 minutes and per
   hour inside the window, with its time. The Hydromet LCRA sites give this back to 1991 for the priority set.
4. **Instantaneous peaks for past floods** (not yet scraped). The USGS peak-flow file (annual instantaneous
   peaks per station, `nwis.waterdata.usgs.gov/nwis/peak`) is the missing scrape that lets a July-2026 peak be
   ranked against instantaneous peaks rather than daily means; it is small (one row per station per year) and
   belongs in `usgs_series_history.py`. Rain intensity (inches per hour) wants the LCRA 15-minute rain history,
   which the Hydromet tool can pull with `--params rain` for any rain site.

Two honest limits. The map is retrospective: it reconstructs, it does not warn. And for an event that happened
before the daily captures began, the 15-minute shape comes only from providers that keep it (USGS instantaneous
archive, Hydromet history), which the tool must fetch for the window on request rather than assume.

## 9. Checklist for whoever does this

- [ ] `storm_delta.py detect` finds the Oct 1–2 window from sqlite alone and writes its file with the triggering readings.
- [ ] `compute` reproduces the §0 numbers (Shoal 541 at 10-01T19:50Z; Llano near Junction 35,000; J-17 640.07; Travis +0.2) and the §8 July-2026 annual ranks (Comfort #2 of 88, Kerrville #3 of 41, Llano at Llano #7 of 88).
- [ ] Tests pass; `python3 -m unittest discover -s tests`.
- [ ] The map layer draws; a hollow symbol appears for a gauge with no window total; no red/green/yellow anywhere in the layer.
- [ ] The card text never says "safe", "dangerous", "flood" as a verdict, or "will".
- [ ] Bundle still schema 1; the swim lens's tests still pass with the new block present.
- [ ] Hypotheses box shows the four above with their readings and `check_by` dates.
