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

Two scrapes are part of this build, not follow-ups (added 2026-10-03 after Saul's "add that to build"):

- **`tools/usgs_peaks.py`** — the USGS peak-flow file: one row per station per water year, the instantaneous
  annual peak with its date and gage height. Endpoint to try first:
  `https://nwis.waterdata.usgs.gov/nwis/peak?site_no=<station>&agency_cd=USGS&format=rdb` (tab-separated, `#`
  comment lines). USGS has been retiring legacy NWIS services; if this one answers with a retirement notice or
  a redirect, record that response raw and fall back to ranking against the 15-minute `continuous` collection
  of the OGC API fetched for the storm window only. Raw under `data/raw/usgs-peaks/`, one versioned gzip per
  station under `data/captures/usgs-peaks/` with a manifest, normalized to `data/history/<station>-peaks.csv`
  and a sqlite table `usgs_peaks(station, date, peak_cfs, gage_height_ft, qualifiers)`. Run it for the 68
  history-tier stations; Sundays in the routine. `compute` then writes `peak_rank: {rank, years, record_peak_cfs,
  record_date}` beside `annual_rank`, and the card prefers the instantaneous rank when it exists.
- **Hill Country rain history** through `hydromet.py`: add a `rainDaily` entry to `PRIORITY['LCRA']` for every
  LCRA rain site inside the Hill Country box (lat 29.9–30.9, lon −100.2 to −97.9 in the all-sites feed; about a
  hundred sites; a daily-rain window is under 1 KB gzipped) and pull it once in full. For intensity, `compute`
  fetches the 15-minute `rain` window that brackets a detected storm for the same sites, on demand, and keeps it
  under the same manifest; it never pulls 15-minute rain for all years. `rain_rank: {inches_window, days_on_record,
  rank_among_daily_totals}` joins the rain record on the card.

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

- README chain: after `hydro_context.py`, add `python3 tools/storm_delta.py detect && python3 tools/storm_delta.py compute --all-open`. Sundays add `python3 tools/usgs_peaks.py collect && python3 tools/usgs_peaks.py normalize`; the Hill Country `rainDaily` sites ride the existing `hydromet.py history --recent-only` line once they are in `PRIORITY`.
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
4. **Instantaneous peaks for past floods** (a build step in §3 since 2026-10-03). The USGS peak-flow file (annual instantaneous
   peaks per station, `nwis.waterdata.usgs.gov/nwis/peak`) is the missing scrape that lets a July-2026 peak be
   ranked against instantaneous peaks rather than daily means; it is small (one row per station per year) and
   belongs in `usgs_series_history.py`. Rain intensity (inches per hour) wants the LCRA 15-minute rain history,
   which the Hydromet tool can pull with `--params rain` for any rain site.

Two honest limits. The map is retrospective: it reconstructs, it does not warn. And for an event that happened
before the daily captures began, the 15-minute shape comes only from providers that keep it (USGS instantaneous
archive, Hydromet history), which the tool must fetch for the window on request rather than assume.

## 9. Checklist for whoever does this

- [x] `storm_delta.py detect` finds the Oct 1–2 window from sqlite alone and writes its file with the triggering readings.
- [ ] `compute` reproduces the §0 numbers (Shoal 541 at 10-01T19:50Z; Llano near Junction 35,000; J-17 640.07; Travis +0.2) and the §8 July-2026 annual ranks (Comfort #2 of 88, Kerrville #3 of 41, Llano at Llano #7 of 88).
- [x] Tests pass; `python3 -m unittest discover -s tests`.
- [x] The map layer draws; a hollow symbol appears for a gauge with no window total; no red/green/yellow anywhere in the layer.
- [x] The card text never says "safe", "dangerous", "flood" as a verdict, or "will".
- [x] Bundle still schema 1; the swim lens's tests still pass with the new block present.
- [x] Hypotheses box shows the four above with their readings and `check_by` dates.


### Build verification — 2026-10-03

- The comparison checkbox stays open because the recorded figures do not all equal the handoff. [The generated comparison report](data/model/storm-delta-validation.json) retains 28 comparisons, their source readings, 19 exact or explicitly rounded matches and nine differences. July’s five daily-mean ranks match.
- The October trigger is USGS 08158030 at September 30 10:35 UTC (8.54 cfs after 0 cfs at 10:30; threshold 7.26). The rule gives t0 September 29 10:35 UTC. Williamson crosses 21 cfs at October 1 17:35, after 6.79 at 17:30. The tool preserves these readings instead of adopting the probe dates.
- Differences include Barton Springs’ 19.5 cfs starting reading; Walnut’s last pre-window reading of 3.05 cfs on July 20, with the long gap disclosed; Bull’s latest 0.43 cfs; Barton Loop’s unrounded 0.05 cfs; Travis +0.10 ft using the last complete day; and Llano volume 15,216.9 acre-ft. Junction’s saved annual record is 319,000 cfs in 1935, not 2018.
- All 67 water tests pass. The swim lens fetched and applied schema 1 with the new block and passed 78 tests (one existing skip). BrowserOS showed the layer off by default, three spring bars, 335 hollow July rain symbols and four open October hypotheses, all checked by October 9. No red, green or yellow was added to the storm symbols.
- Limits remain explicit: no October 3 cloud export; USGS observations end October 2 at 12:10 UTC; no July rolling rain totals; EAA detail bodies lack their original exported fetch sidecars; two EAA spring records have no verified map coordinates. The literal zero-start response rule remains unchanged. The July daily-mean detection file is preserved; newer continuous crossing candidates appear in the comparison report.
- The hypotheses use initials `cloud/Mac session`, status `open`, and the recorded window-cap date as their review deadline. July hypotheses remain empty. The Travis hypothesis is retrospective, replacing the handoff’s forecast wording. No routine prompt or schedule was changed.

## 10. Prompt to start the build (copy-paste into a Claude Code session, Mac or cloud)

The prompt in the chat where this handoff was written is the canonical one; a copy is kept here so the handoff
is self-contained. It assumes the session starts cold.

```
Build the storm-delta map for hill-country-hydro, following HANDOFF_2026-10-03_storm-delta-map.md in that repo. Saul authorizes commits and pushes to main for this build (2026-10-03), in small commits, each only after the full test suite passes.

Setup first. If /home/user/hill-country-hydro (cloud) or the hill-country-hydro folder beside swimming-hole-alerts (Mac) is missing, clone https://github.com/saulbanov/hill-country-hydro. Then: git checkout main; git pull --rebase origin main. Read, in order: AGENTS.md, HANDOFF_2026-10-03_storm-delta-map.md, hill-country-hydro-system.md (the layer table and the standing rules), tools/hydro_context.py and tools/event_ledger.py (the derived-context pattern to copy), tools/hydromet.py and tools/usgs_series_history.py (the capture, manifest and versioning conventions), app/map.js (the layer and card pattern). Python 3 standard library only; no new dependencies.

Data. On the Mac the raw archive is local and data/normalized/water.sqlite is current. In the cloud, data/raw is absent: run python3 tools/cloud_capture_restore.py for the _cloud-captures folders dated 2026-10-01, 2026-10-02 and 2026-10-03, then the normalize steps from the README chain, before computing anything. Confirm the sqlite observations table holds 15-minute USGS readings from 2026-09-29 through 2026-10-02 before you start; if it does not, say so and stop.

Build, in this order, committing after each numbered step:
1. tools/usgs_peaks.py (handoff §3): collect, normalize, tests. Try the NWIS peak endpoint; if it is retired, keep the raw refusal and implement the OGC continuous-window fallback. Run collect for the 68 history-tier stations with a one-second pause.
2. Hill Country rainDaily sites added to PRIORITY['LCRA'] in tools/hydromet.py by the box rule in §3, pulled in full with pause 0.5; then the 15-minute rain window for 2026-09-30 to 2026-10-03 for those sites.
3. tools/storm_delta.py with detect and compute (§2, §3, §8): the window rule, per-site before/peak/now, ratio, response class with its thresholds written beside it, daily-mean rank, annual rank, instantaneous peak rank where usgs_peaks has one, NWS flood category where app/hazards-status.json has thresholds, rate of rise, springs, wells, lakes with the Llano inflow volume, caveats. Fixture tests per §3. Run detect; it must find the Oct 1–2, 2026 window from the record alone and write data/model/storms/<date>.json with the readings that triggered it. Run compute for that window and also for the July 2026 window (detect --since 2026-07-01). Reproduce the §0 and §8 numbers and report any that differ with the reading that differs.
4. publish_bundle.py: additive storm_delta block, schema stays 1; CHANGELOG entry; system document layer table and open items; README chain lines from §6. The swim lens's tests (../austin-swim-map or the folder beside) must still pass with the new block present.
5. app/map.js and app/index.html: the storm layer per §4, off by default, no red, green or yellow in it, cards worded per §4 with every number timed, the standing line under the panel paragraph. Open the page locally to confirm it draws; hollow symbols for missing totals.
6. The hypotheses box per §5, reading data/model/storms/<date>.json; write the four Oct 1–2 hypotheses into that file with check_by dates and status open, initials "cloud/Mac session", and leave the July 2026 file's hypotheses empty for Saul.

Rules that override anything else: raw before interpretation, with a .meta.json beside every fetched body; missing is never zero; never invent an id, a date or a threshold; every network call keeps its pause and records a refusal instead of retrying in a loop; no color or word that reads as a verdict about a place, no forecast; do not change rules, thresholds, place records, inventories or existing tests; do not touch the daily routine prompt; no PR and no scheduled check-ins. If a step cannot be finished, finish the others, say exactly what is missing and why, and leave the checklist in §9 marked honestly.

Finish with a message of at most fifteen lines: what was built, the Oct 1–2 and July 2026 numbers the tool reproduced and any that differ, the peak-flow endpoint's status, sizes added to the repo, test counts, and the commits pushed.
```
