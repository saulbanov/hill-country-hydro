#!/usr/bin/env python3
"""One guarded local water-ledger run followed by the swim-lens run.

The dated claim is written before the first provider request. An interrupted run
cannot silently retry a partly collected day. Use --check for an offline plan
and path check; it makes no provider or Git network request.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
from dataclasses import dataclass
from zoneinfo import ZoneInfo


WATER = pathlib.Path(__file__).resolve().parents[1]
SWIM = WATER.parent / "swimming-hole-alerts"
STATE_DIR = WATER / "data" / "raw" / "mac-daily-run"
LOCAL_TZ = ZoneInfo("America/Chicago")
PYTHON = pathlib.Path("/opt/homebrew/bin/python3")


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
        python_step("water.eaa_collect", w, "eaa", "collect", "--pause-seconds", "4"),
        python_step("water.eaa_normalize", w, "eaa", "normalize"),
        python_step("water.eaa_assess", w, "eaa", "assess"),
        python_step("water.hydromet_collect", w, "hydromet", "collect"),
        python_step("water.hydromet_history", w, "hydromet", "history", "--recent-only"),
        python_step("water.hydromet_normalize", w, "hydromet", "normalize"),
        python_step("water.hydromet_assess", w, "hydromet", "assess"),
        python_step("water.hazards_assess", w, "hazards", "assess"),
        python_step("water.weather_collect", w, "weather_validation", "collect"),
        python_step("water.weather_validate", w, "weather_validation", "validate"),
    ]
    if day.weekday() == 6:  # Sunday: refresh histories before context and publishing.
        steps.extend([
            python_step("water.usgs_daily_collect", w, "usgs_history", "collect"),
            python_step("water.usgs_daily_normalize", w, "usgs_history", "normalize"),
            python_step("water.usgs_series_collect", w, "usgs_series_history", "collect"),
            python_step("water.usgs_series_normalize", w, "usgs_series_history", "normalize"),
            python_step("water.event_ledger", w, "event_ledger"),
        ])
    steps.extend([
        python_step("water.hydro_context", w, "hydro_context"),
        python_step("water.publish_bundle", w, "publish_bundle"),
        Step("water.tests", w, (str(PYTHON), "-m", "unittest", "discover", "-s", "tests")),
    ])
    steps.extend([
        python_step("swim.bundle_fetch", s, "water_bundle", "fetch"),
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
        Step("swim.tests", s, (str(PYTHON), "-m", "unittest", "discover", "-s", "tests")),
    ])
    return steps


def run_command(step: Step) -> None:
    print("RUN", step.name, *step.args, flush=True)
    subprocess.run(step.args, cwd=step.repo, check=True)


def git(repo: pathlib.Path, *args: str, capture: bool = False) -> str:
    result = subprocess.run(
        ("/usr/bin/git", *args), cwd=repo, check=True,
        text=True, capture_output=capture,
    )
    return result.stdout.strip() if capture else ""


def check_paths(steps: list[Step]) -> None:
    if not PYTHON.is_file():
        raise RuntimeError("missing_python")
    for repo in (WATER, SWIM):
        if not (repo / ".git").exists():
            raise RuntimeError("missing_repo_" + repo.name)
    for step in steps:
        if len(step.args) > 1 and step.args[1].startswith("tools/"):
            if not (step.repo / step.args[1]).is_file():
                raise RuntimeError("missing_tool_" + step.name)


def sync_repos() -> None:
    for repo in (WATER, SWIM):
        actual = git(repo, "rev-parse", "--show-toplevel", capture=True)
        if pathlib.Path(actual).resolve() != repo.resolve():
            raise RuntimeError("wrong_repo_" + repo.name)
        if git(repo, "status", "--porcelain", capture=True):
            raise RuntimeError("dirty_repo_" + repo.name)
        print("SYNC", repo.name, flush=True)
        git(repo, "fetch", "origin")
        git(repo, "merge", "--ff-only", "origin/main")
        if git(repo, "status", "--porcelain", capture=True):
            raise RuntimeError("dirty_after_sync_" + repo.name)


def already_collected(day: dt.date) -> str | None:
    message = "Daily run " + day.strftime("%Y%m%d")
    for repo in (WATER, SWIM):
        subjects = git(repo, "log", "--format=%s", "--grep=^" + message + "$",
                       capture=True).splitlines()
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


def commit_and_push(repo: pathlib.Path, day: dt.date) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "--allow-empty", "-m", "Daily run " + day.strftime("%Y%m%d"))
    git(repo, "push", "origin", "main")


def execute(day: dt.date) -> int:
    steps = plan(day)
    stage = "preflight"
    claim = None
    last_step = None
    try:
        check_paths(steps)
        sync_repos()
        prior = already_collected(day)
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
        stage = "water.push"
        commit_and_push(WATER, day)
        for step in swim_steps:
            stage = last_step = step.name
            run_command(step)
            progress(claim, "running", step.name)
        stage = "swim.push"
        commit_and_push(SWIM, day)
        progress(claim, "complete", "swim.push")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="offline command and path check")
    args = parser.parse_args()
    day = dt.datetime.now(LOCAL_TZ).date()
    steps = plan(day)
    if args.check:
        check_paths(steps)
        for step in steps:
            print(step.name, step.repo.name, *step.args)
        print("RESULT OK mode=check steps=" + str(len(steps)))
        return 0
    return execute(day)


if __name__ == "__main__":
    sys.exit(main())
