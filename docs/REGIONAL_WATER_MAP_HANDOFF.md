---
title: Expand the Water Ledger by watershed
created: 2026-10-03
status: ready for execution when invoked by Saul
scope_updated: 2026-10-03 — full historical records and geological strata added to pilot; extension stages defined
---

# Regional water map — execution handoff

## Outcome

Extend the integrated hydro analytic layer, then publish a watershed-based view of the Llano and Pedernales rivers and their connections to the Highland Lakes. Use the existing rain, river, spring, well and reservoir records to explain both a storm response and longer water conditions. Finish with working, tested code on hydro main and an updated version of the existing Site. A plan or an unpublished branch does not complete the execution task.

Saul's review of the Austin prototype: an acceptable start, but the creeks look like splotches rather than lines. The next map must make recognizable river channels the visual subject. Short, thick gauge-location strokes were a conservative design choice, not a requirement imposed by point observations. Draw connected channels clearly while distinguishing geographic context, measured values at gauges and any supported reach estimates. Do not solve the presentation problem by claiming that one gauge measures an entire river.

The reader should be able to answer:

- Where did rain fall during the selected period?
- Which rivers rose or remained low, and how unusual were their daily flows for the season?
- What changed in the available spring and groundwater records over a longer period?
- How did reservoir storage change, and what remains unknown about the causes?
- How does the selected period compare with the longest usable station record, and which changes in measurement or management limit that comparison?
- Which mapped formations and aquifer units provide context for the observed water behavior, and which underground connections remain unproven?

## Start from the delivered work

Source repository: `/Users/saulelbein/Documents/Codex/hill-country-hydro`.
Remote: `https://github.com/saulbanov/hill-country-hydro`.
Use explicit working directories; an unrelated news-sifter worktree may be the session's initial cwd. Verify the repository root and inspect uncommitted work before editing or syncing. Preserve the existing discussion notes and this handoff.

Read:

1. `AGENTS.md`, `hill-country-hydro-system.md` and this file. The system document is the single living plan, decision log and progress record.
2. `README.md`, `docs/CREEK_ANALYTICS.md`, `docs/CREEK_COVERAGE.md` and the tests for the existing creek layer.
3. `tools/creek_normalize.py`, `tools/creek_analytics.py`, `tools/creek_prototype.py`, `tools/package_creek_site.py` and `data/model/creek-display-policy.json`.
4. Relevant collectors/parsers: `tools/hydromet.py`, `tools/groundwater.py`, `tools/reservoirs.py`, `tools/eaa.py`, the USGS history tools, `tools/hydro_context.py` and `tools/publish_bundle.py`. Inspect saved manifests, inventories and records before deciding that another acquisition is needed.
5. The installed Sites building/hosting skills before publication and BrowserOS instructions before browser checks.

The earlier `docs/NORMALIZATION_AND_CREEK_PROTOTYPE_HANDOFF.md` is historical build context, not a request to repeat that completed build. Reusable normalization reached main in `a07b067557b9e90bf8df17cfaf42b6b41c042b26`, with metadata correction `0579c6869e0b22b60cfb9999a94dfc94c8f95396`; the map consumer followed in `f49cac0f2e732680760bbc750feb58a5af2d6220`. Verify ancestry against current main rather than checking out those old commits.

`creek-measurements/v1` currently adapts a bounded Austin discharge/stage selection. Its original timestamps, units, qualifiers, source hashes, duplicate evidence and conflicts are reusable foundations. Rain, groundwater and reservoir adapters are not already implemented by that contract. The browser must consume derived output, never reinterpret provider fields independently.

## Scope and sequence

Audit existing regional records first. Implement reusable adapters for regional river discharge, rainfall, groundwater, spring discharge and reservoir observations where preserved inputs support them. Keep unsupported records in the audit with reasons. Do not make complete recovery of every source a prerequisite for the pilot, or silently reduce the work to another river-only map.

The first detailed geographic view covers the Llano and Pedernales watersheds and the relevant Highland Lakes connections. Verify each tributary's actual receiving reservoir and the intervening network; geographical proximity is not connectivity. Include groundwater or spring observations in that pilot only where inventory and source evidence support their location and relevance. A lack of suitable local spring records is a visible coverage gap, not a reason to borrow an unrelated spring. Regional well/spring records can remain available in a clearly separate regional context view.

The October 3 scope update adds full-record historical exploration and a bounded geological context layer to the pilot. The extension stages below cover deeper historical reconstruction, more detailed underground relationships and additional basin views. They are an ordered build plan, not prerequisites for publishing the pilot or an instruction to execute every extension in the current run.

Concurrent implementation may already exist. Inspect `tools/regional_normalize.py`, `tools/regional_analytics.py`, `docs/REGIONAL_ANALYTICS.md` and the latest system entries if present. Extend and test that work rather than replace it. A recent-window normalized store is a useful fast path, but it does not satisfy the new full-history requirement by itself. Preserve other sessions' edits; record the needed integration changes in the living document.

### 1. Coverage and identity audit

Save a reproducible report with counts and gaps by basin, provider, quantity, station, year and sampling interval. Inventory entries are not evidence that usable measurements exist. Check actual numeric records, quality flags and acquisition metadata.

The living document records 68 daily discharge histories, histories for 90 live TWDB wells, ten reservoir histories, Hydromet rain/river records and EAA well/spring records. Recheck these counts. Some EAA inventory entries have no acquired data; some detail captures lack original retrieval sidecars. Preserve and disclose such gaps. `IDEAS.md` has stale coverage claims, including 22 wells; reconcile those factual claims with the audit without turning its suggestions into mandatory scope.

Select a saved storm with overlapping pilot coverage, preferably the existing October event if supported. Record the actual window, observation cutoff and exclusions. Do not alter immutable storm files to fit a display label. Separately select a common complete day or longer window for seasonal conditions; do not show each station's latest value as though all were simultaneous.

For every pilot station, inventory the earliest and latest available observations, usable years, gaps, changes in statistic, sensor, location or datum, and documented changes in dam operations or capacity. Distinguish unknown continuity from verified continuity. Assess whether preserved captures cover the provider's documented record; use bounded official acquisition to recover missing older records when necessary and available. Do not equate a capture's first row with the first measurement ever made. Record older records that are unavailable or require manual recovery.

### 2. Extend normalization in hydro and integrate it first

Preserve the current contract or introduce an explicitly versioned successor with documented compatibility. Keep the existing creek output reproducible. Store analytic records and deterministic statistics in hydro; visual color/width policy belongs to the map consumer. Preserve the schema-1 water bundle unless a separately justified, tested migration is necessary.

Resolve these quantity-specific contracts from evidence:

| Quantity | Required distinctions |
|---|---|
| Rain | Incremental versus cumulative versus rolling totals; interval boundaries, time zone, resets, missing intervals and coverage. Never sum overlapping rolling totals or equate one gauge with basin-wide rainfall. |
| River/spring flow | Discharge versus stage; instantaneous versus daily mean; original sensor and operator. Hourly spacing does not establish an hourly mean. |
| Groundwater | Depth below land surface versus water-level elevation; units, sign/direction, vertical datum, aquifer and screen metadata when known. Daily highs are not daily means. Do not pool raw elevations across wells. |
| Reservoirs | Elevation versus storage volume versus percent of a stated capacity; capacity definition/version, dates and managed operations. Do not infer volume from elevation without a sourced relation. |

Retain original identities, observation/retrieval times, qualifiers, missingness, provenance and revisions. Extend verified alias handling without collapsing nearby stations or different sensors. Date-only records must remain date-only. No artificial interpolation, gap filling, zero substitutions or undocumented time precision.

Provide offline commands, documented output schemas, a reader interface, source/coverage reports and tests. Large regenerable artifacts may stay ignored, but source pointers and archive restoration requirements must make reproduction possible. Normalization must not fetch data or depend on the website.

Add a full-history output or reader path for the supported pilot stations, reaching back through the longest preserved usable record. Recent event data may remain a compact separate artifact. Retain original observations and generate documented daily/monthly/annual summaries only where the source statistic and coverage allow them. Package historical data by station or period so the initial map need not download the entire archive. Counts of older observations without inspectable historical values do not meet this requirement. The integrated hydro layer owns historical computation and continuity metadata as well as recent readings.

Run the full required water and swim suites, commit the tested analytic extension, integrate/push main under the execution prompt's authorization and verify the commit on `origin/main`. Record the commit and rerun the offline build from integrated code before building its website consumer.

### 3. Geography and defensible comparisons

Acquire the smallest required official channel network and basin/catchment geometry after inspecting available captures. Candidate source: [USGS 3DHP and legacy hydrography products](https://www.usgs.gov/3d-hydrography-program/access-3dhp-data-products). Check local coverage, topology, coordinate systems, attribution and usage terms. [Hydrographic addressing](https://www.usgs.gov/3d-hydrography-program/hydroadd3d) can establish a network location; it does not establish a representative flow measurement along a reach.

Preserve acquired responses and metadata before deriving simplified geometry. Record gauge-to-network matches, confidence/evidence, tributary junctions, dams, flow direction and unresolved matches. Simplification must preserve connections needed by the display. Do not attach a point to the nearest line across a divide.

Use each station's own seasonally comparable history. Daily flow ranks require daily flow observations; storm peaks need matching instantaneous history to claim an instantaneous rank. Define a reference period, seasonal window, minimum year/record coverage, leap-day handling, tie convention and treatment of zero-flow days. Generalize beyond the old October-only reference. Publish counts and gaps; avoid comparing ranks across silently different reference periods. Zero medians must never acquire invented denominators.

Wells, springs and lakes need their own compatible statistics and continuity checks. Well levels can reflect pumping as well as recharge; reservoir storage reflects releases, withdrawals and other inflows as well as rainfall/runoff. Juxtaposition can show timing without proving causation. Do not make a regional aquifer index by averaging unlike wells, or label a storage increase as measured river inflow.

#### Historical and geological strata required in the pilot

Keep the full historical record separate from the reference period used to define usual. Provide an explicit fixed recent reference where coverage supports it, plus full-record exploration. Document the reference dates and show historical eras or breaks only when evidence supports them: station/datum changes, reservoir construction, capacity revisions or operating changes. Do not pool incompatible eras into an unlabeled percentile. Missing stations in an earlier year must appear as unavailable; changes in network coverage must not become a regional trend.

Add sourced aquifer outcrop/subsurface boundaries and available formation, confining-unit, recharge-area and fault context within the pilot. Begin with official, freely accessible sources such as [TWDB aquifer maps and descriptions](https://www.twdb.texas.gov/groundwater/aquifer/index.asp) and [BEG geological mapping](https://www.beg.utexas.edu/research/areas/geologic-mapping). Audit resolution, license/access, coordinate system, version and geographic coverage; some map products require purchase and are outside authorization. Preserve source captures separately from derived geometry.

For mapped wells, retain provider aquifer assignments, completion depth and screen/open intervals where documented, along with source and confidence. A surface formation polygon does not identify a well's producing unit. Surface watersheds and underground flow systems remain distinct; proximity and simultaneous changes do not prove a spring–well or stream–aquifer connection. Show uncertain or absent assignments explicitly.

Include at least one published geological cross-section relevant to the pilot, or an explicitly schematic section derived from cited stratigraphic relationships. A schematic must not invent layer depths, thicknesses, groundwater levels or pathways. If no suitable free evidence exists, record the specific gap and withhold the section; an unsupported 3D model is not a substitute. Distinguish mapped/interpreted geology from instrument observations in the legend and details.

### 4. Build the watershed view

Provide two clearly named modes: **What did this storm do?** and **How wet or dry is the region?** Use a common selected time/window within each view and show freshness or missingness per source. Supported windows can differ between modes; disable unsupported comparisons rather than inventing them.

Draw continuous, named river channels clearly at the initial regional zoom. Use restrained width and sufficient line length so the result reads as rivers rather than blobs. Give unmeasured geography a distinct neutral treatment. Anchor observed conditions to gauges; any inferred reach treatment needs explicit limits and a visible distinction. Neither symbolic width nor color depicts inundation, literal channel width, safety or a forecast.

Coordinate rain, streams, groundwater/springs and reservoirs through the selected watershed and time window. Avoid an opening screen dominated by agency checkboxes or overlapping symbols. Rain points must not imply measured spatial coverage between gauges. Aquifer boundaries, if used, are distinct from surface watersheds. Show reservoir storage separately from river discharge. Allow the user to follow the channels and select details with actual values, a time series, historical context, missingness and sources.

Selecting a basin should align separate rain, river, well/spring and reservoir plots on a shared time axis, with their own units and observed coverage. Include a full-history range and a coverage timeline for supported stations; selecting an old date must never retain a current reading. Keep historical range and comparison-baseline controls distinct. Provide geology as a readable optional layer and a linked section/context panel, without obscuring channels or implying underground measurements. Users must be able to distinguish an observed reading, a calculated comparison and a geological interpretation.

Keep both the existing Austin creek prototype and full ledger reachable. The website remains a dated, manually published snapshot; local collection does not automatically refresh it. Display the saved-data cutoff and publication date separately.

### 5. Verify and publish

Add focused tests for real failure cases: rain totals/reset/interval overlap; unit and datum mismatch; well direction; storage versus elevation; date-only data; duplicates and revisions; partial history and zero-flow ties; temporal alignment; unsupported associations; and geometry connectivity. Preserve all existing rules and tests. Verify selected UI values against normalized records and representative raw-source locators.

Also verify earliest supported historical values, gaps and era boundaries, full-history retrieval independent of recent-store cutoffs, coverage-aware aggregation, baseline selection without silently pooling incompatible eras, and old-date selection without future readings. Test that missing well completion metadata does not become a geological assignment. Check historical timelines, geology legends and any cross-section at desktop and narrow widths. Verify a historical observation and geological attribution against their retained sources.

Run `python3 -m unittest discover -s tests` in hydro and the full sibling swim suite against the resulting bundle in an isolated copy. The previous delivery passed 97 water tests and 79 swim tests with one existing skip; report new actual results. Do not modify the working swim checkout or its data to run integration checks.

Inspect desktop and narrow layouts in BrowserOS. Check readable continuous channels, labels, legends, unsupported conditions, both time modes, details, provenance links and access to the older pages. Describe what the opening screen establishes without clicks. Technical rendering checks do not substitute for Saul's later comprehension review.

Publish through the current Sites workflow to:

- URL: `https://hill-country-hydro.saul-elbein.chatgpt.site`
- Publishing checkout: `/Users/saulelbein/Documents/Codex/hill-country-hydro-site`
- Existing Site ID: `appgprj_6ac12765acb88191a74ce6c2570385f5`
- Manifest: `.openai/hosting.json`, currently static directory `out`.

Confirm the current manifest, sync safely and preserve the Site identity and audience. Package only required public assets and derived data. Never publish raw archives, SQLite, private paths or credentials. Public provenance links must resolve to included files or official sources. Verify successful deployment and the actual published page.

## Extension build plan after the pilot

Complete and assess the pilot before these stages. Keep progress and any reordering in the living system document; do not create separate dated plans. Each stage retains the offline hydro-first integration, tests, provenance and existing-Site publication discipline. No new collection routine or paid source is implied.

1. **Historical storm and drought comparisons.** Compare past events and sustained low-flow periods using the longest compatible records. Examine rainfall distribution/intensity, starting conditions, lag to the largest saved flow, duration of elevated or zero flow, and well/spring/storage response. Integrate discharge to volume only over adequately observed intervals. Report station cohorts and coverage, account for documented measurement/management changes, and keep associations distinct from causal conclusions. Deliver a reproducible event-comparison artifact and explorer.
2. **Conditions before storms and managed water movements.** Audit TexMesonet soil moisture, LCRA releases/operations, TWDB reservoir evaporation and documented pumping/withdrawals. Prioritize sources that resolve a specific pilot uncertainty. Preserve observed versus modeled/estimated values and their intervals. Do not claim a closed water budget where spatial rainfall, removals or other terms are missing. Deliver tested adapters and comparisons of the relevant periods.
3. **More detailed geological relationships and additional basins.** Add supported well completion intervals, published aquifer subdivisions, confining relationships and cross-sections; use studies to establish or qualify connections among wells, springs and gaining/losing reaches. Expand to Guadalupe, Blanco and Medina views after auditing their coverage. Compare within defensible geological and hydrologic groups rather than pooling unlike wells. Deliver a sourced association catalog and basin views; no unsupported groundwater simulation.
4. **Documentary and reconstructed history before instruments.** Add cited historical flood/drought accounts, maps and documented infrastructure changes. Evaluate relevant Texas tree-ring, sediment and cave-deposit reconstructions for older climate context. Preserve each reconstruction's variable, season, spatial extent, dating uncertainty, calibration/validation and temporal resolution. Keep documentary events, reconstructed climate and measured water records in separate evidence classes; never turn a drought index into an invented creek discharge or fill instrument gaps with unlabeled proxies. Deliver a contextual timeline with sources and uncertainty, not a seamless synthetic gauge record.

Useful starting references: [USGS streamflow trend methods and periods](https://apps.usgs.gov/trends/sw-flow/), [Texas paleoclimate research](https://pubs.usgs.gov/publication/70155521), and [USGS guidance on reconstruction limits](https://pubs.usgs.gov/circ/1331/Circ1331.pdf). These identify research paths; local suitability and accessible source data still require inspection.

## Constraints and completion

No new dependencies, paid APIs, forecasts, PRs, schedules, notifications or daily-routine changes. No LLM in the measurement pipeline. Acquisition and deterministic interpretation remain separate. Make bounded official requests only when existing inputs cannot supply required evidence; preserve raw bodies and metadata, honor provider pauses and stop on refusal.

Resolve routine choices from evidence and record them in `hill-country-hydro-system.md`. Preserve concurrent changes and avoid destructive Git operations. This file alone does not launch work or authorize messages to other tasks. When Saul invokes the execution prompt, its scoped commit, integration, push and publication authorization applies; do not ask for it again. Broader work remains outside scope.

Track completion in the living document:

- [ ] Regional coverage/identity audit and supported pilot window established.
- [ ] Reusable quantity-specific normalization, offline commands, contract and tests delivered.
- [ ] Analytic extension integrated into hydro main, pushed and verified on origin/main after full suites.
- [ ] Channel/basin geography and gauge associations sourced and checked.
- [ ] Matched historical comparisons and unsupported outcomes documented and tested.
- [ ] Full available pilot-station histories exposed through an offline hydro output/reader and website timeline; gaps and continuity limits retained.
- [ ] Historical display range and fixed comparison baseline are distinct; earlier dates show actual coverage without current-value substitution.
- [ ] Sourced geological/aquifer context, well assignment evidence and a supported cross-section or explicit source gap documented and displayed.
- [ ] Watershed pilot consumes integrated outputs; all four data families are represented or have explicit coverage gaps.
- [ ] Continuous lines, time modes, evidence details and preserved pages checked on desktop and mobile.
- [ ] Final water/swim suites pass; consumer code integrated and verified on origin/main.
- [ ] Existing Site updated; successful deployment and published content verified.
- [ ] System document records commits, results, limitations and the four extension stages without implying they are already built.

Finish with the website link, analytic integration commit, map commit, test results and remaining limits. If a stage is blocked, identify the observed blocker and leave that deliverable unchecked. Do not claim a geographic association proves reach-wide conditions or that publication proves the map is comprehensible.
