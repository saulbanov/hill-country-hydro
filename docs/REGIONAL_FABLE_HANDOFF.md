# Fable continuation: finish the regional water pilot

Continue the existing implementation in `/Users/saulelbein/Documents/Codex/hill-country-hydro` through tested main integration and publication. Incorporate the historical and geological additions below. Do not restart, replace working architecture to match suggested filenames, or treat this handoff as proof that unfinished features have shipped.

Saul requests this handoff for a new Fable session. The preceding session stopped feature work to prepare it. There is a tested, integrated analytic foundation and substantial uncommitted geography/map work to preserve. The regional pilot is **not yet published**.

## Authorization and boundaries

Saul authorizes commits, integration, pushes to hydro main and publication to the existing Site in small tested steps. That authorization continues for this build; do not ask again. Preserve concurrent work, raw records, rules and existing tests. No new dependencies, paid APIs, forecasts, PRs, schedules, notifications, daily-routine changes or messages to other tasks. Acquisition and analysis remain separate. Use bounded free official requests only when necessary, retaining verbatim bodies and retrieval metadata before interpretation. Do not purchase maps.

Use explicit working directories. The initial shell directory may belong to the unrelated news-sifter worktree. Read the hydro `AGENTS.md`, then the latest `hill-country-hydro-system.md`. That system document is the living plan and decision record. This file is an execution entry point, not a competing history log.

Read `docs/REGIONAL_BUILD_MERGE_HANDOFF.md`, the updated `docs/REGIONAL_WATER_MAP_HANDOFF.md`, `docs/REGIONAL_ANALYTICS.md` and `docs/REGIONAL_COVERAGE.md`. Reconcile their requirements with the actual checkout before editing. The older handoff's descriptions of unimplemented regional normalization are historical; that stage now exists.

## Verified starting point

At handoff preparation, `git fetch origin main` and an ancestry check confirmed both local HEAD and `origin/main` at:

`58c2458449f64f761b80ebd8f036c2443f474bc2`

This commit delivers `regional-measurements/v1`, an offline analytic extension. It does not complete the newly added full-history requirement. Recheck remote state at startup; do not reset to this SHA if later work exists.

The integrated files are:

- `tools/regional_normalize.py`: preserved-source adapters for regional USGS, Hydromet, TWDB and EAA records. Reuses the creek layer's temporal, identity and revision primitives.
- `tools/regional_analytics.py`: read-only `Reader`, exact-date/prior-time selection, quantity-compatible changes, seasonal daily discharge references, rank and strict incremental-rain total gates.
- `tests/test_regional_analytics.py`: 18 added regional tests. Existing tests are unchanged.
- `docs/REGIONAL_ANALYTICS.md`, `docs/REGIONAL_COVERAGE.md`, `data/model/regional-normalization-audit.json`, `data/model/regional-coverage.json`: contract and reproducible audits.

The ignored output directory is `data/normalized/regional-analytics/`. It contains `catalog.json`, `observations.sqlite` and `references.json`. SQLite stores indexed series/time/retrieval fields and zlib-compressed JSON records. The catalog verifies the database hash; use the reader rather than introducing provider parsing into the browser.

The integrated replay produced 2,323,349 unique original observations in 2,451 series and 2,001,037 resolved usable numeric observations. The source archive audit counts original rows, including repeated captures; do not confuse those counts with station-days or complete histories. Database SHA-256:

`0a4e8a267b014346431b2edc7b67f92679681955b48a311b49d87a33a9253120`

The full water suite passed **115 tests** again during handoff preparation. The isolated current swim source fetched/applied the unchanged schema-1 bundle and passed **79 tests, one existing skip**, before analytic integration. These results cover the analytic foundation; they do not certify the later uncommitted map or any new history/geology additions. The legacy creek contract and `dist/water-state.json` schema 1 remain unchanged.

## Preserve and finish the uncommitted implementation

Inspect `git status` and diff every file before changing it. At preparation, the following work existed locally:

| Files | Actual state |
|---|---|
| `tools/regional_acquire.py` | Bounded official-source capture helper; acquisition only. Existing captures are reused. |
| `data/captures/documentary/regional-water/` | Verbatim gzipped official responses and metadata for USGS NHD/WBD, channel pagination, reference lake outlines, connecting reservoir paths, and LCRA documentary pages. Do not fetch them again unnecessarily. |
| `tools/regional_geography.py` | Offline geometry derivation, WBD containment, same-name/same-watershed gauge matching and endpoint connectivity report. |
| `app/regional-{channels,basins,lakes}.geojson` | 2,712 channel pieces, six surface subbasins and five named reference lake outlines. No Inks Lake polygon was fabricated. |
| `data/model/regional-geography.json` | Capture hashes, endpoint graph, junctions and limits. Component sizes: 2,656, 28, 25, 2 and 1 pieces. This alone does not certify complete hydrologic routing. |
| `tools/regional_pilot.py` | Public snapshot consumer pinned to the integrated analytic commit; verifies ancestry against `origin/main`. Reads normalized observations, not raw provider fields. |
| `app/regional-snapshot.json` | Generated recent pilot data, selected observations, charts, sources and explicit gaps. |
| `data/model/regional-gauge-associations.json` | Four pilot gauges match the same named NHD channel in the same WBD watershed, 21.4–95.1 m away. These are position associations, not measured reaches. |
| `app/index.html`, `app/regional.js`, `app/regional.css` | First regional interface: continuous context channels, two modes, watershed selection, four quantity tabs, details and a separate regional spring section. JavaScript syntax passes. Browser QA has not run. |
| `app/austin.html` | Copy of the preceding Austin entry page, preserving its prototype. `app/ledger.html` remains the original ledger. |
| Living document and merge handoff | Concurrent planning edits exist. Preserve them and append precise reconciliation/status rather than replacing sections from stale copies. |

The recent snapshot has four river gauges, 154 rain gauges, 37 inventoried TWDB wells and six reservoirs. Selected usable readings are:

| View | Rivers | Rain | Wells | Reservoirs |
|---|---:|---:|---:|---:|
| Storm | 4 | 154 | 0 | 6 |
| Seasonal | 4 | 0 | 19 | 6 |

These zeros describe missing compatible selections, not zero water. The storm well histories chosen by the current consumer do not reach the October 2 endpoint; the seasonal rainfall selection lacks a matching September 30 rolling-total capture. Other source statistics must not be substituted silently. The full-history work may improve the available selections, but only with evidence.

The immutable storm starts September 29, 2026 at 10:35 UTC. Maximum analysis cutoff is October 3 at 12:15 UTC; actual gauge endpoints differ. Storm rain uses rolling 24-hour totals ending at or within 30 minutes before October 2 at 12:00 UTC. Date-only reservoir/well endpoints bracket the event with September 28 and October 2. The seasonal view uses September 30 daily means and September 1–30 changes; that daily comparison precedes the October 1 pulse.

Four saved river maxima for checks against the current artifact: Llano near Junction 35,000 cfs at October 1 16:20 UTC; Llano at Llano 27,500 cfs at October 2 06:45 UTC; Pedernales near Fredericksburg 15.1 cfs at October 2 05:15 UTC; Pedernales near Johnson City 105 cfs at October 2 18:30 UTC. These are largest saved readings at different times, not a simultaneous map or a statement of event rarity.

Five spring records are presented as separate regional context: Barton, Hueco, Jacob's Well, Comal and San Marcos. The inventoried acquired spring stations do not supply a local Llano/Pedernales spring measurement. Do not borrow one as a substitute.

## Required pilot additions: reconcile, then implement

### 1. Expose full usable station histories through hydro and the website

The current normalizer retains USGS/reservoir daily observations from 2006 and other observations from September 1, 2026. Those hardcoded retention gates and full-archive counts **do not satisfy historical exploration**.

Preserve the compact store. Add a reusable full-history reader/output for supported pilot stations using the longest usable preserved records. Station/series partitions, an additional indexed store, or on-demand offline derivation are acceptable. Adapt to the current compressed-record schema and reader boundary rather than replacing them without need. Make historical values inspectable and traceable; not just earliest/latest dates and row counts.

For each supported station/series, report actual span, missing dates/years, statistic, units, quality, original provenance and known or unknown continuity. Keep sensor, location, datum, aquifer assignment, capacity and management changes distinct. Do not stitch different sensors or invent era boundaries. Audit existing manifests against available bodies. There are missing historical Hydromet files referenced by manifests; identify each recoverable or unavailable input. Assess bounded official recovery where necessary; do not launch unrestricted archive acquisition.

Any daily/monthly/yearly aggregates must declare input statistic, coverage threshold and missingness. Do not manufacture daily means from sparsely sampled points. Keep original observations available. Package browser history by station/period so opening the map does not download the entire raw archive or normalized database.

### 2. Separate history selection from the comparison baseline

Allow a user to inspect the full available record and select historical dates/windows. Retain an explicit seasonal comparison reference separately. The existing default is the station's Approved daily means within ±15 calendar days in 2006–2025, with coverage gates, leap-year handling, midrank ties and zero-flow preservation.

Expose reference dates and comparability. A full-history display range must not silently change the percentile denominator. Do not include the evaluated observation in its own reference when an older date overlaps the proposed baseline; define and test the supported historical-comparison policy, or withhold that rank. Do not pool incompatible eras. An old date without observations must become unavailable rather than retaining the latest reading. Daily means cannot rank instantaneous peaks. A growing station network is not evidence of a regional trend.

### 3. Coordinate the water quantities visibly

The current quantity tabs preserve meaning but show one family at a time. Add aligned rain, river, well/spring and reservoir plots or an equivalent readable shared-window view for the selected watershed. Preserve independent units, statistics, time precision and gaps. Make different actual source endpoints visible.

Keep the storm and seasonal modes. Preserve the explicit local spring gap and separate regional context. A well measures local level/head, not aquifer volume. Reservoir storage change is not gauged inflow. Similar timing does not prove recharge, underground connectivity or causation.

### 4. Add bounded sourced geology and a supported section or evidence gap

No geological layer or cross-section has been implemented or acquired by this session. Start with official free TWDB aquifer maps/descriptions and BEG mapping/cross-section sources identified in the full brief. Check local coverage, scale, version, coordinate system, reuse rights and actual accessibility. Preserve captures before deriving geometry.

Include applicable aquifer outcrop/subsurface extent and available formation, recharge-area, confining-unit and fault context. Retain documented provider well aquifer assignments and completion/screen/open intervals where available. Current normalized well metadata has aquifer assignments but lacks screen/continuity certification. A surface polygon cannot establish a well's producing unit. Do not infer underground connections from proximity or from the WBD surface watershed polygons.

Provide a relevant published cross-section or a clearly schematic section supported by cited relationships. A schematic must not invent depths, thicknesses, water levels or flow paths. If suitable free evidence cannot be obtained, document the source/access/coverage checks and show the specific evidence gap in the interface; withhold the unsupported section. A generic “geology unavailable” label without investigation does not close this requirement. Keep interpreted geology visually distinct from measured readings and surface watersheds.

### 5. Finish geography, public packaging and interface verification

Preserve the continuous channels. Check the network's disjoint components, direction codes, tributary junctions and connections through managed lakes; record unresolved paths. Verify the stated Llano→Lake LBJ and Pedernales→Lake Travis associations against captured geometry/official evidence, not proximity. The current page states them, but a dedicated receiving-reservoir route validation has not been completed. Reference lake polygons are geographic context, not current inundation.

Known unfinished work:

- `app/index.html` links to `docs/REGIONAL_GEOGRAPHY.md`, which does not yet exist. Write it from verified evidence or replace the link with an included valid equivalent.
- `tools/package_creek_site.py` still packages the old creek-only asset list. Extend or add a public-only packager for the regional page, history partitions, geology/context, Austin prototype and original ledger. Do not run the old packager and assume the regional site is complete.
- Check local-preview versus published-root paths for all docs, scripts, data and older-page links.
- Add focused geometry, artifact, history and geological-assignment tests. No regional consumer tests existed at handoff preparation.
- Complete BrowserOS desktop/narrow checks: continuous recognizable rivers, uncluttered labels, both modes, quantity coordination, historical controls, unavailable selections, exact source values, geology evidence, and access to the older pages.
- Publication date is generated by the consumer build; regenerate or set it to the actual publication date. Keep it separate from measurement cutoff.

## Ordered execution and acceptance

1. Inspect the current repo, remote and concurrent changes. Update the reconciliation table already appended to the system document. Treat partial local work as work to finish, not delivered functionality.
2. Implement and test the full-history/continuity reader and any needed analytic corrections. Preserve the recent fast path. Add source-grounded geological metadata without conflating interpretation with measurement.
3. Run the full hydro suite and full swim suite against the resulting bundle **in an isolated copy** of the current swim source. Do not write to the working swim checkout. Existing successful checks are only a baseline for unchanged inputs.
4. Commit/integrate/push additive analytic changes. Verify their exact commit or ancestry on a freshly fetched `origin/main`. Replay offline outputs from integrated code before pinning/consuming the new analytic revision in the website. Do not amend or rewrite `58c24584`.
5. Complete the history, coordinated plots, geology and map consumer. Check representative historical observations and geological attributions directly against their preserved source locators. Add tests for old values outside recent cutoffs, missing years, continuity boundaries, baseline/range separation, no future substitution, unsupported aquifer assignments and network connectivity.
6. Run final full water and isolated swim suites; perform desktop/narrow BrowserOS checks. Integrate and verify the map commit on `origin/main`.
7. Publish the validated public package to the existing Site and verify successful deployment and the actual published page. Record what is live, commits, suite results, remaining gaps and the opening screen's claims in the living document. Do not claim browser rendering proves Saul finds the map comprehensible.

## Existing Site: keep identity and audience

- URL: `https://hill-country-hydro.saul-elbein.chatgpt.site`
- Site ID: `appgprj_6ac12765acb88191a74ce6c2570385f5`
- Publishing checkout: `/Users/saulelbein/Documents/Codex/hill-country-hydro-site`
- `.openai/hosting.json`: the same project ID, static directory `out`, not-found handling `none`.
- Native Site read confirmed active status, public audience and version 2. The online version is still the earlier Austin prototype; no regional save/deploy call has occurred.
- The Sites opening workflow synchronized the existing publishing checkout at source commit `1ed6aaf7761ba89314c21bacfa6b3b2cd99c3e3f`. No regional files have been packaged into that checkout. Reopen/sync safely through the installed Sites building/hosting skills and obtain fresh short-lived credentials; never copy credentials into files or this handoff.

Retain `/austin.html` for the Austin prototype and `/ledger.html` for the original ledger. Package only required public assets/derived values, with included or official provenance links. Never publish raw captures, SQLite, private paths, credentials or repository metadata. Do not create a replacement Site or change its audience. No automation is requested.

A local development server was started for the hydro root on `127.0.0.1:8766`; its lifetime is not guaranteed across sessions. The local regional route is `/app/`. Reuse only if it still serves this checkout. No browser preview or screenshots were completed before the handoff request interrupted feature work.

## Extension plan: record, do not make all of it a pilot prerequisite

Keep these stages in `hill-country-hydro-system.md`, with explicit deliverables and status:

1. Historical storm/drought comparisons: comparable rain distribution/intensity and starting conditions; lags, persistence, zero-flow periods, well/spring/storage changes, coverage and continuity. Deliver reproducible comparison artifacts and an explorer; distinguish gauged volume from basin-wide runoff.
2. Added explanatory measurements: audit TexMesonet soil moisture, LCRA releases/operations, TWDB evaporation and documented pumping/withdrawals against specific unresolved questions. Distinguish observed, modeled and estimated quantities; do not invent a closed water budget.
3. Deeper geology and additional basins: supported aquifer subdivisions, completion intervals, confining relationships and published spring/stream connections; audited Guadalupe, Blanco and Medina views. Deliver an evidence-backed association catalog and basin consumers, not an unsupported groundwater simulation.
4. Documentary/paleoclimate history: dated accounts, historical maps and infrastructure changes, then suitable tree-ring, sediment or cave-deposit reconstructions. Retain variable, geography, season, resolution, dating/calibration uncertainty and evidence class. Do not turn drought proxies into invented historical creek discharge or silently fill gauge gaps.

Finish with the live website link, verified analytic integration commit(s), map commit, actual test results, what the reconciliation changed, and specific remaining limitations. Identify any blocked pilot requirement with observed evidence. Do not present these extension stages as delivered features.
