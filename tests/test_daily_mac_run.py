"""Offline tests for the Mac scheduler. No collector runs; the Git tests use throwaway
repositories with a local bare origin, so no network request is made."""

import datetime as dt
import fcntl
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from tools import daily_mac_run as job


class DailyMacRunTests(unittest.TestCase):
    def test_plan_keeps_water_before_swim_and_sunday_histories(self):
        friday = job.plan(dt.date(2026, 10, 2))
        sunday = job.plan(dt.date(2026, 10, 4))
        first_swim = next(i for i, step in enumerate(friday)
                          if step.name.startswith("swim."))
        self.assertTrue(all(s.name.startswith("water.") for s in friday[:first_swim]))
        self.assertTrue(all(s.name.startswith("swim.") for s in friday[first_swim:]))
        self.assertNotIn("water.usgs_daily_collect", [s.name for s in friday])
        self.assertIn("water.usgs_daily_collect", [s.name for s in sunday])
        self.assertLess([s.name for s in sunday].index("water.event_ledger"),
                        [s.name for s in sunday].index("water.publish_bundle"))
        self.assertFalse(any("cloud_capture_export" in " ".join(s.args)
                             for s in sunday))
        for steps, versioned in ((friday, False), (sunday, True)):
            eaa = next(s for s in steps if s.name == "water.eaa_details")
            self.assertEqual("details", eaa.args[2])
            self.assertEqual(versioned, "--version" in eaa.args)
            self.assertNotIn("water.eaa_collect", [s.name for s in steps])

    def test_lens_reads_the_bundle_from_the_water_checkout_that_ran(self):
        fetch = next(s for s in job.plan(dt.date(2026, 10, 2)) if s.name == "swim.bundle_fetch")
        self.assertEqual(("--from", str(job.WATER / "dist" / "water-state.json")), fetch.args[-2:])

    def test_one_claim_per_day_even_after_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            state = pathlib.Path(temp)
            day = dt.date(2026, 10, 3)
            first = job.claim_day(day, state)
            self.assertIsNotNone(first)
            job.progress(first, "failed", "water.eaa_details")
            self.assertIsNone(job.claim_day(day, state))
            self.assertEqual("failed", json.loads(first.read_text())["status"])
            self.assertIsNotNone(job.claim_day(day + dt.timedelta(days=1), state))

    def test_repeated_faults_stop_before_unrelated_collection(self):
        # Different injected failures exercise water and swim boundaries.
        cases = [
            ("water.usgs_collect", False, 0),
            ("water.eaa_details", False, 0),
            ("water.publish_bundle", False, 0),
            ("swim.coa_collect", True, 0),
            ("swim.assess", True, 0),
        ]
        day = dt.date(2026, 10, 3)
        for fault, water_landed, swim_landed in cases:
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temp:
                claim = job.claim_day(day, pathlib.Path(temp))
                seen = []
                landed = []

                def fake_run(step):
                    seen.append(step.name)
                    if step.name == fault:
                        raise RuntimeError("injected_failure")

                with mock.patch.object(job, "present", return_value=True), \
                     mock.patch.object(job, "check_paths"), \
                     mock.patch.object(job, "guard", return_value="c0de"), \
                     mock.patch.object(job, "already_collected", return_value=None), \
                     mock.patch.object(job, "claim_day", return_value=claim), \
                     mock.patch.object(job, "run_command", side_effect=fake_run), \
                     mock.patch.object(job, "validate_bundle"), \
                     mock.patch.object(job, "commit_and_land",
                                       side_effect=lambda repo, date, code: landed.append(repo)):
                    with mock.patch("builtins.print"):
                        result = job.execute(day)
                self.assertEqual(1, result)
                self.assertEqual(fault, seen[-1])
                self.assertEqual(water_landed, job.WATER in landed)
                self.assertEqual(swim_landed, job.SWIM in landed)
                self.assertEqual("failed", json.loads(claim.read_text())["status"])

    def test_existing_daily_commit_skips_all_collectors(self):
        day = dt.date(2026, 10, 2)
        with mock.patch.object(job, "present", return_value=True), \
             mock.patch.object(job, "check_paths"), \
             mock.patch.object(job, "guard", return_value="c0de"), \
             mock.patch.object(job, "already_collected", return_value="hill-country-hydro"), \
             mock.patch.object(job, "claim_day") as claim, \
             mock.patch.object(job, "run_command") as run:
            with mock.patch("builtins.print"):
                self.assertEqual(0, job.execute(day))
        claim.assert_not_called()
        run.assert_not_called()

    def test_water_validation_and_landing_failures_block_swim(self):
        day = dt.date(2026, 10, 3)
        for fault in ("water.validate", "water.land"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temp:
                claim = job.claim_day(day, pathlib.Path(temp))
                seen = []

                def fake_land(repo, date, code):
                    if fault == "water.land":
                        raise RuntimeError("injected_land_failure")

                def fake_validate():
                    if fault == "water.validate":
                        raise RuntimeError("injected_validation_failure")

                with mock.patch.object(job, "present", return_value=True), \
                     mock.patch.object(job, "check_paths"), \
                     mock.patch.object(job, "guard", return_value="c0de"), \
                     mock.patch.object(job, "already_collected", return_value=None), \
                     mock.patch.object(job, "claim_day", return_value=claim), \
                     mock.patch.object(job, "run_command",
                                       side_effect=lambda step: seen.append(step.name)), \
                     mock.patch.object(job, "validate_bundle", side_effect=fake_validate), \
                     mock.patch.object(job, "commit_and_land", side_effect=fake_land):
                    with mock.patch("builtins.print"):
                        self.assertEqual(1, job.execute(day))
                self.assertTrue(seen)
                self.assertTrue(all(name.startswith("water.") for name in seen))
                self.assertEqual(fault, json.loads(claim.read_text())["last_step"])

    def test_missing_swim_checkout_publishes_water_then_fails_naming_the_path(self):
        day = dt.date(2026, 10, 3)
        with tempfile.TemporaryDirectory() as temp:
            gone = pathlib.Path(temp) / "no-such-swim"
            claim = job.claim_day(day, pathlib.Path(temp))
            seen, landed, said = [], [], []
            with mock.patch.object(job, "SWIM", gone), \
                 mock.patch.object(job, "present", side_effect=lambda repo: repo != gone), \
                 mock.patch.object(job, "check_paths"), \
                 mock.patch.object(job, "guard", return_value="c0de") as guard, \
                 mock.patch.object(job, "already_collected", return_value=None), \
                 mock.patch.object(job, "claim_day", return_value=claim), \
                 mock.patch.object(job, "run_command", side_effect=lambda s: seen.append(s.name)), \
                 mock.patch.object(job, "validate_bundle"), \
                 mock.patch.object(job, "commit_and_land",
                                   side_effect=lambda repo, date, code: landed.append(repo)), \
                 mock.patch("builtins.print", side_effect=lambda *a, **k: said.append(" ".join(map(str, a)))):
                self.assertEqual(1, job.execute(day))
            self.assertEqual([job.WATER], [call.args[0] for call in guard.call_args_list])
            self.assertEqual([job.WATER], landed)
            self.assertFalse(any(name.startswith("swim.") for name in seen))
            self.assertIn("SKIPPED swim — no checkout at " + str(gone), said)
            self.assertTrue(said[-1].startswith("RESULT FAILED stage=swim.preflight"))

    def test_missing_water_checkout_runs_nothing(self):
        with mock.patch.object(job, "WATER", pathlib.Path("/no/such/water")), \
             mock.patch.object(job, "run_command") as run, \
             mock.patch("builtins.print"):
            self.assertEqual(1, job.execute(dt.date(2026, 10, 3)))
        run.assert_not_called()


def sh(cwd, *args):
    return subprocess.run(("/usr/bin/git", *args), cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


class PinGitTests(unittest.TestCase):
    """A bare origin, a session clone that pushes to main, and a pin on its own branch."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = pathlib.Path(temp.name)
        config = root / "gitconfig"
        config.write_text("[user]\n\tname = Test\n\temail = test@example.com\n"
                          "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n")
        env = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(config),
                                           "GIT_CONFIG_NOSYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)
        quiet = mock.patch("builtins.print")
        quiet.start()
        self.addCleanup(quiet.stop)
        self.origin = root / "origin.git"
        sh(root, "init", "--quiet", "--bare", str(self.origin))
        self.dev = root / "dev"
        sh(root, "clone", "--quiet", str(self.origin), str(self.dev))
        for name, text in (("tools/run.py", "v1\n"), ("data/x.json", "{}\n"), ("data/y.json", "{}\n")):
            self.write(self.dev, name, text)
        self.push_from_dev("code v1")
        self.pin = root / "pin"
        sh(root, "clone", "--quiet", str(self.origin), str(self.pin))
        sh(self.pin, "switch", "--quiet", "-c", "runtime/test")
        self.lock = mock.patch.object(job, "RUN_LOCK", root / "run.lock")
        self.lock.start()
        self.addCleanup(self.lock.stop)
        self.day = dt.date(2026, 10, 9)

    def write(self, repo, name, text):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def push_from_dev(self, message):
        sh(self.dev, "add", "-A")
        sh(self.dev, "commit", "--quiet", "-m", message)
        sh(self.dev, "push", "--quiet", "origin", "HEAD:main")

    def origin_main(self, *args):
        return sh(self.origin, *args)

    def run_day(self, x=None, y=None):
        code = job.guard(self.pin)
        if x is not None:
            self.write(self.pin, "data/x.json", x)
        if y is not None:
            self.write(self.pin, "data/y.json", y)
        job.commit_and_land(self.pin, self.day, code)
        return code

    def test_fast_forward_when_main_has_not_moved(self):
        start = sh(self.pin, "rev-parse", "HEAD")
        self.run_day(y='{"day": 9}\n')
        self.assertEqual(sh(self.pin, "rev-parse", "HEAD"), self.origin_main("rev-parse", "main"))
        self.assertEqual("Daily run 20261009", self.origin_main("log", "-1", "--format=%s", "main"))
        self.assertEqual(start, job.code_commit(self.pin))

    def test_merge_keeps_session_code_off_the_pin_and_names_the_code(self):
        self.write(self.dev, "tools/run.py", "v2\n")
        self.push_from_dev("code v2")
        session_tip = self.origin_main("rev-parse", "main")
        code = self.run_day(y='{"day": 9}\n')
        parents = self.origin_main("log", "-1", "--format=%P", "main").split()
        self.assertEqual([session_tip, sh(self.pin, "rev-parse", "HEAD")], parents)
        self.assertEqual("v2", self.origin_main("show", "main:tools/run.py"))
        self.assertEqual('{"day": 9}', self.origin_main("show", "main:data/y.json"))
        self.assertIn(code, self.origin_main("log", "-1", "--format=%B", "main"))
        self.assertEqual("v1\n", (self.pin / "tools/run.py").read_text())
        sh(self.dev, "fetch", "--quiet")
        self.assertEqual("dev", job.already_collected(self.day, (self.dev,)))

    def test_a_file_changed_on_both_sides_stops_the_landing(self):
        self.write(self.dev, "data/x.json", '{"backfill": true}\n')
        self.push_from_dev("session backfill")
        before = self.origin_main("rev-parse", "main")
        with self.assertRaisesRegex(RuntimeError, "land_conflict"):
            self.run_day(x='{"day": 9}\n', y='{"day": 9}\n')
        self.assertEqual(before, self.origin_main("rev-parse", "main"))

    def test_promote_lands_stranded_days_with_mains_copy_and_moves_the_code(self):
        self.write(self.dev, "data/x.json", '{"backfill": true}\n')
        self.write(self.dev, "tools/run.py", "v2\n")
        self.push_from_dev("session backfill and code")
        with self.assertRaises(RuntimeError):
            self.run_day(x='{"day": 9}\n', y='{"day": 9}\n')
        self.assertEqual(1, len(job.off_main(self.pin, daily=True)))
        with mock.patch.object(job, "check_paths"), mock.patch.object(job, "test_in_scratch"):
            self.assertEqual(0, job.promote((self.pin,)))
        self.assertEqual(sh(self.pin, "rev-parse", "HEAD"), self.origin_main("rev-parse", "main"))
        self.assertEqual('{"backfill": true}', self.origin_main("show", "main:data/x.json"))
        self.assertEqual('{"day": 9}', self.origin_main("show", "main:data/y.json"))
        self.assertEqual("v2\n", (self.pin / "tools/run.py").read_text())
        self.assertEqual([], job.off_main(self.pin, daily=True))
        job.guard(self.pin)

    def test_promote_rolls_back_when_the_promoted_code_fails_its_tests(self):
        old = sh(self.pin, "rev-parse", "HEAD")
        self.write(self.dev, "tools/run.py", "v2\n")
        self.push_from_dev("code v2")
        failing = mock.patch.object(job, "test_in_scratch",
                                    side_effect=subprocess.CalledProcessError(1, "unittest"))
        with mock.patch.object(job, "check_paths"), failing:
            self.assertEqual(1, job.promote((self.pin,)))
        self.assertEqual(old, sh(self.pin, "rev-parse", "HEAD"))
        self.assertEqual("v1\n", (self.pin / "tools/run.py").read_text())

    def test_promote_waits_for_a_running_day(self):
        old = sh(self.pin, "rev-parse", "HEAD")
        self.write(self.dev, "tools/run.py", "v2\n")
        self.push_from_dev("code v2")
        with open(job.RUN_LOCK, "a+") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(1, job.promote((self.pin,)))
        self.assertEqual(old, sh(self.pin, "rev-parse", "HEAD"))

    def test_guard_refuses_code_committed_in_the_pin_and_a_dirty_pin(self):
        self.write(self.pin, "tools/run.py", "hotfix\n")
        with self.assertRaisesRegex(RuntimeError, "dirty"):
            job.guard(self.pin)
        sh(self.pin, "commit", "--quiet", "-am", "hotfix in the pin")
        with self.assertRaisesRegex(RuntimeError, "code_not_on_main"):
            job.guard(self.pin)

    def test_guard_refuses_a_detached_checkout(self):
        sh(self.pin, "switch", "--quiet", "--detach")
        with self.assertRaisesRegex(RuntimeError, "detached_head"):
            job.guard(self.pin)


if __name__ == "__main__":
    unittest.main()
