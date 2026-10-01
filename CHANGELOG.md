# Changelog

## 2026-10-01 — repository seeded; bundle schema 1
- Seeded from `saulbanov/austin-swim-map` at its 2026-10-01 `main` (commit history stays there). Collectors, inventories,
  histories (68 discharge + 126 non-flow daily series), versioned captures, ledgers and context moved here; places,
  rules, visit notes and operator checks stayed with the swim map.
- `dist/water-state.json` schema 1: `schema_version`, `generated_at`, `stations{id: name, lat, lon, county, tier, kind,
  live_parameters, latest{param: value, unit, observed_at, fresh_within_1h, age_hours}, context, thresholds, source}`,
  `wells`, `wells_meta`, `lakes`, `eaa{wells, rain_gauges}`, `alerts{alerts, gauges, coverage}`, `captures`, `missing_inputs`.
