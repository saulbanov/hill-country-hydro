# Changelog

## 2026-10-03 — additive: retrospective storm changes
- Optional `storm_delta` contains detected windows, timed rain/flow/spring/well/lake measurements, sampling-specific ranks, coverage caveats and reviewer hypotheses. Schema stays 1 under Saul’s explicit authorization for this additive block. Existing blocks retain their shape. Detection records its triggering readings; computation reads saved data only. The map layer starts off and uses measurement colors without a place verdict.
- USGS annual peak bodies and bounded July continuous flow/stage captures are retained with metadata. LCRA rain history expands by the handoff’s geographic rule; bounded native rain captures supply observed hourly intensity.

## 2026-10-03 — EAA wells through the detail pages
- The EAA CSV download endpoints (`DownloadGroundwaterCsv`, `DownloadRainGaugesCsv`, `DownloadSpringAndStreamCsv`) have answered HTTP 500 with a generic error page to every request since 2026-10-01, for any site or sensor, with or without browser headers and cookies; this is not throttling. `eaa.py details` now reads each active well's `/GroundWater/Details/<siteInfoId>` page, which embeds the full daily-high record (J-17 from 1932) and the sensor inventory, and `normalize` fills `eaa_well_levels` from it (DHE elevation and DTW depth). `--version` keeps one gzip per well under `data/captures/eaa/details/` (Sundays). Streams: `/SpringsAndStreams/GaugeHeight/<id>` carries the full 5-minute record (~130 MB a site) and is opt-in with `--streams`. Rain gauges have no page that carries data; `eaa.rain_gauges` stays empty until the CSV door reopens or the EAA offers an export. Bundle shape unchanged.

## 2026-10-02 — fix: `monitor.py readings`
- Since the split, nothing in this repo rewrote `app/gauge-readings.json` after a collect (the step lived in the lens's `assess`), so the bundle carried the previous day's USGS values. `monitor.py readings` now writes the file from `data/parsed/latest-by-station.json`; it runs after `signal_pipeline.py parse` in the README chain and the routine.

## 2026-10-02 — additive: `hydromet` (LCRA Hydromet: LCRA and City of Austin gauges)
- `hydromet.py` captures `hydromet.lcra.org/api/GetDataForAllSites` (407 sites: 275 LCRA river, rain, lake and dam gauges across the Colorado basin; 81 City of Austin flood-warning gauges; 51 mirrored USGS sites) and the six per-sensor site lists every day. History comes from two endpoints that refuse windows of 180 days or more, so it is pulled in three fixed windows per calendar year, one gzip each under `data/captures/hydromet/<agency>/`, with a manifest per site. On file after the first pull: 59 series, 3,852 windows, 21.6 million readings, no refused windows. LCRA creek and river sites reach back to December 1991 (Bull Creek at Loop 360, Barton at Loop 360, Walnut at Webberville Road, Onion at US 183, the Colorado at Austin, Mansfield and Tom Miller dam levels), Onion at Buda to 2000, Lake Austin gauges to 2003, City sites to October and November 2015. The LCRA hourly series is patchy (whole windows empty where the 15-minute series is complete), so an empty hourly window is asked again at 15 minutes; the Austin creek sites are kept at 15 minutes outright. A priority list (`PRIORITY` in the tool) names the Austin creeks the swim lens cites, the Hill Country rivers and the lake levels; everything else is captured live only.
- The bundle gains `hydromet{sites{'AGENCY:site': ...}, history_coverage, counts}` and `counts.hydromet_sites`. Each site record carries agency, name, type, coordinates, a creek tag, the latest stage, flow, dam head and tail, water temperature, the feed's rain accumulations, freshness, and which history params are on file. Schema stays 1; the field is additive. A City gauge's 0.00 flow is the reading the City publishes, not a verdict; a missing flow stays absent.

## 2026-10-01 (later still) — full records for every live TWDB well
- `data/wells-regional.json` index rule changed to every well with a feed row at most 7 days old (90 wells, was 22). Full records fetched for the other 77; `data/captures/twdb-wells/` grows accordingly. Bundle shape unchanged; more wells gain a 13-month percentile.

## 2026-10-01 (later) — additive: `eaa.critical_period`
- `eaa.py conditions` captures the EAA Aquifer Conditions page (summary table with 10-day averages; Comal springflow daily means since 1927 and San Marcos since 1956; J-17 and J-27 daily highs) and the Critical Period Management page (stated reduction percentages) every day. The stage trigger tables exist only as images; they are captured verbatim and transcribed once into `data/eaa-cpm-stages.json` with image checksums. The bundle's `eaa` block gains `critical_period` (10-day averages, implied stage per indicator from the transcribed table, the EAA's stated reduction, and whether they agree). Schema stays 1; the field is additive.
- Base map: USGS The National Map topo with the National Hydrography overlay (public domain) by default; USGS imagery-topo and CARTO light as alternates.

## 2026-10-01 — repository seeded; bundle schema 1
- Seeded from `saulbanov/austin-swim-map` at its 2026-10-01 `main` (commit history stays there). Collectors, inventories,
  histories (68 discharge + 126 non-flow daily series), versioned captures, ledgers and context moved here; places,
  rules, visit notes and operator checks stayed with the swim map.
- `dist/water-state.json` schema 1: `schema_version`, `generated_at`, `stations{id: name, lat, lon, county, tier, kind,
  live_parameters, latest{param: value, unit, observed_at, fresh_within_1h, age_hours}, context, thresholds, source}`,
  `wells`, `wells_meta`, `lakes`, `eaa{wells, rain_gauges}`, `alerts{alerts, gauges, coverage}`, `captures`, `missing_inputs`.

## Daily runs
- 20261002: stations 218 (126 with a reading within an hour), wells 127, lakes 10, EAA wells 69, EAA rain gauges 85, Hydromet sites 407; EAA critical period: San Antonio Pool implied Stage 3 (J-17 10-day 639.0 ft, Comal 143 cfs, San Marcos 92 cfs), EAA states 35%, agree; Uvalde stable, agree; Hydromet: 407 sites in the feed, 393 fresh within an hour, 67 windows refreshed, no refusals; failures: EAA per-site downloads refused 8 in a row (HTTP 500), stopped as designed; the first bundle of the run carried the previous day's USGS values until `monitor.py readings` was added and the bundle republished.
