# Scheduled tooling

## Local daily water and swim run

`daily_mac_run.py` is the single Mac job for both repositories. At 6:57 AM in the
Mac's local time zone, it fast-forwards each clean `main` from `origin/main`,
runs the water README's daily chain and Sunday history refresh, validates and
pushes the water bundle, then fetches that bundle in the swim repository, runs
its place-side chain, tests it, and pushes. A water failure stops the lens.
The job does not run either repo's `cloud_capture_export.py`; the Mac keeps raw
captures under each repo's ignored `data/raw/`.

The runner checks for a `Daily run YYYYMMDD` commit in either repo and writes
an exclusive claim under `data/raw/mac-daily-run/` before the first provider
request. A second start on the same Central-time date skips collection, even
after an interrupted run. A failed partial run needs inspection; it does not
automatically retry providers. Its final stdout line is `RESULT OK`, `RESULT
SKIPPED`, or `RESULT FAILED` with the date or failed stage. The pinned
`launchd-run.py` wrapper also records that line in the shared heartbeat log.

The installed plist is user-local at
`~/Library/LaunchAgents/org.saulelbein.hill-country-hydro.plist`; the tracked
reinstall template is `tools/launchd-hill-country-hydro.xml`. It uses the Mac's
local time zone. The Mac was on Central time when the plist was prepared. `launchd` runs a
missed calendar event when the Mac wakes from sleep, coalescing multiple missed
events into one. If the Mac is powered off, this plist has no `RunAtLoad`
catch-up: the missed day is skipped. The next scheduled day runs once. Keep the
Mac on Central time if the required wall-clock time is 6:57 AM Central.

Do **not** bootstrap the Mac job until the old claude.ai routine
`trig_012HVfp2gXNb1wK9K1LBvmyB` has been disabled. This prevents two 6:57
provider chains. On the cutover day, do not hand-fire collection after the
cloud has already run. The first scheduled Mac run is the end-to-end proof.

### Install after the cloud routine is off

```sh
cp tools/launchd-hill-country-hydro.xml ~/Library/LaunchAgents/org.saulelbein.hill-country-hydro.plist
plutil -lint ~/Library/LaunchAgents/org.saulelbein.hill-country-hydro.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/org.saulelbein.hill-country-hydro.plist
launchctl list | rg 'org\.saulelbein\.hill-country-hydro'
```

### Offline verification and reversal

```sh
python3 tools/daily_mac_run.py --check
python3 -m unittest tests.test_daily_mac_run -v
launchctl bootout gui/$(id -u)/org.saulelbein.hill-country-hydro
```

The job's stdout and stderr go to
`~/Library/Logs/org.saulelbein.hill-country-hydro.log`. The shared heartbeat
goes to `~/Documents/Claude Code/future-heist/.launchd-heartbeat.log`.
`launchctl bootout` disables the job without deleting its plist or claim files.
