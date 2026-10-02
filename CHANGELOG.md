# Changelog

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
