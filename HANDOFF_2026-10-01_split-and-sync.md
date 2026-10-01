# Handoff — bring the Mac copy, the swim lens and the water ledger into one working system

**For:** a local Claude Code session on Saul's Mac, and Saul reading along. Written 2026-10-01 (night) by the cloud session `session_01NurpiA1w4XfqZCrG3QrTYH`. **This file supersedes** `HANDOFF_2026-09-30_local-integration.md` and `HANDOFF_2026-10-01_local-integration.md`; they stay for the record and for detail, and this file says which section to read when.

**Read this whole file once before running anything.** Then work top to bottom. Every step says what it changes, how to check it, and how to undo it. Nothing here rewrites git history, deletes a raw file, or touches a provider faster than it allows.

---

## 0. The picture in one minute

Two days of cloud work turned the swimming-hole map into two things:

| Repo | Role | Owns |
|---|---|---|
| `saulbanov/hill-country-hydro` (new, private, seeded today) | **the water ledger**: measurement and station context for Central Texas | every collector (USGS, TWDB wells and lakes, Edwards Aquifer Authority, NWS), inventories (215 live USGS locations, 127 wells, 10 lakes, EAA sites), daily histories (68 flow, 126 non-flow), versioned captures, event ledgers, hydrologic context, the published bundle `dist/water-state.json`, a water map |
| `saulbanov/austin-swim-map` (existing) | **the swim lens**: what the measurements mean for a swimming place | places, place-to-station relationships, Saul's visit notes, condition rules and bands, City and TPWD operator checks, hazard place links, the storm-week experiment and its snapshots, the hypothesis list, the places map |

And one place that holds the bytes: **the Mac folder** `~/Documents/Codex/swimming-hole-alerts/`, a clone of `austin-swim-map`, with the only raw archive from before the cloud sessions. It becomes the home of both repos and, eventually, of the daily run.

The seam is one file, one direction: the water repo publishes `dist/water-state.json` each morning; the swim repo reads it with `tools/water_bundle.py fetch && apply` and never writes back. Station ids, well numbers and lake slugs are frozen on both sides.

The cloud routine (`trig_012HVfp2gXNb1wK9K1LBvmyB`, 6:57 AM Central, bound to the cloud session) already runs the water chain first and the lens second, and pushes both. `main` of both repos moves every morning: pull before you start, push when you finish.

---

## 1. Before you start

- [ ] Saul's OK to commit (the standing rule). This handoff was written at his request; treat that as the OK for the steps below, and ask before anything marked **ask**.
- [ ] Disk: the water repo's raw archive will be 2–3 GB after restore; the Mac folder already holds its own `data/raw/`.
- [ ] Python 3.11+ standard library only; no new packages. `node` is only needed for `node --check` on the map scripts.
- [ ] Do not run any collector during steps 1–6. The cloud routine ran this morning; running the same collectors from the Mac the same day doubles the load on providers, and the EAA server already throttles.

Terminology, because the names drifted: "swimming-hole-alerts" is the Mac folder's name for `austin-swim-map`. "The substrate", "the water repo", "the ledger" all mean `hill-country-hydro`. "The lens" means `austin-swim-map`.

---

## 2. Merge the swim repo into the Mac folder

What it changes: the Mac folder catches up with everything on GitHub (roughly sixty commits since the last pull, including today's bundle reader). Nothing in `data/raw/` or `data/normalized/` is touched by a merge; they are git-ignored.

```sh
cd ~/Documents/Codex/swimming-hole-alerts
git status                       # commit or stash anything local you mean to keep
git add -A && git commit -m "Local work before integrating origin/main 2026-10-01"   # only if there was something
git fetch origin
git log --oneline HEAD..origin/main | wc -l
git merge origin/main
```

If the merge is clean, go to section 3. If it conflicts, resolve **by file type**, never by picking a side blindly:
- `swimming-hole-alerts-system.md`, `README.md`, `data/coverage.md`, `data/coverage.json`: keep both sides of every hunk (log entries interleave by date).
- Generated files (`app/status.json`, `app/operator-status.json`, `app/gauge-readings.json`, `app/hydro-context.json`, `app/hazards-status.json`, `app/pool-status.json`, `app/tpwd-alerts.json`, `data/parsed/*`, `outputs/*`, `data/model/*-manifest.json`, `data/model/*-event-ledger.json`): take `origin/main` (`git checkout --theirs <file>`) and regenerate later.
- Hand-authored records (`data/holes.json`, `data/gauges.json`, `data/rules.json`, `data/observations.jsonl`, `data/model/place-relationships.json`): take `origin/main`, then re-apply any local-only edit by hand. Ids are frozen; never rename or renumber.
- `tools/*.py`, `tests/*.py`: take `origin/main` unless the Mac has a change that never reached GitHub; carry such a change over as a new commit after the merge, with a test.
Then `git add -A && git commit` (the generated merge message is fine).

Check: `python3 -m unittest discover -s tests` runs with **no skips** on the Mac (the cloud checkout skips three tests for lack of the raw archive). Expect roughly 95 tests.

Undo: `git merge --abort` before committing; after committing, `git revert -m 1 <merge commit>`.

---

## 3. Clone the water repo beside it

What it changes: adds a sibling folder. The lens's `tools/water_bundle.py` looks for `../hill-country-hydro/dist/water-state.json` by default (or `WATER_BUNDLE=<path or URL>`), so the two folders must be siblings or the variable must be set.

```sh
cd ~/Documents/Codex
git clone https://github.com/saulbanov/hill-country-hydro
cd hill-country-hydro && python3 -m unittest discover -s tests     # 24 tests, all should pass without any raw archive
```

Read `hill-country-hydro-system.md` (purpose, layers, rules, open items) and `AGENTS.md` there before touching it. `IDEAS.md` is a list of possible builds, not a backlog.

---

## 4. Give the water repo its raw archive

What it changes: copies measurement bytes into `hill-country-hydro/data/raw/` (git-ignored there too). Nothing is removed from the Mac's swim folder; copying is enough, and the swim folder's copies stay until section 7.

4a. **Copy the Mac's pre-cloud measurement captures.** These are the provider folders that are measurements, not City pages:
```sh
cd ~/Documents/Codex
for d in usgs usgs-daily usgs-history nws; do
  [ -d swimming-hole-alerts/data/raw/$d ] && rsync -a --ignore-existing swimming-hole-alerts/data/raw/$d/ hill-country-hydro/data/raw/$d/
done
```
Leave `documentary/`, `austin-pools/`, `tpwd/` and any operator-page captures in the swim folder; `twdb/`, `twdb-reservoirs/`, `eaa/` did not exist before today, so there is nothing to copy for them.

4b. **Restore every cloud capture folder with checksums.** The script exists now: `hill-country-hydro/tools/cloud_capture_restore.py`. It gunzips, verifies sha256 and length against each folder's `manifest.jsonl`, writes to `restore_to`, skips identical files, and keeps both when a local file differs (`.attempt-N`). Dry-run first.
```sh
cd ~/Documents/Codex/hill-country-hydro
python3 tools/cloud_capture_restore.py --check                                  # its own _cloud-captures/*
python3 tools/cloud_capture_restore.py --check ../swimming-hole-alerts/_cloud-captures/*   # the swim repo's folders too
python3 tools/cloud_capture_restore.py
python3 tools/cloud_capture_restore.py ../swimming-hole-alerts/_cloud-captures/*
```
Expected on 2026-10-01: four folders in each repo (64 + 206 + 606 + 969 files; the swim repo's copies are the same bytes). Any `BAD` line means a manifest mismatch: stop and look; do not delete anything.

4c. **Restore the versioned histories into raw** (optional but tidy): the gzips under `data/captures/usgs-daily/`, `data/captures/twdb-wells/`, `data/captures/twdb-reservoirs/`, `data/captures/eaa/` are the newest complete captures; `usgs_history.py normalize` and friends read them directly when the raw copy is absent, so this step can wait.

Check: `du -sh hill-country-hydro/data/raw` is in the low gigabytes; `ls hill-country-hydro/data/raw` shows `usgs usgs-daily twdb twdb-reservoirs eaa nws documentary` (documentary only holds the inventory and audit captures).

Undo: these are copies; deleting `hill-country-hydro/data/raw/` loses nothing that is not still in the swim folder or the capture folders.

---

## 5. Rebuild the water repo from its own archive and publish

What it changes: regenerates `data/normalized/water.sqlite`, `data/parsed/`, `data/history/`, `app/*.json`, `dist/water-state.json` inside the water repo. No network unless you choose to collect (do not today; see section 1).

```sh
cd ~/Documents/Codex/hill-country-hydro
python3 tools/monitor.py normalize
python3 tools/signal_pipeline.py normalize && python3 tools/signal_pipeline.py parse
python3 tools/usgs_history.py normalize && python3 tools/usgs_series_history.py normalize
python3 tools/groundwater.py normalize && python3 tools/groundwater.py assess
python3 tools/reservoirs.py normalize && python3 tools/reservoirs.py assess
python3 tools/eaa.py normalize && python3 tools/eaa.py assess
python3 tools/hydro_context.py
python3 tools/event_ledger.py
python3 tools/weather_validation.py validate
python3 tools/publish_bundle.py
python3 -m unittest discover -s tests
```

Check: `publish_bundle.py` prints counts near `stations: 218, wells: 127, lakes: 10, eaa_wells: 69, eaa_rain_gauges: 85` and `missing inputs: []`. `data/model/daily-history-skipped.json` and `series-history-skipped.json` list at most the two incomplete USGS responses noted in the system document. Open `app/index.html` through `python3 -m http.server 8000 --bind 127.0.0.1` and click a station, a well and a lake.

Commit (it is generated output and the regenerated bundle): `git add -A && git commit -m "Rebuild from the restored archive on the Mac" && git push origin main`.

---

## 6. Point the lens at the bundle and verify the map

What it changes: the swim folder's `app/gauge-readings.json` and `app/hydro-context.json` are rewritten from the bundle; `status.json` is reassessed from them. Operator steps fetch City and TPWD pages (small; allowed today).

```sh
cd ~/Documents/Codex/swimming-hole-alerts
python3 tools/water_bundle.py fetch && python3 tools/water_bundle.py apply
python3 tools/austin_operator.py collect && python3 tools/austin_operator.py normalize && python3 tools/austin_operator.py parse && python3 tools/austin_operator.py assess
python3 tools/pool_pipeline.py collect && python3 tools/pool_pipeline.py normalize && python3 tools/pool_pipeline.py parse
python3 tools/hazards.py assess
python3 tools/tpwd_alerts.py assess
python3 tools/monitor.py assess
python3 tools/experiment_snapshot.py --experiment storm-week-2026-10
python3 -m unittest discover -s tests
```

Check, on the map (`python3 -m http.server 8000 --bind 127.0.0.1`, open `/app/`):
- Bull Creek District Park: a reading from 08154700 with the **bundle's** timestamp, the provisional band's color or "no fresh reading", the visits "the park falls, roughly".
- McKinney Lower Falls: red below 1.19 cfs, the "Park alerts (TPWD)" block, visits April 26 and May 10 and the May–June range.
- Twin Falls, Hill of Life, Sculpture Falls, Gus Fruh, Campbell's Hole, The Flats: colored under the recorded bands when fresh.
- St. Edward's, McKinney Upper Falls, the Onion Creek playground, the Williamson greenbelts: gray with context cards and the gauges shown.
- The gauge layer: 73 markers; the "Aquifer wells (TWDB)" layer: 127 markers.
- `app/water-state` provenance: `data/water-state.meta.json` names the bundle's `generated_at` and sha256.

Commit: `git add -A && git commit -m "First bundle-driven assess on the Mac" && git push origin main`.

Undo: the swim folder's own collectors are still present until section 7; `python3 tools/monitor.py collect --stations <the Austin ten> && normalize` followed by `signal_pipeline` and `hydro_context.py` restores the old path.

---

## 7. Prune the swim repo (only after section 6 looked right) — **ask Saul first**

What it changes: removes from `austin-swim-map` the files that now live in the water repo. Ordinary `git rm`; the history stays. The deletion list, so nothing is guessed:

- tools: `usgs_history.py`, `usgs_series_history.py`, `regional_inventory.py`, `station_lists.py`, `hydro_context.py`, `event_ledger.py`, `groundwater.py`, `reservoirs.py`, `eaa.py`, `weather_validation.py`, `usgs_catalog.py`, `historical_inventory.py`, `historical_backfill.py`, `austin_official_geography.py`; keep `monitor.py` only for `assess` (strip `collect`/`normalize` or leave them unused, Saul's call), keep `reach_geometry.py` only if the marker audit still needs it (it does; keep).
- data: `data/history/`, `data/captures/usgs-daily/`, `data/captures/twdb-wells/`, `data/captures/twdb-reservoirs/`, `data/captures/eaa/`, `data/captures/nws/`, `data/stations-regional.json`, `data/usgs-locations-regional.json`, `data/usgs-history-plan.json`, `data/wells-regional.json`, `data/eaa-sites.json`, `data/model/*-event-ledger.json` (the swim-side labels are reproduced in the water repo's ledgers only for stations that have places; keep `08154700` and `08159000` ledgers if the rule tests cite them, or point those tests at the bundle's `thresholds`), `data/model/*-daily-history-manifest.json`, `data/model/austin-candidate-station-probe.json`.
- app: `app/groundwater.json`, `app/reservoirs.json`, `app/eaa.json`, the wells layer in `app.js` if Saul wants the swim map to show only places and gauges.
- tests: `test_groundwater.py`, `test_regional_sources.py`, the station-only classes in `test_hydro_model.py`.
- `_cloud-captures/`: delete after section 4b confirmed every file restored into the water repo.

Keep: `data/gauges.json` (markers), `data/model/place-relationships.json`, `data/rules.json`, `data/observations.jsonl`, `data/holes.json`, the storm-week protocol and `data/experiments/`, `tools/water_bundle.py`, the operator tools, `hazards.py` (its `links` and `assess` are place-side).

Write the pruning into the Decision Log and the Session Log. Then: `python3 -m unittest discover -s tests`, `git commit`, `git push`.

---

## 8. Move the daily run home — **ask Saul which option**

Two options; both run the same two chains in the same order (water first, lens second). The README of each repo has the exact commands.

- **Keep the cloud routine.** It works today. Cost: the raw bytes of every day ride the branch under `_cloud-captures/` (about 25 MB a day) until a local session restores them. Choose this if the Mac is often asleep at 6:57.
- **A launchd job on the Mac.** `~/Library/LaunchAgents/com.saul.hill-country-hydro.plist` running a shell script at 6:57 that does: `cd hill-country-hydro && <README chain> && git push`, then `cd swimming-hole-alerts && water_bundle fetch/apply && <lens chain> && git push`. The moment this runs, edit the cloud routine to **stop** (or delete it): two collectors a day against the EAA server is one too many. Also remove `cloud_capture_export.py` from both chains; the Mac's `data/raw/` is the archive.

Either way: never two collection runs against the same provider on the same morning.

---

## 9. Update the atlas and the share bundle

- `reporting-os/AGENTS.md` in the meta-repo: add a row `hill-country-hydro | L1 scraper + L2 substrate | own repo (split 2026-10-01 from austin-swim-map)`; change the `austin-swim-map` row to `L3 lens over hill-country-hydro`. Mirror both in the meta-repo's top-level table.
- Regenerate `artifacts/austin-swim-map-share-*.zip` from the pruned swim repo.

---

## 10. What is where, for reference

| Thing | Water repo | Swim repo |
|---|---|---|
| Raw captures | `data/raw/` (ignored); versioned gzips `data/captures/`; cloud folders `_cloud-captures/` | operator and documentary captures only after pruning |
| Inventories | `data/stations-regional.json`, `data/usgs-locations-regional.json`, `data/usgs-history-plan.json`, `data/wells-regional.json`, `data/eaa-sites.json` | `data/holes.json`, `data/gauges.json`, `data/model/place-relationships.json` |
| Histories | `data/history/*.csv` with manifests in `data/model/` | none |
| Context | `app/hydro-context.json`, `data/model/*-event-ledger.json`, `app/groundwater.json`, `app/reservoirs.json`, `app/eaa.json`, `app/hazards-status.json` | copies of the first two, rewritten from the bundle by `water_bundle.py apply` |
| Rules and notes | none | `data/rules.json`, `data/observations.jsonl`, the hypothesis list in the plan |
| Experiment | `data/model/storm-week-validation.json` (rain validation) | the protocol, `data/experiments/storm-week-2026-10/` snapshots |
| Plan documents | `hill-country-hydro-system.md`, `IDEAS.md`, `CHANGELOG.md`, `AGENTS.md`, `README.md` | `swimming-hole-alerts-system.md`, `AUSTIN_SWIM_MODEL_HANDOFF.md`, `PROPOSAL_2026-10-01_central-texas-water-split.md`, this file |
| Daily routine | collects, publishes, pushes | fetches the bundle, operator checks, assess, snapshot, pushes |

---

## 11. Open items that need Saul

1. Public visibility of `hill-country-hydro`: replace the contact email in the collectors' User-Agent strings (`tools/*.py`, search `saul.elbein`) with a project address first.
2. EAA throttling: the server refused bulk CSV pulls on 2026-10-01; find the tolerated pace or email `data@edwardsaquifer.org` for a bulk export.
3. The two open swim-side questions from the visits: Middle vs Lower Bull Creek Falls; which falls on May 10, 2025; a rating for the April 27, 2025 Onion Creek playground visit.
4. Whether to build any of `IDEAS.md`; the dry index and the event catalog are the two most others build on.
5. The hypothesis list and visit-reporting feature noted in the swim plan after Step 10 (not built).
6. Which of the two daily-run homes (section 8).

---

## 12. Verification checklist for whoever does this

- [ ] Section 2: swim folder merged, tests pass with no skips.
- [ ] Section 3: `hill-country-hydro` cloned beside it; its tests pass.
- [ ] Section 4: every cloud capture folder restored with zero `BAD` lines; the Mac's USGS and NWS raw folders copied over.
- [ ] Section 5: bundle published with no missing inputs; water tests pass; pushed.
- [ ] Section 6: the swim map's cards show readings with the bundle's timestamp; swim tests pass; pushed.
- [ ] Section 7 (after Saul's OK): pruned, logged, tests pass, pushed.
- [ ] Section 8 (after Saul's choice): exactly one daily run exists.
- [ ] Section 9: atlas rows updated; share zip regenerated.
- [ ] The next morning's `Daily run <date>` commits appear on both repos' `main`.
