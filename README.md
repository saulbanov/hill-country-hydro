# hill-country-hydro — the Central Texas Water Ledger

Published map: [Central Texas Water Ledger](https://hill-country-hydro.saul-elbein.chatgpt.site). The hosted map is a saved snapshot; publishing updates is separate from the daily collection run.

**What this is.** A dated, sourced record of what Central Texas's official water gauges say: 215 USGS
locations (streams, springs, wells, lakes) from Junction to Bastrop and Uvalde to Georgetown, 127 state
wells, ten lakes, and the Edwards Aquifer Authority's wells, rain gauges and streams, plus NWS notices.
Every reading is kept raw first, normalized second, and compared only with its own station's past
(trend, seasonal percentile, event thresholds). It makes no forecast and no verdict. Other projects,
such as the Austin swimming-hole map, read its published bundle and apply their own judgment.

**Who it is for.** Reporters and readers who want to know, with sources, whether a river, spring, well
or lake is up or down, by how much, and how that compares with the record. It was split out of
`austin-swim-map` on 2026-10-01 (see that repo's `PROPOSAL_2026-10-01_central-texas-water-split.md`).

Plan, decisions and log: [`hill-country-hydro-system.md`](hill-country-hydro-system.md). What could be built on this layer: [`IDEAS.md`](IDEAS.md).

## How a day works

Saul chose the Mac for the daily run on October 2. The loaded job is
`org.saulelbein.hill-country-hydro`, scheduled for 6:57 AM Mac local time,
water first and swim second. Saul reported the old claude.ai trigger disabled
before the Mac job was loaded; the signed-out Mac browser could not verify its
state independently. Installation, reversal, logs, sleep behavior, and offline
checks are in [tools/README.md](tools/README.md). The first scheduled Mac run
has yet to prove the chain end to end.

1. **Collect** (raw first): `monitor.py collect --inventory` reads every live USGS location; `groundwater.py collect`
   one statewide TWDB well file; `reservoirs.py collect` ten lake CSVs; `eaa.py details` the EAA list pages and every
   active well's page (its full daily record rides in the page) at a gentle pace; `hydromet.py collect` the LCRA Hydromet all-sites feed (LCRA, City of Austin and mirrored USGS
   gauges: creek stage and flow, rain accumulations, lake and dam levels) plus the window of 15-minute history holding today; `hazards.py assess` NWS alerts and flood-stage categories; `weather_validation.py collect` NWS observations.
2. **Normalize**: typed rows into `data/normalized/water.sqlite`; daily histories into `data/history/*.csv`.
3. **Context**: `hydro_context.py` (freshness, 6-hour trend, 48-hour peak, same-time-of-year percentile) and,
   weekly, `event_ledger.py` (hysteresis events and per-station thresholds) for the 68 history-tier stations.
4. **Publish**: `publish_bundle.py` writes `dist/water-state.json` (schema in `CHANGELOG.md`).
5. **Schedule**: the Mac LaunchAgent `org.saulelbein.hill-country-hydro` runs both repositories at 6:57 AM Mac local time. It keeps raw captures in local `data/raw/`, commits and pushes the water bundle before running the swim lens, and skips a second provider attempt on the same date. See `tools/README.md` for logs and missed runs.

```sh
python3 tools/monitor.py collect --inventory && python3 tools/monitor.py normalize
python3 tools/signal_pipeline.py normalize && python3 tools/signal_pipeline.py parse && python3 tools/monitor.py readings   # readings = app/gauge-readings.json, the newest value per station the bundle carries
python3 tools/groundwater.py collect && python3 tools/groundwater.py normalize && python3 tools/groundwater.py assess
python3 tools/reservoirs.py collect && python3 tools/reservoirs.py normalize && python3 tools/reservoirs.py assess
python3 tools/eaa.py conditions && python3 tools/eaa.py details --pause-seconds 3 && python3 tools/eaa.py normalize && python3 tools/eaa.py assess   # conditions = the EAA summary table, springflow and index-well histories, and the stated reduction; details = every active well's page with its full daily-high record (the CSV download door has answered HTTP 500 since 2026-10-01); Sundays add --version
python3 tools/hydromet.py collect && python3 tools/hydromet.py history --recent-only && python3 tools/hydromet.py normalize && python3 tools/hydromet.py assess   # LCRA Hydromet; history windows < 180 days, three fixed per year
python3 tools/hazards.py assess
python3 tools/hydro_context.py
python3 tools/storm_delta.py detect && python3 tools/storm_delta.py compute --all-open
python3 tools/weather_validation.py collect && python3 tools/weather_validation.py validate
python3 tools/publish_bundle.py
# Sundays: full history refresh
python3 tools/usgs_history.py collect && python3 tools/usgs_history.py normalize
python3 tools/usgs_series_history.py collect && python3 tools/usgs_series_history.py normalize
python3 tools/event_ledger.py
python3 tools/usgs_peaks.py collect && python3 tools/usgs_peaks.py normalize
# Once (or when PRIORITY in hydromet.py grows): full Hydromet records back to 1995 (LCRA, hourly) and 2015 (City, 15-minute), in parallel shards over disjoint site lists
python3 tools/hydromet.py history --agency LCRA --pause-seconds 0.5 && python3 tools/hydromet.py history --agency COA --pause-seconds 0.5
python3 -m unittest discover -s tests
```

## Storm windows

`storm_delta.py detect` records the readings that chose each window under `data/model/storms/`.
Detection preserves an existing file. `compute --storm <date>` rebuilds that window's measurements;
`compute --all-open` updates windows still open in the derived output. Computation is offline.
The map's **Storm changes** checkbox is off by default. The optional `storm_delta` bundle block
keeps schema 1; each reading carries its time, sampling basis and source.

Bounded acquisition precedes computation. For the October case:

```sh
python3 tools/hydromet.py rain-window --start 2026-09-30 --end 2026-10-03 --pause-seconds 0.5
python3 tools/hydromet.py normalize
python3 tools/storm_delta.py compute --storm 2026-09-30
```

A saved successful rain window is reused; `--refresh` explicitly requests a newer body.
The dates are inclusive Central-time calendar days. Future portions of a requested interval
have no readings. Daily rain history covers LCRA sites reporting rain inside 29.9–30.9 latitude,
−100.2 to −97.9 longitude, including river and lake sites with rain sensors. Those sites join
`PRIORITY` from the saved all-sites feed and ride `history --recent-only`.

For an older detected window, `usgs_peaks.py collect-window --start <UTC> --end <UTC>`
fetches flow; add `--parameter 00065` for stage. Both require explicit increasing UTC timestamps
at most ten days apart, pause one second, and retain refusals. Run `usgs_peaks.py normalize`
before computing. Continuous-window observations are never represented as an annual peak file.
See [the comparison report](data/model/storm-delta-validation.json) for the handoff's worked examples;
regenerate it after both computations with `python3 tools/storm_validation.py`.
These README commands do not alter the installed daily runner or its prompt.

## Inventories (rebuilt only from saved captures)
- `data/usgs-locations-regional.json` — every live USGS location, kinds and live parameters; `data/stations-regional.json` — discharge stations by tier; `data/usgs-history-plan.json` — non-flow daily series kept as history.
- `data/wells-regional.json` — TWDB wells (90 live wells with full records); `data/eaa-sites.json` — EAA wells, streams, rain gauges.
- `data/raw/hydromet/lists/` — the Hydromet site lists per sensor type (LCRA flow, rain, lake level, water temperature; City flow, rain), captured daily; `data/captures/hydromet/<agency>/<site>-manifest.json` — which history windows are on file.
- `python3 tools/regional_inventory.py` and `--all-locations` rebuild them from `data/raw/documentary/usgs-regional-inventory-*/`.

## Rules
See `AGENTS.md`: raw before interpretation, missing is never zero, no color and no verdict here, ids frozen,
official sources only, gentle with providers. Attribution: USGS, TWDB (Water Data for Texas), LCRA Hydromet (LCRA and City of Austin gauges), Edwards Aquifer
Authority, National Weather Service, OpenStreetMap contributors (ODbL), City of Austin GIS.


## Reusable creek prototype analytics

The independent [`creek-measurements/v1` contract](docs/CREEK_ANALYTICS.md) normalizes saved
USGS and LCRA/City creek observations, retaining sources, alternative sensors and conflicts.
It is an offline prototype analytic layer in this repository; the website consumes its output.
The existing water bundle stays schema 1. [Source coverage and gaps](docs/CREEK_COVERAGE.md).

```sh
python3 tools/creek_normalize.py --storm 2026-09-30 --through 2026-10-03T12:15:00Z
python3 tools/creek_analytics.py
```

Other consumers can read `data/normalized/creek-analytics/catalog.json`, `observations.jsonl`
and `references.json`, or use `tools.creek_analytics.load()`. The large store is regenerable
from the preserved inputs and remains ignored. These commands are manual; the daily routine
is unchanged. The contract documents missing archive prerequisites and comparison limits.
