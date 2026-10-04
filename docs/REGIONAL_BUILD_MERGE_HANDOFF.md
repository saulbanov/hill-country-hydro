# Merge history and geological context into the ongoing regional build

This is an additive scope handoff for the build already underway in `/Users/saulelbein/Documents/Codex/hill-country-hydro`. Reconcile it with the actual code and decisions in that session. Continue from completed work; do not restart the project or replace a working architecture to match an earlier proposal's filenames, storage format or screen layout. “Merge” here means incorporating requirements; no particular Git branch merge is prescribed.

Read `AGENTS.md`, the latest `hill-country-hydro-system.md`, the current analytic contract and the historical/geological additions in `docs/REGIONAL_WATER_MAP_HANDOFF.md`. This note explains how to incorporate those additions into an active build. Keep evolving progress and decisions in the system document.

## Reconcile before editing

Inspect current changes, integration status and tests. Local commit `58c24584` existed when this note was written, with regional analytics and additional geography/consumer work in progress. That is a discovery pointer, not proof of current remote state. Do not re-create an already integrated layer or overwrite uncommitted work. Verify the current state yourself.

Add a compact reconciliation table to the system document: requirement, existing implementation/evidence, remaining change, and validation. Mark each as already satisfied, implement in pilot, extension-only, or blocked with evidence. Different implementation choices are acceptable if they meet the outcome. Do not silently defer a pilot requirement because the older plan omitted it. Resolve routine differences yourself and proceed; ask only about a consequential conflict that evidence and existing authorization cannot resolve.

## Add to the current pilot

1. **Full available station history.** Expose the longest usable preserved record for supported pilot stations through the reusable hydro layer and the website. Audit earliest/latest records, missing years and known station, sensor, statistic, datum or management changes. Where older official records are missing locally, assess bounded recovery and document unavailable inputs. Preserve any efficient recent-window store; add indexed history, partitions or another compatible reader path. Archive counts alone are not historical exploration. The current contract's 2006 daily and September 2026 other-data cutoffs do not satisfy this addition by themselves.

2. **Separate historical range from “usual.”** Retain an explicit, defensible seasonal reference period while allowing inspection of the full record. Show gaps, differing station coverage and documented breaks. Do not combine incompatible eras into an unlabeled rank, substitute current values for an old date or treat a growing gauge network as a regional trend. Older evidence can be displayed even when it cannot support a comparable percentile.

3. **Show complementary dimensions together.** Selecting a watershed should connect rain, river flow, well/spring observations and reservoir storage through aligned plots or an equivalent readable view. Preserve their own units, intervals and gaps. Show both storm response and longer conditions. Similar timing is not proof of recharge or causation; wells measure local level/head, not total aquifer volume, and storage change is not measured inflow.

4. **Add bounded geological context.** Include sourced aquifer outcrop/subsurface context and available formations, recharge areas, confining relationships and faults relevant to the pilot. Retain documented well aquifer assignments and completion/screen intervals where available; never infer the producing unit from a surface polygon alone. Provide a relevant published cross-section or a clearly schematic section supported by cited relationships. If suitable free evidence is unavailable, expose the specific gap and withhold the unsupported section. No invented underground depths, connections or 3D simulation. Keep geological interpretation visibly distinct from observations and surface watersheds distinct from aquifers.

5. **Keep the map legible.** Preserve the work on continuous recognizable channels and the existing pilot geography unless evidence requires a correction. History and geology should be accessible without obscuring the rivers. Gauge observations, contextual channel lines and any supported reach estimates must remain distinguishable; symbolic width is not inundation.

Use existing official inputs first. The fuller handoff names TWDB and BEG geography sources; check access, scale and provenance. Do not purchase restricted maps. Unsupported geology must remain a stated limitation, not a fabricated layer.

## Merge into the extension plan, not this pilot's critical path

Record these ordered stages and their deliverables in the existing living plan:

1. Historical storm/drought comparisons: comparable rainfall and starting conditions, response lags, persistence, zero-flow periods, and well/spring/storage changes, with coverage and continuity checks.
2. Added explanatory inputs: audit soil moisture, reservoir releases, evaporation and documented pumping/withdrawals to address specific unresolved questions; distinguish observations from estimates and incomplete water budgets.
3. Deeper geological associations and additional basins: supported aquifer subdivisions, well completions and spring/stream connections; extend the audited approach to the Guadalupe, Blanco and Medina.
4. Documentary and paleoclimate history: dated accounts and infrastructure changes, then suitable tree-ring, sediment or cave-deposit reconstructions. Keep observed, calculated, interpreted, documentary and reconstructed evidence distinguishable. Retain reconstructed variables, geographic scope, resolution and uncertainty; never convert a drought proxy into invented historical creek discharge.

Do not execute every extension merely because it is listed. The pilot must provide the full-record and geological foundations above, while these deeper analyses remain explicit subsequent work.

## Integration and delivery

Reuse the existing offline normalization/reader boundary. No provider interpretation in browser code. If the analytic stage is already integrated, deliver these additions as subsequent tested commits rather than rewriting its history. Integrate analytic changes into hydro main, push under the build's existing authorization, verify on `origin/main`, and have the map consume that integrated version.

Add focused tests for old records outside recent cutoffs, continuity boundaries, missing years, time/baseline selection and unsupported geological assignments. Run the full water suite and isolated swim suite before integration/push; inspect desktop and narrow browser views. Verify at least one historical observation and geological attribution against sources. Existing results are a baseline, not proof that additions pass.

Continue through publication to the same Central Texas Water Ledger Site, preserving its identity/audience and access to the Austin prototype and original ledger. No new dependencies, paid APIs, forecasts, PRs, schedules, notifications or daily-routine changes. Preserve raw records, rules, tests and concurrent work. Existing build authorization persists; this handoff does not authorize unrelated actions or contacting other tasks.

Finish with what was reconciled, what is online, the verified analytic/map commits, test results, any genuinely blocked pilot requirement, and the recorded extension stages. Do not report extension ideas as delivered features. The request to author this handoff does not itself run the build; apply it when Saul supplies it to the ongoing session.
