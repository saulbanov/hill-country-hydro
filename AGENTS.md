# hill-country-hydro — agent rules

This repository is the **Central Texas water ledger**: a raw-first, deterministic record of what the
region's official water gauges said, when, and how that compares with each gauge's own past. It is the
L1 (acquisition) and L2 (normalized store + deterministic context) substrate in Saul's reporting-os
layer map. Lenses such as `austin-swim-map` read its published bundle; this repo never decides what a
reading means for a person.

## Standing rules (inherited from the swim project, 2026-09 → 10)
- **Raw before interpretation.** Every provider response is written to `data/raw/` with a `.meta.json`
  (url, retrieved_at, status, sha256, bytes) before anything parses it. Versioned copies live gzipped
  under `data/captures/`. Never hand-edit raw or generated files.
- **Missing is never zero.** A value the provider did not return is absent. A null is dropped, not 0.
- **No color, no verdict, no forecast.** Trend, window peak, seasonal percentile and event thresholds
  describe the station's own record. Rules that turn a reading into a verdict belong to a lens.
- **Ids are frozen.** USGS station numbers, TWDB state well numbers, TWDB lake slugs, EAA site ids.
- **Official sources only; no paid API, no LLM in the loop, no deployment or notifications from here.**
- **No git commits without Saul's explicit OK.** The daily routine's own commits were authorized on
  2026-09-29 and extended to this repo on 2026-10-01.
- **Cloud sessions deliver bytes:** a cloud run exports its raw captures under
  `_cloud-captures/<session>-<date>/` with a spool-format `manifest.jsonl`; a local session restores them.
- **Gentle with providers.** USGS: pause between requests. EAA: 3–4 s pauses, stop after repeated
  refusals, never loop. TWDB: a handful of files a day.

## Where to read first
`hill-country-hydro-system.md` (purpose, layers, decision log, session log, open items), then `README.md`
(the daily chain). `IDEAS.md` lists possible builds; it is not a backlog.

## Layout
- `tools/` collectors (`monitor.py collect/normalize`, `usgs_history.py`, `usgs_series_history.py`,
  `groundwater.py`, `reservoirs.py`, `eaa.py`, `hydromet.py`, `hazards.py`, `weather_validation.py`), inventories
  (`regional_inventory.py`, `station_lists.py`), context (`hydro_context.py`, `event_ledger.py`,
  `reach_geometry.py`), export (`cloud_capture_export.py`, `austin_capture_manifest.py`), and the
  publisher (`publish_bundle.py` → `dist/water-state.json`).
- Regional pilot: `regional_normalize.py` → `regional_analytics.py` (compact store), `regional_history.py` (full records, continuity,
  fixed baseline), `regional_geography.py`, `regional_geology.py`, then the consumer `regional_pilot.py`, `regional_history_package.py`
  and `package_regional_site.py`. Contracts in `docs/REGIONAL_*.md`. All offline.
- `data/` inventories, `history/` daily CSVs, `captures/` versioned gzips, `model/` ledgers and manifests.
- `app/` generated context files and the map page. `dist/` the bundle lenses read.
- `tests/` unittest; run `python3 -m unittest discover -s tests` before any push.

## The bundle contract
`dist/water-state.json` carries `schema_version`, `generated_at`, and per-id blocks for stations,
wells, lakes, eaa sites, hydromet sites and alerts. A lens may read it; it may not write back. Changes to the shape
bump `schema_version` and are logged in `CHANGELOG.md`.
