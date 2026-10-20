---
title: Normalize the water sources, then build the creek prototype
purpose: Architecture and implementation handoff for the Central Texas Water Ledger
created: 2026-10-03
status: ready-to-use
---

# Normalize the sources, then build the creek prototype

Copy the prompt below into a fresh session in `hill-country-hydro`, or ask that session to read this file and execute it. This is the execution brief. Keep evolving decisions, progress and blockers in `hill-country-hydro-system.md`; do not create another dated plan.

---

## Mission

Architect and implement the next version of the Central Texas Water Ledger in two stages: **cross-provider normalization first, then an online creek-map prototype that consumes that normalized output.** Complete the architecture decisions needed for each stage, document their evidence, implement, test, and publish the prototype to the existing Site. A design document alone does not complete this brief. The normalization work must be integrated into `hill-country-hydro` main as a reusable **prototype analytic layer**, with code, tests, a documented contract and a reproducible command. A working branch or deployed map alone does not complete it.

Saul's entry question is “What did this storm do?” Understanding the region's water over months and years is the larger project. He wants to look at the map and see “the creeks all swollen”: the creek lines themselves should communicate departure from their usual condition through thickness or color. The definition of usual and the visual scale are still open decisions.

The present map does not accomplish that. It opens with agency checkboxes and “Pick a marker.” Enabling Storm changes adds hundreds of overlapping symbols and a long methods paragraph. The previous build demonstrated that data and symbols were present, but did not demonstrate that a person could understand the storm by looking at the page.

Success: a reader can recognize which named creek stretches showed elevated measurements, at what time, and relative to what baseline, without first clicking individual gauges. Clicking exposes the measurements and their sources. The display must also make unavailable comparisons recognizable.

## Read first and locate the work

Mac source repository: `/Users/saulelbein/Documents/Codex/hill-country-hydro`.
Cloud location if available: `/home/user/hill-country-hydro`.
Remote: `https://github.com/saulbanov/hill-country-hydro`.
The unrelated news-sifter worktree sometimes supplied as the session cwd is not this project. Use explicit working directories and verify the repository with `git rev-parse --show-toplevel`.

Read in this order:

1. `AGENTS.md`, then `hill-country-hydro-system.md`: standing rules, the latest product discussion, unresolved issues and existing publishing instructions.
2. This handoff. The user-approved direction is normalization followed by a creek-based online prototype; metric and geometry policies below are questions to resolve, not existing decisions.
3. `README.md`, `HANDOFF_2026-10-03_storm-delta-map.md` and `data/model/storm-delta-validation.json`: the existing chain, previous build and discrepancies. The old handoff contains superseded example readings; use the current source record rather than forcing those examples to match.
4. `tools/monitor.py`, `tools/hydromet.py`, `tools/usgs_series_history.py`, `tools/usgs_peaks.py`: acquisition, source identities, fields, metadata and normalization.
5. `tools/hydro_context.py`, `tools/event_ledger.py`, `tools/storm_delta.py`, `tools/reach_geometry.py`: existing deterministic context and geometry limits.
6. `tools/publish_bundle.py`, `app/index.html`, `app/map.js`, `app/austin-creeks.geojson`, the relevant inventories under `data/`, and existing tests.
7. The applicable architecture and build skills when available. For browser inspection use the BrowserOS skill. Before changing the hosted Site, read the installed Sites building and hosting skills and follow their current workflow.

Inspect branch status and concurrent changes before syncing or editing. Preserve uncommitted work. At handoff creation, `hill-country-hydro-system.md` already has uncommitted product-discussion notes belonging to this session; this handoff is also new. Do not discard either.

## What exists and what remains unproven

- USGS observations contain original station and series IDs, parameter, unit, observation time, retrieval time, qualifiers and raw path.
- Hydromet history uses agency/site/param, `value1`, `value2`, observation time, an hourly flag and source reference. Capture headers and manifests carry additional field descriptions. Read those descriptions; a positional field name is not a unit definition.
- The Hydromet all-sites feed includes LCRA, City of Austin and mirrored USGS sites. These are not necessarily independent measurements. Names or nearby coordinates alone do not establish duplicates.
- Seasonal context already computes station-specific daily-flow medians and percentiles within the existing ±15-day calendar window. That does not establish an equivalent instantaneous reference distribution.
- Saved Austin geometry has 86 waterway LineStrings covering Barton, Blunn, Bull, Onion, Shoal, Walnut and Williamson creeks. This is a candidate prototype area, not a promise that all seven have adequate comparable records.
- `reach_geometry.py` locates points along saved ways. Its contract explicitly says it does not establish a hydrologic relationship. Existing creek tags can group names, including tributaries, and are not sufficient evidence for assigning measurements to a channel segment.
- The current public Site is a manually published snapshot. Existing local collection does not automatically refresh that Site. Keep the actual observation cutoff visible; do not call the prototype live.

## Stage 1 — normalize the intakes

First audit saved data and produce a compact source/coverage table for the candidate creeks. Include provider, original site/series identity, measurement type, units, datum where relevant, sampling and aggregation, record coverage, qualifiers, duplicate evidence, raw provenance and suitability for the proposed comparison. Show counts and gaps by source and creek; aggregate totals alone are insufficient.

Design and implement a deterministic derived measurement representation owned by hill-country-hydro that both the map prototype and other analytic consumers can read. Preserve the original archives, inventories and source-specific records. Reuse existing normalization where sound; do not build another collector to solve a schema problem.

Resolve and record these questions:

- Which fields distinguish the original operator, the distributing feed, the physical gauge and the individual measurement series? How are verified aliases represented while retaining original IDs?
- How are units, vertical datums, observation time, retrieval time, time zones, date-only records and interval start/end represented? Preserve unknowns rather than supplying fictitious precision.
- What establishes that a Hydromet row mirrors a USGS reading? How is a preferred display series selected, and how are disagreements and alternate observations retained? Do not average duplicate feeds or silently stitch different sensors.
- Which records are instantaneous, daily means, accumulated totals or another statistic? Hourly spacing alone does not establish an hourly mean. Stage, discharge, lake elevation and depth below ground remain different quantities even when some share feet as a unit.
- How will missing, stale, rejected, provisional and insufficient-history states propagate into the display? Distinguish measured zero from no observation.
- Where within hill-country-hydro will the derived records, identity evidence, report and reproducible command live? Decide whether a separately versioned analytic artifact or a bundle extension best preserves consumers. Either choice is part of the hydro repository and its documented public contract, not a map-only or publishing-checkout implementation. The previous schema-1 exception for `storm_delta` does not authorize every future schema change.

Scope the implemented adapters to the USGS and LCRA/City creek measurements needed for this prototype, with coverage and exclusions explicit. Design the record so later rain, spring, well and lake work is possible without falsely treating those measurements as interchangeable. Do not turn this into a migration of every historical source before anything can be seen.

Normalization is offline. If source metadata is genuinely missing, identify the smallest acquisition needed, preserve its raw body and sidecar, and only then analyze it. Keep provider pauses, record refusals, and avoid retry loops. Python standard library only; no new dependencies or paid API calls.

Stage 1 is complete when every selected display input traces to an original observation, units and temporal meaning are explicit, duplicates and conflicts have a documented treatment, and fixtures verify the important failure cases. Save the coverage report even when some sites remain unsupported.

### Required integration into hill-country-hydro main

Saul explicitly requires: “Normalization layer must merge as a prototype analytic layer in hill country hydro too, not just get lost in this branch.” Treat integration as a separate deliverable from the online prototype.

- Keep the normalization implementation, tests, identity evidence and schema/contract in the source repository. Document its prototype status, supported sources, limitations, inputs, outputs and offline invocation in the README and system layer table. Update the changelog for the new analytic contract.
- Give other consumers a stable, documented way to read its output without running the website or importing map JavaScript. Large regenerable stores may remain ignored under existing repository conventions, but the committed code, source references and instructions must reproduce them from the preserved inputs.
- Integrate the completed normalization stage into `hill-country-hydro` main after the full water and relevant swim suites pass, independently of whether the visual prototype is finished. If a working branch is used, merge its tested changes; if working directly on main, commit the tested stage there. Push the completed stage and verify that the integration commit is present on `origin/main`. No PR is required or requested.
- Record the integration commit, validation counts and reproducible command in the system document. Verify the analytic output can be generated from the integrated code. The map stage must consume this integrated layer; it must not retain a divergent branch-only copy.
- If integration is blocked, preserve the work and report the specific blocker and unmerged commit. Leave integration unchecked. A branch, local commit or public deployment is not evidence that the analytic layer reached remote main.

## Stage 2 — choose the comparison and build the prototype

Use one recorded October storm and a small set of supported named Austin creeks for the first visual test. Verify the actual saved window and coverage; do not change the immutable storm detection files to fit calendar labels. Keep July as a useful later comparison only where its inputs support the same method.

Resolve these design questions using the audited records:

1. **What does usual mean?** Compare candidate seasonal medians, percentiles or another defensible measure on the selected creeks. Explain what each preserves or hides. A percentile expresses historical position, not a proportional amount of excess flow. Ratios become undefined when the baseline is zero. Do not hide either problem with an invented denominator.
2. **Are time scales comparable?** Decide how instantaneous storm readings and historical reference data can be compared. A 15-minute value against daily means must not be presented as an instantaneous historical rank. If adequate matching history is unavailable, constrain or label the comparison, or show an explicitly separate event-relative view.
3. **What stretch does a gauge represent?** Record geometry source, station association, limits and evidence. Do not spread one reading through an entire watershed, across tributary junctions, or between gauges without a defensible rule. Unsupported stretches remain identifiable as unsupported. A nearby coordinate is not enough.
4. **What does the line encode?** Choose thickness, color or a combination with a legible scale, including ordinary, elevated and unavailable conditions. Document any display transform or cap. Symbolic width represents a measurement comparison, not literal channel width, inundation extent or a safety category. Do not add red, green or yellow storm verdict colors.
5. **How does time work?** Consider a single-time display with before/peak/after controls or a time slider. This is a design choice, not a requirement to animate. If using time controls, keep all visible measurements tied to the selected time, disclose sampling differences, and leave gaps rather than interpolating unsupported readings. A display of each creek's separate peak must say that the peaks occurred at different times.

Build a first screen with named creeks, recognizable geography, a short explanation of the encoding, the selected time and the saved-data cutoff. Agency names and the full source audit belong in details. Clicking a creek should reveal the measurement, comparison basis, a simple time series where available, and provenance. Source gauge markers can be inspected without dominating the opening view. Preserve access to the existing ledger and its evidence.

The interface must consume the common normalized representation. Provider-specific interpretation belongs upstream, not in separate JavaScript branches that quietly assign different meanings to the same line thickness.

## Verification and failure cases

Add focused tests; preserve existing tests and measurement rules. Cover equivalent units, unknown units/datums, ambiguous or date-only times, missing versus zero, verified mirrors, conflicting duplicates, multiple sensors, sampling/aggregation mismatch, insufficient history, zero baselines, temporal gaps and unsupported geometry. Test whichever of these the implementation actually handles, with explicit unsupported outcomes for the rest.

Run `python3 -m unittest discover -s tests` in the source repository. Verify the sibling swim consumer against the resulting bundle, preferably in an isolated copy so its working data is not replaced. On this Mac it lives at `../swimming-hole-alerts`; elsewhere it may be `../austin-swim-map`. The last recorded baseline was 70 water tests and 79 swim tests with one existing skip; rerun and report actual counts rather than treating those counts as current proof.

Inspect the prototype in BrowserOS at desktop and narrow widths. Confirm supported creek lines draw, names and legend are readable, unavailable stretches differ from low flow, the time control behaves honestly, and detail values agree with the normalized artifact. Drawing successfully is only a technical check. Also describe what a reader can infer from the initial screen without clicks; leave Saul's comprehension judgment open until he actually reviews it.

## Publish on the existing website

Existing URL: `https://hill-country-hydro.saul-elbein.chatgpt.site`.
Mac publishing checkout: `/Users/saulelbein/Documents/Codex/hill-country-hydro-site`.
Its `.openai/hosting.json` contains Site ID `appgprj_6ac12765acb88191a74ce6c2570385f5` and static directory `out`. Confirm the current Site and manifest before editing. Reuse that identity and preserve its audience; do not create a replacement Site.

Use the current Sites workflow to open/sync the publishing checkout, prepare the static output and publish. Source remains in `hill-country-hydro`. Package any geometry and derived prototype artifacts the new interface actually requires; the previous deployment contained only HTML, JavaScript, the water bundle and two storm JSON files. Check relative paths in the hosted layout. Do not upload raw archives, SQLite, source history or local-only provenance files. Public detail links must point to files included in the deployment or official source pages, not local filesystem paths.

No schedule, notifications, PR or daily-routine changes. Publish a dated snapshot for review. Confirm deployment success through the hosting tools and give the existing Site URL plus any new prototype path. If publication is blocked, finish the local implementation and say exactly what prevented the online result.

## Working discipline and authorization

Make routine reversible implementation choices from evidence; do not turn each into a user question. Record method and scope decisions, alternatives and limits in `hill-country-hydro-system.md`. Ask a concise question only when a consequential ambiguity cannot be resolved from sources or the user's direction. Do independent work while awaiting an answer.

Do not alter existing thresholds, inventories, place records, hypotheses or immutable storm windows to make the prototype easier. New derived comparisons and geometry associations need explicit methods and provenance. No forecasts or place verdicts. Raw acquisition and interpretation remain separate.

This file requests architecture followed by implementation when Saul asks a session to execute it. It does not itself constitute a new instruction to another running task. Do not message tasks, create tasks, delegate, schedule work or publish merely because this handoff exists. Saul’s subsequent instruction explicitly requires merging the normalization layer into hill-country-hydro main; carry out that scoped integration, including commits and the push, after the full required suites pass. Use small commits and preserve concurrent work. Do not ask again for permission already given for that integration; assess authorization separately for unrelated changes.

## Deliverables and honest completion

Update the living system document with architecture decisions and this checklist as work proceeds:

- [ ] Source coverage and comparability audit saved, with gaps by creek/provider.
- [ ] Common measurement representation implemented in hill-country-hydro with original provenance.
- [ ] Reusable prototype analytic contract, offline command, README, layer table and changelog documented.
- [ ] Normalization stage integrated and pushed to main after passing suites; commit verified on origin/main.
- [ ] Identity, duplicate, conflict and time/units policies tested.
- [ ] Baseline and display scale chosen from actual records and documented.
- [ ] Gauge-to-channel associations supported and unsupported reaches explicit.
- [ ] Creek prototype consumes normalized output and passes browser checks.
- [ ] Water and swim checks pass; actual counts recorded.
- [ ] Existing Site updated and successful deployment confirmed.
- [ ] Saul's assessment of whether the visual is comprehensible recorded when received.

Finish with a short account of what is online, how to read it, which creeks/sources it covers, remaining limitations, test results, and any commits actually pushed. Do not claim that an unreviewed prototype has solved the comprehension problem.

Begin by inspecting the checkout and authoritative inputs, then audit normalization. Do not skip directly to restyling the map.

---

End of copy-pasteable prompt.

## Context when using this handoff

The original storm-data build is already integrated into the Central Texas Water Ledger. This is its next product step. The normalization stage must become a reusable prototype analytic layer on hill-country-hydro main before the work is considered delivered. Execute normalization first, then use the supported data to build and publish a bounded creek prototype. Keep the broader regional-water project in view without making it a prerequisite for this first readable display.
