# hill-country-hydro — the Central Texas Water Ledger

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
python3 tools/weather_validation.py collect && python3 tools/weather_validation.py validate
python3 tools/publish_bundle.py
# Sundays: full history refresh
python3 tools/usgs_history.py collect && python3 tools/usgs_history.py normalize
python3 tools/usgs_series_history.py collect && python3 tools/usgs_series_history.py normalize
python3 tools/event_ledger.py
# Once (or when PRIORITY in hydromet.py grows): full Hydromet records back to 1995 (LCRA, hourly) and 2015 (City, 15-minute), in parallel shards over disjoint site lists
python3 tools/hydromet.py history --agency LCRA --pause-seconds 0.5 && python3 tools/hydromet.py history --agency COA --pause-seconds 0.5
python3 -m unittest discover -s tests
```

## Inventories (rebuilt only from saved captures)
- `data/usgs-locations-regional.json` — every live USGS location, kinds and live parameters; `data/stations-regional.json` — discharge stations by tier; `data/usgs-history-plan.json` — non-flow daily series kept as history.
- `data/wells-regional.json` — TWDB wells (90 live wells with full records); `data/eaa-sites.json` — EAA wells, streams, rain gauges.
- `data/raw/hydromet/lists/` — the Hydromet site lists per sensor type (LCRA flow, rain, lake level, water temperature; City flow, rain), captured daily; `data/captures/hydromet/<agency>/<site>-manifest.json` — which history windows are on file.
- `python3 tools/regional_inventory.py` and `--all-locations` rebuild them from `data/raw/documentary/usgs-regional-inventory-*/`.

## Rules
See `AGENTS.md`: raw before interpretation, missing is never zero, no color and no verdict here, ids frozen,
official sources only, gentle with providers. Attribution: USGS, TWDB (Water Data for Texas), LCRA Hydromet (LCRA and City of Austin gauges), Edwards Aquifer
Authority, National Weather Service, OpenStreetMap contributors (ODbL), City of Austin GIS.
