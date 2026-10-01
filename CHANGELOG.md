# Changelog

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
