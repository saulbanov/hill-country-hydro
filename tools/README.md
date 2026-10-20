# Scheduled tooling

## Local daily water and swim run

`daily_mac_run.py` is the single Mac job for both repositories. At 6:57 AM in the
Mac's local time zone, it runs the water README's daily chain and Sunday history
refresh, validates the water bundle and lands it on `origin/main`, then fetches that
bundle into the swim repository, runs its place-side chain, tests it, and lands it.
A water failure stops the lens. The job does not run either repo's
`cloud_capture_export.py`; the Mac keeps raw captures in each repo's ignored
`data/raw/`.

### Where it runs: two pins (2026-10-08)

The job never runs in the checkouts sessions work in. The plist sets `WATER_REPO`
and `SWIM_REPO` to two separate clones that nothing else uses:

| Pin | Branch | Ignored data, linked to |
|---|---|---|
| `~/Documents/runtime/hill-country-hydro` | `runtime/hill-country-hydro` | `~/Documents/job-data/hill-country-hydro/{raw,normalized,parsed}` |
| `~/Documents/runtime/austin-swim-map` | `runtime/austin-swim-map` | `~/Documents/job-data/austin-swim-map/{raw,parsed}` |

The shared checkouts (`~/Documents/Codex/hill-country-hydro`,
`~/Documents/Codex/austin-swim-map`) link the same folders, so a session there reads
and writes the same raw and normalized store the job does. Their branch and
uncommitted work no longer matter to the job. They also no longer receive each day's
commit by themselves: `git pull` brings it from `origin/main`. Without the variables
the runner uses the checkout holding the script and its sibling, so a hand run in a
plain shell still works. A missing checkout prints `SKIPPED <repo> — no checkout at
<path>`; with swim missing, water still runs and lands and the run ends `RESULT
FAILED stage=swim.preflight`.

**Before the run**, each checkout must be on a branch, clean, and hold no commit
beyond `origin/main` except its own `Daily run YYYYMMDD` commits. The run never
pulls code.

**Landing.** The run commits `Daily run YYYYMMDD` on the pin's branch and pushes it
to `origin/main`: as a fast-forward when main has not moved since the pin's code,
otherwise as a merge commit whose second parent is the day's commit, so main records
which code wrote the data. The merge is built file by file: main keeps every file the
run did not change, and the run's files replace main's. If a session changed a file
since the last landing that the run also changed (as session backfills did to
`dist/water-state.json`, `app/hydromet.json` and Hydromet capture manifests on
2026-10-02 and 10-03), nothing is pushed: the run prints a `CONFLICT` line per file
and ends `RESULT FAILED stage=water.land` (or `swim.land`). Two generations of a
generated file are never blended line by line.

### Moving code into the pins: `--promote`

Code pushed to `origin/main` does not reach the 6:57 run until someone runs the pin's
own copy of the runner, which finds both pins (its own folder and its sibling):

```sh
/opt/homebrew/bin/python3 ~/Documents/runtime/hill-country-hydro/tools/daily_mac_run.py --promote
```

A session may run it once its change is on `origin/main` and tests pass (Saul,
2026-10-08). It refuses while a scheduled run holds the job's lock, fast-forwards
both pins to `origin/main`, checks the plan's tool paths, and runs both suites in a
throwaway worktree (the swim suite rewrites `app/status.json`, which would leave a
pin dirty). If anything fails, every moved pin goes back to its old commit. Each
line `PROMOTE <repo> <old> -> <new>` records the move. If day commits failed to land
on a conflict, the promote lands them first, keeping main's copy of each file both
sides changed; the next run rewrites those files from the store. Promote after a
session commits any file the run writes, before the next 6:57.

### One attempt per day

The runner checks for a `Daily run YYYYMMDD` commit in either pin and on either
`origin/main`, and writes an exclusive claim under `data/raw/mac-daily-run/` (in the
shared job-data store) before the first provider request. A second start on the same
Central-time date skips collection, even after an interrupted run. A failed partial
run needs inspection; it does not automatically retry providers, and it leaves the
pin dirty, so the next day refuses to start until someone looks. Its final stdout
line is `RESULT OK`, `RESULT SKIPPED`, or `RESULT FAILED` with the date or failed
stage. The pinned `launchd-run.py` wrapper also records that line in the shared
heartbeat log, and `org.futureheist.pin-clean-check` names a dirty pin within 15
minutes.

It uses EAA's current `details` command with four-second pauses, adding `--version`
on Sundays; it does not use the obsolete EAA CSV collection route.

The installed plist is user-local at
`~/Library/LaunchAgents/org.saulelbein.hill-country-hydro.plist`; the tracked
reinstall template is `tools/launchd-hill-country-hydro.xml`. It uses the Mac's
local time zone. The Mac was on Central time when the plist was prepared. `launchd` runs a
missed calendar event when the Mac wakes from sleep, coalescing multiple missed
events into one. If the Mac is powered off, this plist has no `RunAtLoad`
catch-up: the missed day is skipped. The next scheduled day runs once. Keep the
Mac on Central time if the required wall-clock time is 6:57 AM Central.

Saul confirmed that he disabled the old claude.ai routine
`trig_012HVfp2gXNb1wK9K1LBvmyB` before this LaunchAgent was loaded on
2026-10-02. The cloud status was not independently visible from the signed-out
Mac browser. On the cutover day, do not hand-fire collection after the cloud
has already run. The first scheduled Mac run is the end-to-end proof.

### Reinstall after confirming the cloud routine is off

```sh
cp tools/launchd-hill-country-hydro.xml ~/Library/LaunchAgents/org.saulelbein.hill-country-hydro.plist
plutil -lint ~/Library/LaunchAgents/org.saulelbein.hill-country-hydro.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/org.saulelbein.hill-country-hydro.plist
launchctl list | rg 'org\.saulelbein\.hill-country-hydro'
```

### Offline verification and reversal

```sh
/opt/homebrew/bin/python3 ~/Documents/runtime/hill-country-hydro/tools/daily_mac_run.py --check
python3 -m unittest tests.test_daily_mac_run -v
launchctl bootout gui/$(id -u)/org.saulelbein.hill-country-hydro
```

The job's stdout and stderr go to
`~/Library/Logs/org.saulelbein.hill-country-hydro.log`. The shared heartbeat
goes to `~/Documents/Claude Code/future-heist/.launchd-heartbeat.log`.
`launchctl bootout` disables the job without deleting its plist or claim files.
