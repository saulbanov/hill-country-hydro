# hill-country-hydro — system document

The living plan, decision log and session log for the Central Texas Water Ledger. Companion files:
`README.md` (what it is and how a day runs), `AGENTS.md` (rules every session follows), `CHANGELOG.md`
(bundle schema and daily-run lines), and **[`IDEAS.md`](IDEAS.md)** (what could be built on this layer,
especially once the history is in). The swim map that reads this repo's bundle keeps its own plan in
`saulbanov/austin-swim-map/swimming-hole-alerts-system.md`; the split itself is argued in that repo's
`PROPOSAL_2026-10-01_central-texas-water-split.md`.

## Purpose

Keep a dated, sourced record of what Central Texas's official water gauges say, and compare each reading
only with its own station's past. Measurement first (raw bytes, then typed rows), deterministic context
second (trend, window peak, seasonal percentile, event thresholds), and a published bundle third. No
forecast, no verdict about a place or a person. Lenses do that, and they say so.

## Layers (reporting-os vocabulary)

| Layer | Here | Files |
|---|---|---|
| L0 sources | USGS OGC API; TWDB Water Data for Texas (wells, reservoirs); Edwards Aquifer Authority pages and CSVs; NWS alerts and observations; City of Austin GIS creek and park lines; OpenStreetMap waterways | `data/raw/documentary/`, `app/*.geojson` |
| L1 acquisition | `tools/monitor.py collect`, `usgs_history.py`, `usgs_series_history.py`, `groundwater.py`, `reservoirs.py`, `eaa.py`, `hazards.py collect`, `weather_validation.py collect`, `cloud_capture_export.py` | `data/raw/` (ignored), `data/captures/` (versioned gzips), `_cloud-captures/` |
| L2 store and inventories | `water.sqlite` tables; `data/history/*.csv`; `regional_inventory.py` → `data/usgs-locations-regional.json`, `data/stations-regional.json`, `data/usgs-history-plan.json`, `data/wells-regional.json`; `data/eaa-sites.json`; `station_lists.py` | `data/` |
| L2 deterministic context | `hydro_context.py`, `event_ledger.py`, `reach_geometry.py`, `weather_validation.py validate` | `app/hydro-context.json`, `data/model/*-event-ledger.json`, `data/model/austin-reach-geometry.json`, `data/model/storm-week-validation.json` |
| L3 products | `publish_bundle.py` → `dist/water-state.json`; the map page `app/index.html` + `app/map.js`; the ideas in `IDEAS.md` | `dist/`, `app/` |

## What the record holds (2026-10-01)

- 215 live USGS locations in the box (-100.2, 29.3) to (-97.2, 30.9): 125 report discharge (38 Travis and Williamson, 30 hand-listed regional rivers and springs, 57 other), 37 report stage only, 3 springs (Barton, Jacob's Well, Hueco), 12 wells, 33 lake sites. Current readings for all 215 each morning; 28 parameter codes parsed.
- Daily histories: 68 discharge records (Onion Creek at US 183 from 1924) and 126 non-flow series (stage, lake elevation, precipitation totals, well depth, water temperature) with manifests; two incomplete responses recorded and skipped.
- TWDB: 127 wells in the box, one statewide daily feed; full records for every live well (90; J-17 from 1932; Lovelady with 15-minute data), fetched once and extended by the feed. By aquifer among the live wells: Trinity 55, Edwards (Balcones Fault Zone) 12, Carrizo-Wilcox 7, Edwards-Trinity Plateau 6, Ellenburger-San Saba 5, Hickory 2, Yegua-Jackson 2. Ten lakes with full records (Lake Austin from 1940).
- EAA: 69 wells, 18 streams, 85 rain gauges listed; per-site CSVs are the full record; the server throttles bulk pulls (HTTP 500 and resets after a few dozen files on 2026-10-01), so coverage fills in slowly.
- EAA conditions: the Aquifer Conditions page carries the Comal springflow daily record since 1927 and San Marcos since 1956 (not served live by USGS), the J-17 and J-27 daily highs, today's 15-minute readings, and a summary table with the 10-day averages the Critical Period rules use; captured daily. The stage trigger tables are images, captured and transcribed with checksums into `data/eaa-cpm-stages.json`. On 2026-10-01 the arithmetic (J-17 10-day 638.7 ft, Comal 145 cfs) and the EAA's own page agree on Stage 3, 35% reduction for the San Antonio Pool; Uvalde stable.
- NWS: active alerts by county and flood-stage categories for 14 forecast gauges; hourly observations at Camp Mabry and Bergstrom for the rain validation.

## Standing rules

See `AGENTS.md`. The ones that matter most when adding a source: preserve the raw response with a meta sidecar before parsing; never write a zero for a value the provider did not return; keep one versioned gzip per series and prune older ones; be gentle with providers and record a refusal instead of looping; never add a color, a verdict, or a forecast here.

## Daily routine

A claude.ai Routine fires at 6:57 AM Central into the cloud session that seeded this repo. It runs the README chain here, publishes the bundle, commits `Daily run <date>` and pushes, then runs the swim lens off the bundle. Sundays add the full history refresh and the event ledgers. The long-term home for the run is Saul's Mac; the cloud export of raw captures (`_cloud-captures/`) is the stopgap until then and grows roughly 25 MB a day.

## Synchronizing with the Mac copy and the swim lens
The order of operations (merge the swim repo on the Mac, clone this repo beside it, move the measurement raw archive here, rebuild, publish, verify the lens, then prune the swim repo and move the daily run home) is written once, in `saulbanov/austin-swim-map/HANDOFF_2026-10-01_local-integration.md` section 10. The same walkthrough is copied here as `HANDOFF_2026-10-01_split-and-sync.md`; `tools/cloud_capture_restore.py` exists and is tested.

## Open items

- Public visibility: the collectors send Saul's contact email in their User-Agent header; swap for a project address before making the repository public.
- EAA throttling: find the rate the server tolerates, or ask data@edwardsaquifer.org for a bulk export.
- Two incomplete USGS daily responses (a Lovelady well-depth mean and one lake elevation) to re-fetch.
- LCRA Hydromet (City of Austin flood gauges, lake operations) has no data endpoint found; TWDB relays the lake levels.
- Nothing live measures bacteria; the 8 water-temperature and 6 turbidity series are the closest water-quality signals.
- A `CHANGELOG.md` schema bump process for the bundle once the first lens change needs one.

## Decision log

- 2026-10-01 · Every live well keeps its full record · Saul asked whether all the relevant wells had been pulled into the layer. They had not: an aquifer-and-size rule had kept full records for 22 wells and left out the 31 Kerr, Kendall and Bandera Trinity wells that carry the Hill Country rivers' base flow. The rule is now "every well with a daily-feed row at most 7 days old" (90 wells); the remaining 77 records (1.6 GB raw, roughly 40 MB gzipped) were fetched the same day. J-17 stays what it is: the San Antonio Pool's regulatory index well, relevant to the Comal and San Marcos springs, not to Austin or the Hill Country rivers; Lovelady is the Austin well, and the Trinity wells are the rivers'.

- 2026-10-01 · Stage thresholds are part of the daily package, not a one-off · Saul: "This should be part of the deterministic package." `eaa.py conditions` now captures the EAA conditions and plan pages every morning; the stage tables (images) are captured verbatim and transcribed once with checksums; `assess` computes the implied stage from the 10-day averages and shows it beside the EAA's stated reduction, flagging any disagreement rather than resolving it.
- 2026-10-01 · Base map · USGS The National Map (public domain, hydrography drawn) as default, CARTO light as alternate; OpenStreetMap's own tile server is not used in production per its tile policy. Lake data is daily back to the 1940s; the "2011 and 2022" in `IDEAS.md` are comparison years, not a sampling step.

- 2026-10-01 · Repository created and seeded · Saul chose the name `hill-country-hydro`, said the water map can be public, and agreed to the split proposed in the swim repo. Seeded from `austin-swim-map` at its 2026-10-01 `main`; commit history for the moved files stays there. Started private because of the contact email in request headers.
- 2026-10-01 · Bundle schema 1 · One file, one direction: `dist/water-state.json` carries stations, wells, lakes, EAA sites and alerts with a `schema_version`; a lens reads it and never writes back. Changes bump the version and are logged in `CHANGELOG.md`.
- 2026-10-01 · Ideas file · Saul asked for the build ideas to live in a Markdown file cross-linked with this document: `IDEAS.md`.

## Session log

### 2026-10-01 — seeded, pushed, documented
- First commit `f3dfcd9` pushed to `saulbanov/hill-country-hydro` (private) after Saul created the empty repository; the session's GitHub integration cannot create repositories itself.
- Added this system document and `IDEAS.md`; linked both from `README.md` and `AGENTS.md`. Added `tools/cloud_capture_restore.py` (checksum-verified restore of `_cloud-captures/` into `data/raw/`, never overwriting a differing file) and the split-and-sync handoff. Tests: 24 pass.
