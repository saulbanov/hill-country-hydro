#!/usr/bin/env python3
"""One guarded local water-ledger run followed by the swim-lens run.

Both repositories run from pinned checkouts that interactive sessions never use: the
installed plist sets WATER_REPO and SWIM_REPO to separate clones under ~/Documents/runtime/.
A pin's own branch holds the code it was last promoted to plus its `Daily run YYYYMMDD`
data commits. The run never pulls code. It lands each day's data commit on origin/main
(see land()). Code reaches a pin only through --promote, which a session runs after its
change is on origin/main.

The dated claim is written before the first provider request. An interrupted run
cannot silently retry a partly collected day. Use --check for an offline plan
and path check; it makes no provider or Git network request.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from zoneinfo import ZoneInfo


# The water ledger checkout: WATER_REPO if set (the installed plist points it at the pin,
# ~/Documents/runtime/hill-country-hydro), else the checkout holding this script.
WATER = pathlib.Path(os.environ.get("WATER_REPO")
                     or pathlib.Path(__file__).resolve().parents[1]).expanduser()
# The swim lens checkout: SWIM_REPO if set (the plist: ~/Documents/runtime/austin-swim-map),
# else the sibling folder named for its repo (saulbanov/austin-swim-map), else its old folder
# name (renamed 2026-10-05).
SWIM = pathlib.Path(os.environ.get("SWIM_REPO") or next(
    (p for p in (WATER.parent / "austin-swim-map", WATER.parent / "swimming-hole-alerts") if p.is_dir()),
    WATER.parent / "austin-swim-map")).expanduser()
STATE_DIR = WATER / "data" / "raw" / "mac-daily-run"
LOCAL_TZ = ZoneInfo("America/Chicago")
PYTHON = pathlib.Path("/opt/homebrew/bin/python3")
DAILY = re.compile(r"Daily run \d{8}")
# launchd-run.py --lock holds this file for the whole scheduled run. --promote takes it
# too, so a promote never moves a pin while a day is running.
RUN_LOCK = (pathlib.Path.home() / "Library" / "Caches" / "launchd-run"
            / "org.saulelbein.hill-country-hydro.lock")


@dataclass(frozen=True)
class Step:
    name: str
    repo: pathlib.Path
    args: tuple[str, ...]


def python_step(name: str, repo: pathlib.Path, tool: str, *args: str) -> Step:
    return Step(name, repo, (str(PYTHON), "tools/" + tool + ".py", *args))


def plan(day: dt.date) -> list[Step]:
    w = WATER
    s = SWIM
    steps = [
        python_step("water.usgs_collect", w, "monitor", "collect", "--inventory"),
        python_step("water.usgs_normalize", w, "monitor", "normalize"),
        python_step("water.signal_normalize", w, "signal_pipeline", "normalize"),
        python_step("water.signal_parse", w, "signal_pipeline", "parse"),
        python_step("water.readings", w, "monitor", "readings"),
        python_step("water.wells_collect", w, "groundwater", "collect"),
        python_step("water.wells_normalize", w, "groundwater", "normalize"),
        python_step("water.wells_assess", w, "groundwater", "assess"),
        python_step("water.lakes_collect", w, "reservoirs", "collect"),
        python_step("water.lakes_normalize", w, "reservoirs", "normalize"),
        python_step("water.lakes_assess", w, "reservoirs", "assess"),
        python_step("water.eaa_conditions", w, "eaa", "conditions"),
        python_step("water.eaa_details", w, "eaa", "details", "--pause-seconds", "4",
                    *(("--version",) if day.weekday() == 6 else ())),
        python_step("water.eaa_normalize", w, "eaa", "normalize"),
        python_step("water.eaa_assess", w, "eaa", "assess"),
        python_step("water.hydromet_collect", w, "hydromet", "collect"),
        python_step("water.hydromet_history", w, "hydromet", "history", "--recent-only"),
        python_step("water.hydromet_normalize", w, "hydromet", "normalize"),
        python_step("water.hydromet_assess", w, "hydromet", "assess"),
        python_step("water.hazards_assess", w, "hazards", "assess"),
        python_step("water.weather_collect", w, "weather_validation", "collect"),
        python_step("water.weather_validate", w, "weather_validation", "validate"),
        python_step("water.operator_notices_collect", w, "operator_notices", "collect"),
        python_step("water.operator_notices_normalize", w, "operator_notices", "normalize"),
        python_step("water.usdm_collect", w, "usdm", "collect"),
        python_step("water.usdm_normalize", w, "usdm", "normalize"),
    ]
    if day.weekday() == 6:  # Sunday: refresh histories before context and publishing.
        steps.extend([
            python_step("water.usgs_daily_collect", w, "usgs_history", "collect"),
            python_step("water.usgs_daily_normalize", w, "usgs_history", "normalize"),
            python_step("water.usgs_series_collect", w, "usgs_series_history", "collect"),
            python_step("water.usgs_series_normalize", w, "usgs_series_history", "normalize"),
            python_step("water.event_ledger", w, "event_ledger"),
            python_step("water.nclimdiv_collect", w, "nclimdiv", "collect"),
            python_step("water.nclimdiv_normalize", w, "nclimdiv", "normalize"),
            python_step("water.ghcn_collect", w, "ghcn_daily", "collect"),
            python_step("water.ghcn_normalize", w, "ghcn_daily", "normalize"),
            python_step("water.field_measurements_collect", w, "usgs_field_measurements", "collect"),
            python_step("water.field_measurements_normalize", w, "usgs_field_measurements", "normalize"),
        ])
        if day.day <= 7:  # first Sunday of the month: TWDB drillers' reports (one ~150 MB file)
            steps.extend([
                python_step("water.twdb_gwuse_collect", w, "twdb_groundwater_use", "collect"),
                python_step("water.twdb_gwuse_normalize", w, "twdb_groundwater_use", "normalize"),
            ])
    steps.extend([
        python_step("water.hydro_context", w, "hydro_context"),
        python_step("water.publish_bundle", w, "publish_bundle"),
        Step("water.tests", w, (str(PYTHON), "-m", "unittest", "discover", "-s", "tests")),
    ])
    steps.extend([
        # The lens reads the bundle this run just published, in the water checkout it ran in.
        python_step("swim.bundle_fetch", s, "water_bundle", "fetch",
                    "--from", str(w / "dist" / "water-state.json")),
        python_step("swim.bundle_apply", s, "water_bundle", "apply"),
        python_step("swim.coa_collect", s, "lcra_coa_live", "collect"),
        python_step("swim.coa_normalize", s, "lcra_coa_live", "normalize"),
        python_step("swim.blunn_collect", s, "blunn_flow_history", "collect"),
        python_step("swim.blunn_normalize", s, "blunn_flow_history", "normalize"),
        python_step("swim.pools_collect", s, "pool_pipeline", "collect"),
        python_step("swim.pools_normalize", s, "pool_pipeline", "normalize"),
        python_step("swim.pools_parse", s, "pool_pipeline", "parse"),
        python_step("swim.operator_collect", s, "austin_operator", "collect"),
        python_step("swim.operator_normalize", s, "austin_operator", "normalize"),
        python_step("swim.operator_parse", s, "austin_operator", "parse"),
        python_step("swim.operator_assess", s, "austin_operator", "assess"),
        python_step("swim.hazards_assess", s, "hazards", "assess"),
        python_step("swim.tpwd_assess", s, "tpwd_alerts", "assess"),
        python_step("swim.assess", s, "monitor", "assess"),
        python_step("swim.snapshot", s, "experiment_snapshot", "--experiment", "storm-week-2026-10"),
        # Posted-hours pages that render only in a browser (Pflugerville): render, check, publish the
        # check file to the public map's Pages repo. Each stage logs and exits 0 on failure.
        python_step("swim.browser_hours_collect", s, "browser_hours", "collect"),
        python_step("swim.browser_hours_assess", s, "browser_hours", "assess"),
        python_step("swim.browser_hours_publish", s, "browser_hours", "publish"),
        Step("swim.tests", s, (str(PYTHON), "-m", "unittest", "discover", "-s", "tests")),
    ])
    return steps


def run_command(step: Step) -> None:
    print("RUN", step.name, *step.args, flush=True)
    subprocess.run(step.args, cwd=step.repo, check=True)


def git(repo: pathlib.Path, *args: str, capture: bool = False,
        env: dict[str, str] | None = None, stdin: str | None = None) -> str:
    result = subprocess.run(
        ("/usr/bin/git", *args), cwd=repo, check=True, env=env, input=stdin,
        text=True, capture_output=capture,
    )
    return result.stdout.strip() if capture else ""


def present(repo: pathlib.Path) -> bool:
    return (repo / ".git").exists()


def check_paths(steps: list[Step]) -> None:
    if not PYTHON.is_file():
        raise RuntimeError("missing_python " + str(PYTHON))
    for repo in sorted({step.repo for step in steps}):
        if not present(repo):
            raise RuntimeError("missing_checkout " + str(repo))
    for step in steps:
        if len(step.args) > 1 and step.args[1].startswith("tools/"):
            if not (step.repo / step.args[1]).is_file():
                raise RuntimeError("missing_tool_" + step.name)


def off_main(repo: pathlib.Path, daily: bool) -> list[str]:
    """Short ids of HEAD's commits that origin/main lacks: its daily data commits
    (daily=True) or anything else, which is code that was never landed (daily=False)."""
    out = git(repo, "log", "--format=%h %s", "origin/main..HEAD", capture=True)
    rows = [line.partition(" ") for line in out.splitlines() if line]
    return [sha for sha, _, subject in rows if bool(DAILY.fullmatch(subject)) == daily]


def code_commit(repo: pathlib.Path) -> str:
    """The commit the checkout was last promoted to: HEAD without its daily data commits."""
    return git(repo, "log", "-1", "--first-parent", "--format=%H", "-E", "--invert-grep",
               "--grep=^Daily run [0-9]{8}$", "HEAD", capture=True)


def guard(repo: pathlib.Path) -> str:
    """Refuse a checkout the run must not write from, fetch origin, return its code commit.

    The checkout must be on a branch, clean, and hold no commit beyond origin/main except
    its own daily data commits: landing pushes everything HEAD has, so any other commit
    would be code reaching main from a scheduled job."""
    actual = git(repo, "rev-parse", "--show-toplevel", capture=True)
    if pathlib.Path(actual).resolve() != repo.resolve():
        raise RuntimeError("wrong_repo " + str(repo))
    branch = git(repo, "branch", "--show-current", capture=True)
    if not branch:
        raise RuntimeError("detached_head " + str(repo))
    dirt = git(repo, "status", "--porcelain", capture=True)
    if dirt:
        raise RuntimeError("dirty " + str(repo) + ": " + "; ".join(dirt.splitlines()[:5]))
    git(repo, "fetch", "--quiet", "origin")
    stray = off_main(repo, daily=False)
    if stray:
        raise RuntimeError("code_not_on_main " + str(repo) + ": " + ",".join(stray))
    code = code_commit(repo)
    print("CHECKOUT", repo.name, "path=" + str(repo), "branch=" + branch,
          "code=" + code[:12], flush=True)
    return code


def already_collected(day: dt.date, repos: tuple[pathlib.Path, ...]) -> str | None:
    message = "Daily run " + day.strftime("%Y%m%d")
    for repo in repos:
        subjects = git(repo, "log", "--format=%s", "--grep=^" + message + "$",
                       "HEAD", "origin/main", capture=True).splitlines()
        if message in subjects:
            return repo.name
    return None


def claim_day(day: dt.date, state_dir: pathlib.Path = STATE_DIR) -> pathlib.Path | None:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / (day.strftime("%Y%m%d") + ".json")
    try:
        with path.open("x", encoding="utf-8") as file:
            json.dump({"day": day.isoformat(), "status": "started", "last_step": None,
                       "started_at": dt.datetime.now(LOCAL_TZ).isoformat()}, file)
            file.write("\n")
    except FileExistsError:
        return None
    return path


def progress(path: pathlib.Path, status: str, last_step: str | None) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(status=status, last_step=last_step,
                updated_at=dt.datetime.now(LOCAL_TZ).isoformat())
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def validate_bundle() -> None:
    bundle = WATER / "dist" / "water-state.json"
    data = json.loads(bundle.read_text(encoding="utf-8"))
    if data.get("missing_inputs") != []:
        raise RuntimeError("bundle_missing_inputs")
    counts = data.get("counts", {})
    for key in ("stations", "wells", "lakes", "eaa_wells", "eaa_rain_gauges"):
        if not isinstance(counts.get(key), int) or counts[key] < 1:
            raise RuntimeError("bundle_empty_" + key)
    generated = dt.datetime.fromisoformat(data["generated_at"])
    if generated.astimezone(LOCAL_TZ).date() != dt.datetime.now(LOCAL_TZ).date():
        raise RuntimeError("bundle_not_generated_today")
    print("BUNDLE", json.dumps(counts, sort_keys=True), flush=True)


def is_ancestor(repo: pathlib.Path, older: str, newer: str) -> bool:
    code = subprocess.run(("/usr/bin/git", "merge-base", "--is-ancestor", older, newer),
                          cwd=repo).returncode
    if code > 1:
        raise RuntimeError("merge_base_failed " + str(repo))
    return code == 0


def changed(repo: pathlib.Path, base: str, ref: str) -> list[str]:
    out = git(repo, "diff", "--name-only", "--no-renames", "-z", base, ref, capture=True)
    return [path for path in out.split("\0") if path]


def overlay_tree(repo: pathlib.Path, main_wins: bool) -> tuple[str, list[str]]:
    """Merge HEAD into origin/main file by file, never line by line.

    Start from origin/main's tree and lay over it every file HEAD changed since the merge
    base. A line merge of two generations of a generated file (the bundle, a capture
    manifest) can yield a file neither side wrote, so a file changed on both sides is never
    blended: the landing stops on it, and --promote (main_wins=True) keeps main's copy.
    Returns the tree id and the files changed on both sides."""
    base = git(repo, "merge-base", "origin/main", "HEAD", capture=True)
    ours = changed(repo, base, "HEAD")
    theirs = set(changed(repo, base, "origin/main"))
    both = sorted(path for path in ours if path in theirs)
    if both and not main_wins:
        for path in both:
            print("CONFLICT", repo.name, path, file=sys.stderr, flush=True)
        raise RuntimeError(
            "land_conflict " + repo.name + ": " + str(len(both)) + " files changed on origin/main"
            " and in this checkout since " + base[:12] + "; fix: tools/daily_mac_run.py --promote")
    listing = git(repo, "ls-tree", "-r", "-z", "HEAD", capture=True)
    head = {}
    for entry in listing.split("\0"):
        if entry:
            meta, _, path = entry.partition("\t")
            head[path] = meta
    removed = "0 " + "0" * len(base)
    lines = [(head[path] if path in head else removed) + "\t" + path
             for path in ours if path not in theirs]
    with tempfile.TemporaryDirectory() as temp:
        env = {**os.environ, "GIT_INDEX_FILE": str(pathlib.Path(temp) / "index")}
        git(repo, "read-tree", "origin/main", env=env)
        if lines:
            git(repo, "update-index", "-z", "--index-info", env=env, stdin="\0".join(lines) + "\0")
        tree = git(repo, "write-tree", env=env, capture=True)
    return tree, both


def land(repo: pathlib.Path, stamp: str, code: str, attempts: int = 2) -> None:
    """Put HEAD's daily commits on origin/main without moving the checkout's code.

    Fast-forward when origin/main is an ancestor of HEAD. Otherwise push a merge commit
    built by overlay_tree(); its second parent is the day's commit, so main records which
    code wrote the data. A push that loses a race with a session's push fetches and
    rebuilds once."""
    for attempt in range(attempts):
        if attempt:
            git(repo, "fetch", "--quiet", "origin")
        if is_ancestor(repo, "origin/main", "HEAD"):
            target, how = "HEAD", "fast-forward"
        else:
            tree, _ = overlay_tree(repo, main_wins=False)
            head = git(repo, "rev-parse", "HEAD", capture=True)
            message = (
                "Land daily run " + stamp + " from " + repo.name + " pin\n\n"
                "The data is pin commit " + head + ", written by code " + code + " in "
                + str(repo) + ". Files the run changed come from that commit; every other "
                "file is origin/main's.\n")
            target = git(repo, "commit-tree", tree, "-p", "origin/main", "-p", "HEAD",
                         "-m", message, capture=True)
            how = "merge " + target[:12]
        try:
            git(repo, "push", "--quiet", "origin", target + ":refs/heads/main")
        except subprocess.CalledProcessError:
            if attempt + 1 < attempts:
                print("RETRY", repo.name, "push rejected or failed; fetching", flush=True)
                continue
            raise
        print("LANDED", repo.name, how, flush=True)
        return


def commit_and_land(repo: pathlib.Path, day: dt.date, code: str) -> None:
    stamp = day.strftime("%Y%m%d")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "--allow-empty", "-m", "Daily run " + stamp)
    land(repo, stamp, code)


def execute(day: dt.date) -> int:
    stage = "preflight"
    claim = None
    last_step = None
    if not present(WATER):
        print("SKIPPED water — no checkout at " + str(WATER), file=sys.stderr, flush=True)
        print("RESULT FAILED stage=preflight reason=no_water_checkout path=" + str(WATER),
              file=sys.stderr, flush=True)
        return 1
    swim_present = present(SWIM)
    if not swim_present:
        print("SKIPPED swim — no checkout at " + str(SWIM), file=sys.stderr, flush=True)
    steps = [step for step in plan(day) if swim_present or not step.name.startswith("swim.")]
    repos = (WATER, SWIM) if swim_present else (WATER,)
    try:
        check_paths(steps)
        code = {repo: guard(repo) for repo in repos}
        prior = already_collected(day, repos)
        if prior:
            print("RESULT SKIPPED reason=existing_daily_commit repo=" + prior +
                  " day=" + day.isoformat(), flush=True)
            return 0
        stage = "claim"
        claim = claim_day(day)
        if claim is None:
            print("RESULT SKIPPED reason=day_already_attempted day=" + day.isoformat(), flush=True)
            return 0
        water_steps = [step for step in steps if step.name.startswith("water.")]
        swim_steps = [step for step in steps if step.name.startswith("swim.")]
        for step in water_steps:
            stage = last_step = step.name
            run_command(step)
            progress(claim, "running", step.name)
        stage = "water.validate"
        validate_bundle()
        stage = "water.land"
        commit_and_land(WATER, day, code[WATER])
        if not swim_present:
            progress(claim, "failed", "swim.preflight")
            print("RESULT FAILED stage=swim.preflight reason=no_swim_checkout path=" + str(SWIM) +
                  " water=published day=" + day.isoformat(), file=sys.stderr, flush=True)
            return 1
        for step in swim_steps:
            stage = last_step = step.name
            run_command(step)
            progress(claim, "running", step.name)
        stage = "swim.land"
        commit_and_land(SWIM, day, code[SWIM])
        progress(claim, "complete", "swim.land")
        print("RESULT OK day=" + day.isoformat() + " water=published swim=assessed", flush=True)
        return 0
    except (OSError, subprocess.CalledProcessError, RuntimeError, ValueError, KeyError) as exc:
        print("ERROR", stage, str(exc), file=sys.stderr, flush=True)
        if claim is not None:
            try:
                progress(claim, "failed", stage)
            except OSError as state_error:
                print("ERROR state_write", str(state_error), file=sys.stderr, flush=True)
        print("RESULT FAILED stage=" + stage + " reason=command_or_validation_error",
              file=sys.stderr, flush=True)
        return 1


def take_run_lock():
    """The scheduled run's lock file, held, or None while a run holds it."""
    RUN_LOCK.parent.mkdir(parents=True, exist_ok=True)
    handle = open(RUN_LOCK, "a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def test_in_scratch(repo: pathlib.Path) -> None:
    """Run the repo's suite in a throwaway worktree of HEAD: the swim suite rewrites
    tracked files (app/status.json), which would leave the pin dirty."""
    with tempfile.TemporaryDirectory() as temp:
        scratch = pathlib.Path(temp) / repo.name
        git(repo, "worktree", "add", "--quiet", "--detach", str(scratch), "HEAD")
        try:
            subprocess.run((str(PYTHON), "-m", "unittest", "discover", "-s", "tests"),
                           cwd=scratch, check=True)
        finally:
            git(repo, "worktree", "remove", "--force", str(scratch))


def promote(repos: tuple[pathlib.Path, ...]) -> int:
    """Move each pin's code to origin/main: the one deliberate way code reaches the run.

    Day commits a landing could not push (a file changed on both sides) land here, with
    main's copy of each such file; the next run rewrites it from the store. The promoted
    code must pass the --check paths and both suites, or every moved pin goes back."""
    lock = take_run_lock()
    if lock is None:
        print("RESULT FAILED stage=promote reason=daily_run_in_progress lock=" + str(RUN_LOCK),
              file=sys.stderr, flush=True)
        return 1
    moved = []
    stage = "promote.guard"
    try:
        for repo in repos:
            if not present(repo):
                raise RuntimeError("no checkout at " + str(repo))
            guard(repo)
            old = git(repo, "rev-parse", "HEAD", capture=True)
            days = off_main(repo, daily=True)
            note = ""
            if days:
                stage = "promote.land"
                tree, both = overlay_tree(repo, main_wins=True)
                message = ("Promote " + repo.name + " pin and land " + str(len(days)) +
                           " daily commits\n\nKept origin/main's copy of " + str(len(both)) +
                           " files both sides changed: " + ", ".join(both[:20]) + "\n")
                target = git(repo, "commit-tree", tree, "-p", "origin/main", "-p", "HEAD",
                             "-m", message, capture=True)
                git(repo, "push", "--quiet", "origin", target + ":refs/heads/main")
                note = " landed=" + ",".join(days) + " main_copy=" + str(len(both))
            else:
                target = "origin/main"
            stage = "promote.move"
            git(repo, "merge", "--quiet", "--ff-only", target)
            moved.append((repo, old))
            print("PROMOTE", repo.name, old[:12], "->",
                  git(repo, "rev-parse", "HEAD", capture=True)[:12] + note, flush=True)
        stage = "promote.check"
        check_paths([step for step in plan(dt.datetime.now(LOCAL_TZ).date())
                     if step.repo in repos])
        for repo in repos:
            stage = "promote.tests." + repo.name
            test_in_scratch(repo)
    except (OSError, subprocess.CalledProcessError, RuntimeError, ValueError) as exc:
        print("ERROR", stage, str(exc), file=sys.stderr, flush=True)
        for repo, old in moved:
            git(repo, "reset", "--quiet", "--keep", old)
            print("ROLLBACK", repo.name, "->", old[:12], file=sys.stderr, flush=True)
        print("RESULT FAILED stage=" + stage, file=sys.stderr, flush=True)
        return 1
    finally:
        lock.close()
    print("RESULT OK mode=promote", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="offline command and path check")
    parser.add_argument("--promote", action="store_true",
                        help="move both pins' code to origin/main, then check and test it")
    args = parser.parse_args()
    if args.promote:
        return promote((WATER, SWIM))
    day = dt.datetime.now(LOCAL_TZ).date()
    steps = plan(day)
    if args.check:
        for repo in (WATER, SWIM):
            if present(repo):
                print("CHECKOUT", repo.name, "path=" + str(repo), "branch=" +
                      (git(repo, "branch", "--show-current", capture=True) or "(detached)"),
                      "code=" + code_commit(repo)[:12])
            else:
                print("SKIPPED", repo.name, "— no checkout at " + str(repo))
        check_paths(steps)
        for step in steps:
            print(step.name, step.repo.name, *step.args)
        print("RESULT OK mode=check steps=" + str(len(steps)))
        return 0
    return execute(day)


if __name__ == "__main__":
    sys.exit(main())
