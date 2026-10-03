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
| L1 acquisition | `tools/monitor.py collect`, `usgs_history.py`, `usgs_series_history.py`, `usgs_peaks.py`, `hydromet.py`, `groundwater.py`, `reservoirs.py`, `eaa.py`, `hazards.py collect`, `weather_validation.py collect`, `cloud_capture_export.py` | `data/raw/` (ignored), `data/captures/` (versioned gzips), `_cloud-captures/` |
| L2 store and inventories | `water.sqlite` tables; `data/history/*.csv`; `regional_inventory.py` → `data/usgs-locations-regional.json`, `data/stations-regional.json`, `data/usgs-history-plan.json`, `data/wells-regional.json`; `data/eaa-sites.json`; `station_lists.py` | `data/` |
| L2 deterministic context | `hydro_context.py`, `event_ledger.py`, `storm_delta.py`, `reach_geometry.py`, `weather_validation.py validate` | `app/hydro-context.json`, `data/model/*-event-ledger.json`, `data/model/austin-reach-geometry.json`, `data/model/storm-week-validation.json`, `data/model/storms/*.json`, `app/storm-delta.json` |
| L3 products | `publish_bundle.py` → `dist/water-state.json`; the map page `app/index.html` + `app/map.js`; the ideas in `IDEAS.md` | `dist/`, `app/` |

## What the record holds (2026-10-01)

- 215 live USGS locations in the box (-100.2, 29.3) to (-97.2, 30.9): 125 report discharge (38 Travis and Williamson, 30 hand-listed regional rivers and springs, 57 other), 37 report stage only, 3 springs (Barton, Jacob's Well, Hueco), 12 wells, 33 lake sites. Current readings for all 215 each morning; 28 parameter codes parsed.
- Daily histories: 68 discharge records (Onion Creek at US 183 from 1924) and 126 non-flow series (stage, lake elevation, precipitation totals, well depth, water temperature) with manifests; two incomplete responses recorded and skipped.
- TWDB: 127 wells in the box, one statewide daily feed; full records for every live well (90; J-17 from 1932; Lovelady with 15-minute data), fetched once and extended by the feed. By aquifer among the live wells: Trinity 55, Edwards (Balcones Fault Zone) 12, Carrizo-Wilcox 7, Edwards-Trinity Plateau 6, Ellenburger-San Saba 5, Hickory 2, Yegua-Jackson 2. Ten lakes with full records (Lake Austin from 1940).
- EAA: 69 wells, 18 streams, 85 rain gauges listed. Since 2026-10-03 every active well's full daily-high record comes from its detail page (the CSV door closed on 2026-10-01); rain and stream data wait on a door that works.
- EAA conditions: the Aquifer Conditions page carries the Comal springflow daily record since 1927 and San Marcos since 1956 (not served live by USGS), the J-17 and J-27 daily highs, today's 15-minute readings, and a summary table with the 10-day averages the Critical Period rules use; captured daily. The stage trigger tables are images, captured and transcribed with checksums into `data/eaa-cpm-stages.json`. On 2026-10-01 the arithmetic (J-17 10-day 638.7 ft, Comal 145 cfs) and the EAA's own page agree on Stage 3, 35% reduction for the San Antonio Pool; Uvalde stable.
- LCRA Hydromet (added 2026-10-02): 407 gauges in one feed, every reading captured daily. 81 City of Austin flood-warning sites (47 creek stage sites, 34 rain gauges) fill the gaps USGS leaves on Williamson (Emerald Forest, Silvermine, Kincheon Branch), Slaughter at Brodie, Walnut, Little Walnut, Shoal, Waller, Boggy, Fort Branch, Bouldin and Blunn; 275 LCRA sites add Bull Creek at Loop 360, Barton at SH 71 and Loop 360, Onion at Buda and US 183, Walnut at Webberville Road, the Pedernales, Llano, San Saba and Sandy Creek gauges, and lake and dam levels for Buchanan through Lady Bird Lake. Full history on file for the priority sites (59 series, 21.6 million readings: LCRA from December 1991, the Austin creek sites at 15 minutes and the rivers and lakes hourly with 15-minute fill where the hourly series is empty; City sites at 15 minutes from late 2015), extended by the daily run; the rest can be pulled the same way by adding a site to `PRIORITY`.
- NWS: active alerts by county and flood-stage categories for 14 forecast gauges; hourly observations at Camp Mabry and Bergstrom for the rain validation.

## Standing rules

See `AGENTS.md`. The ones that matter most when adding a source: preserve the raw response with a meta sidecar before parsing; never write a zero for a value the provider did not return; keep one versioned gzip per series and prune older ones; be gentle with providers and record a refusal instead of looping; never add a color, a verdict, or a forecast here.

## Daily routine

The Mac LaunchAgent `org.saulelbein.hill-country-hydro` is the daily-run home, scheduled at 6:57 AM Mac local time (Central at cutover). It runs the water chain, publishes and pushes the bundle, then runs the swim lens. Sundays add the full history refresh and event ledgers. Saul confirmed on 2026-10-02 that he disabled the former claude.ai routine `trig_012HVfp2gXNb1wK9K1LBvmyB` before this job was loaded. The claude.ai state could not be inspected independently because the Mac browser was signed out. See `tools/README.md` for the claim, missed-run, and log behavior. The first scheduled Mac run remains to be observed.

## Synchronizing with the Mac copy and the swim lens
The order of operations (merge the swim repo on the Mac, clone this repo beside it, move the measurement raw archive here, rebuild, publish, verify the lens, then prune the swim repo and move the daily run home) is written once, in `saulbanov/austin-swim-map/HANDOFF_2026-10-01_local-integration.md` section 10. The same walkthrough is copied here as `HANDOFF_2026-10-01_split-and-sync.md`; `tools/cloud_capture_restore.py` exists and is tested.

## Open items

- Observe the first scheduled Mac run and check both `Daily run YYYYMMDD` commits. At 2026-10-02 21:50 Central the water checkout contained concurrent uncommitted Hydromet history work. If it remains dirty at 6:57, the runner's clean-branch guard will fail before any provider request; finish or move that work through its own session, then assess the next day's run without a same-day retry.

- Storm-delta coverage: the restored USGS record ends October 2 at 12:10 UTC; no October 3 cloud export was found. July has bounded USGS flow and stage, but no matching Hydromet rolling-total snapshots, so July rain symbols are hollow. EAA detail bodies lack their original exported fetch sidecars; that provenance gap is disclosed.
- Storm response rule: a zero start makes “below twice start” unreachable for nonnegative flow. The tool preserves the handoff’s literal threshold and withholds recession-dependent classifications when observations are incomplete. Any rule revision needs Saul’s decision.
- July detection review: the original July 11 record was created from daily means. Added continuous readings produce a July 10 23:40 UTC first crossing and a separate post-cap July 19 candidate. The original is preserved; `data/model/storm-delta-validation.json` retains the newer candidate readings for review.
- Storm review: hypotheses are reviewed from saved observations by their recorded check dates, without a scheduled check-in. The two EAA spring records lack verified coordinates in the existing inventory and appear as cards; the three inventoried USGS springs have map bars.

- Public visibility: the collectors send Saul's contact email in their User-Agent header; swap for a project address before making the repository public.
- EAA: the CSV download door has been closed (HTTP 500 to everything) since 2026-10-01. Wells now come from the detail pages; rain gauges have no other door (ask data@edwardsaquifer.org for an export, or use LCRA Hydromet's 246 rain gauges for the Hill Country); streams exist as 130 MB pages, opt-in.
- Two incomplete USGS daily responses (a Lovelady well-depth mean and one lake elevation) to re-fetch.
- LCRA Hydromet: the site lists name 81 LCRA flow, 246 LCRA rain and 19 lake-level sites, plus 42 City flow and 78 City rain sites; only the priority set has full history. Growing it is a matter of request budget (about one request per site per four months of record; the server answered roughly one request every four seconds on 2026-10-02).
- Nothing live measures bacteria; the 8 water-temperature and 6 turbidity series are the closest water-quality signals.
- A `CHANGELOG.md` schema bump process for the bundle once the first lens change needs one.

## Decision log

- 2026-10-03 · Storm computation stays offline · Acquisition retains raw bodies and metadata first, then normalization and deterministic computation use them. This follows Saul’s scrape/analysis separation over the handoff’s shorthand “compute fetches.” Additive `storm_delta` keeps schema 1 as explicitly requested. Daily records use the last complete day before t0 as baseline; within-day clock times are not invented. Hand-authored storm hypotheses remain separate from computed measurements.

- 2026-10-02 · Move the daily run to the Mac · Saul chose Mac launchd and confirmed he disabled the claude.ai routine before the Mac job was loaded. The runner permits one provider attempt per Central-time day and uses repeatable offline fault tests; no same-day provider retry is scheduled. The first live scheduled run is the end-to-end check.

- 2026-10-02 — Hydromet history is stored in fixed calendar windows (Jan-Apr, May-Aug, Sep-Dec) rather than rolling ones, so a window's file name never changes and a closed window is fetched once. The window holding today is refreshed every run. One manifest per site so shards over disjoint site lists can run in parallel without clobbering each other. LCRA history at hourly resolution by default (the server offers it; 15-minute is four times the bytes and available with `--fifteen-minute`); City history at its native 15 minutes because the City endpoint has no hourly form.

- 2026-10-01 · Every live well keeps its full record · Saul asked whether all the relevant wells had been pulled into the layer. They had not: an aquifer-and-size rule had kept full records for 22 wells and left out the 31 Kerr, Kendall and Bandera Trinity wells that carry the Hill Country rivers' base flow. The rule is now "every well with a daily-feed row at most 7 days old" (90 wells); the remaining 77 records (1.6 GB raw, roughly 40 MB gzipped) were fetched the same day. J-17 stays what it is: the San Antonio Pool's regulatory index well, relevant to the Comal and San Marcos springs, not to Austin or the Hill Country rivers; Lovelady is the Austin well, and the Trinity wells are the rivers'.

- 2026-10-01 · Stage thresholds are part of the daily package, not a one-off · Saul: "This should be part of the deterministic package." `eaa.py conditions` now captures the EAA conditions and plan pages every morning; the stage tables (images) are captured verbatim and transcribed once with checksums; `assess` computes the implied stage from the 10-day averages and shows it beside the EAA's stated reduction, flagging any disagreement rather than resolving it.
- 2026-10-01 · Base map · USGS The National Map (public domain, hydrography drawn) as default, CARTO light as alternate; OpenStreetMap's own tile server is not used in production per its tile policy. Lake data is daily back to the 1940s; the "2011 and 2022" in `IDEAS.md` are comparison years, not a sampling step.

- 2026-10-01 · Repository created and seeded · Saul chose the name `hill-country-hydro`, said the water map can be public, and agreed to the split proposed in the swim repo. Seeded from `austin-swim-map` at its 2026-10-01 `main`; commit history for the moved files stays there. Started private because of the contact email in request headers.
- 2026-10-01 · Bundle schema 1 · One file, one direction: `dist/water-state.json` carries stations, wells, lakes, EAA sites and alerts with a `schema_version`; a lens reads it and never writes back. Changes bump the version and are logged in `CHANGELOG.md`.
- 2026-10-01 · Ideas file · Saul asked for the build ideas to live in a Markdown file cross-linked with this document: `IDEAS.md`.

## Session log

### 2026-10-03 — storm-delta build
- Validation: 67 water tests pass. A temporary copy of the swim lens fetched and applied the new bundle, then passed its 78-test suite (one existing skip). The layer drew in BrowserOS with hollow missing symbols and timed cards. The October file now contains four open hypotheses with dated supporting readings, initials `cloud/Mac session`, and October 9 review dates derived from the recorded cap. July remains empty. Handoff §9 records the unreproduced figures and coverage limits; its exact-reproduction checkbox remains open.
- Added raw-first annual peak acquisition for 68 USGS history stations (64 numeric annual records; four without annual peaks), plus explicit bounded July flow/stage acquisition. The NWIS peak endpoint responded normally; redirects/refusals remain preserved and the OGC window command is available as fallback.
- Expanded daily rain priority to all 123 LCRA rain-reporting sites in the specified box, including river and lake sites with rain sensors. All 123 were pulled; 121 have historical readings. Five series reach 1988, with empty 1987 and 1986 responses retained to establish the earlier boundary. Bounded native rain supplies intensity without requesting every year's 15-minute rain.
- Added immutable detection records, offline storm computation, an optional schema-1 bundle block, and an off-by-default map layer. Comparisons preserve daily/instantaneous sampling, missing readings, source dates, long baseline gaps and the unchanged response thresholds. `tools/storm_validation.py` writes the worked-example comparison report. The original July detection remains frozen after continuous data enrichment.
- The October record reproduces Shoal 541 cfs, Walnut 650 cfs, Junction 35,000 cfs, Barton Springs 26.5 cfs, J-17 640.07 ft and its +1.74 ft daily rise, the 36-well +0.05 ft seven-day median and recharge-zone −0.11 ft median. The detected t0 changes Barton’s baseline to 19.5 cfs and the complete-day Travis baseline to September 28, giving +0.10 ft. Llano integration yields 15,216.9 acre-ft through October 2 11:00 UTC. Detailed differing readings are retained in `data/model/storm-delta-validation.json`.
- July daily maxima and ranks match all five examples: Comfort 52,900 cfs (#2/88), Kerrville 29,400 (#3/41), Llano 53,600 (#7/88), Pedernales 23,600 (#15/88), Junction 30,400 (#14/109). Acquired instantaneous peaks are stored separately; they do not replace those daily comparisons.

### 2026-10-02 — Mac daily-run cutover
- After Saul reported the claude.ai routine disabled, loaded `org.saulelbein.hill-country-hydro` in `gui/501`. `launchctl print` showed one 6:57 calendar trigger, zero runs, and no immediate collection. `plutil -lint` passed. The job uses `RunAtLoad=false`; it does not catch up after a full power-off. The cloud state is based on Saul's confirmation, not an independent claude.ai inspection. No provider collection was repeated on October 2.

### 2026-10-03 — storm-delta map handoff
Saul asked what the week's storm data says and then for a handoff to make it one of the proposed maps. The read: rain fell on the upper Llano, not Austin; paved Austin creeks flashed and emptied, limestone creeks barely moved; the Llano near Junction peaked at 35,000 cfs (top 0.1% of daily means since 1915); Barton Springs rose to 26.5 cfs but stayed at the 17th percentile; Comal did not respond; J-17 jumped 1.7 ft in a day; Travis gained 0.2 ft with about 16,600 acre-ft past Llano and the pulse still running. The handoff specifies the storm window rule, `tools/storm_delta.py`, the map layer, and a hypotheses list with check-by dates.

### 2026-10-03 — EAA refusals diagnosed; wells rerouted through the detail pages
Saul asked for a way around the EAA refusals. Probing showed the CSV download endpoints answer HTTP 500 (a generic "Oops" page) to every request, for every site and sensor, with plain or browser-like headers and a session cookie, so it is a closed door rather than a rate limit. The site's own well pages embed the full daily-high record and the sensor list, and that is now what `eaa.py details` reads. Stream pages carry the full 5-minute record but weigh about 130 MB each (opt-in); rain-gauge pages carry no data. Cross-reference: 20 of the 69 EAA wells also have USGS site numbers and 3 are in the TWDB daily feed (J-17, J-27, ANR602).

### 2026-10-02 — Mac daily runner prepared; cloud cutover pending
- Added `tools/daily_mac_run.py` and an unloaded 6:57 AM Central launchd plist. The runner syncs clean branches, blocks a duplicate day from either existing `Daily run YYYYMMDD` commit or its own dated claim, runs the water chain before the swim lens, tests both, and pushes each repo only after its chain succeeds. The Mac keeps raw captures locally, so neither cloud export command appears in its plan. A failed water command, bundle validation, or push stops before the lens. Five offline tests passed, including seven injected fault points; the full water suite passed 38 tests. No provider collection or Mac scheduled run occurred in this session. The cloud routine's current status and deactivation still require confirmation before the plist can be loaded.

### 2026-10-02 — Mac capture reconciliation for the swim split
- Restored the October 2 water and swim cloud exports into the ignored local `data/raw/` archive, then checked all five swim-side export folders against it. The restore reported zero bad or missing files; identical captures were skipped. The raw archive is now about 2.7 GB. This was an archive reconciliation, not another provider collection run. The swim repo's tracked duplicate exports and water-only histories were then eligible for its approved §7 prune.

### 2026-10-02 — LCRA Hydromet gauges
Saul pointed out that the Hydromet network carries more Bull, Barton, Onion and Williamson creek gauges than USGS does. A local session had already found the all-sites feed; this one mapped the history endpoints from the site's own JavaScript (`HistoricData/GetDataBySite` for LCRA, `CoaHistoricalData/GetDataBySite` for the City; both refuse windows of 180 days or more; LCRA offers `/hourly`), probed the record starts (1995 for LCRA creek sites, 2005 for Lake Austin, November 2015 for the City), and wrote `tools/hydromet.py` with tests. Full history pulled for the priority sites in six parallel shards; sizes and refusals are in the manifests.

### 2026-10-01 — Mac archive restored and bundle rebuilt
- Cloned beside `swimming-hole-alerts`. Copied existing USGS raw captures and checksum-restored four cloud capture folders (1,845 files; zero mismatches); the swim repo's duplicate folders matched byte-for-byte. Restored 99 TWDB well histories and ten reservoir histories from versioned gzips with manifest SHA-256 and byte-length checks. Raw archive is 2.5 GB; no collectors ran.
- Rebuilt normalized observations, 68 flow histories, 126 non-flow histories, well and reservoir history, EAA context, station context and event ledgers, storm validation, and `dist/water-state.json`. Bundle reports 218 stations, 127 wells, ten lakes, 69 EAA wells, 85 EAA rain gauges, and no missing inputs. The two previously noted USGS non-flow responses remain skipped. At publication time all station readings were beyond the bundle's freshness window, so zero were labeled fresh. All 26 tests pass; local map cards opened for a USGS station, a TWDB well, and Lake Austin.

### 2026-10-01 — seeded, pushed, documented
- First commit `f3dfcd9` pushed to `saulbanov/hill-country-hydro` (private) after Saul created the empty repository; the session's GitHub integration cannot create repositories itself.
- Added this system document and `IDEAS.md`; linked both from `README.md` and `AGENTS.md`. Added `tools/cloud_capture_restore.py` (checksum-verified restore of `_cloud-captures/` into `data/raw/`, never overwriting a differing file) and the split-and-sync handoff. Tests: 24 pass.
