"""Offline fault tests for the Mac scheduler; no collector or Git command runs."""

import datetime as dt
import json
import pathlib
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
        for fault, water_pushed, swim_pushed in cases:
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temp:
                claim = job.claim_day(day, pathlib.Path(temp))
                seen = []
                pushed = []

                def fake_run(step):
                    seen.append(step.name)
                    if step.name == fault:
                        raise RuntimeError("injected_failure")

                with mock.patch.object(job, "check_paths"), \
                     mock.patch.object(job, "sync_repos"), \
                     mock.patch.object(job, "already_collected", return_value=None), \
                     mock.patch.object(job, "claim_day", return_value=claim), \
                     mock.patch.object(job, "run_command", side_effect=fake_run), \
                     mock.patch.object(job, "validate_bundle"), \
                     mock.patch.object(job, "commit_and_push",
                                       side_effect=lambda repo, date: pushed.append(repo)):
                    with mock.patch("builtins.print"):
                        result = job.execute(day)
                self.assertEqual(1, result)
                self.assertEqual(fault, seen[-1])
                self.assertEqual(water_pushed, job.WATER in pushed)
                self.assertEqual(swim_pushed, job.SWIM in pushed)
                self.assertEqual("failed", json.loads(claim.read_text())["status"])

    def test_existing_daily_commit_skips_all_collectors(self):
        day = dt.date(2026, 10, 2)
        with mock.patch.object(job, "check_paths"), \
             mock.patch.object(job, "sync_repos"), \
             mock.patch.object(job, "already_collected", return_value="hill-country-hydro"), \
             mock.patch.object(job, "claim_day") as claim, \
             mock.patch.object(job, "run_command") as run:
            with mock.patch("builtins.print"):
                self.assertEqual(0, job.execute(day))
        claim.assert_not_called()
        run.assert_not_called()

    def test_wrong_branch_stops_before_fetch_or_collection(self):
        calls = []

        def fake_git(repo, *args, capture=False):
            calls.append(args)
            if args == ("rev-parse", "--show-toplevel"):
                return str(repo)
            if args == ("branch", "--show-current"):
                return "unrelated-work"
            self.fail("Git mutation attempted on a non-main branch")

        with mock.patch.object(job, "git", side_effect=fake_git):
            with self.assertRaisesRegex(RuntimeError, "not_main_"):
                job.sync_repos()
        self.assertEqual(2, len(calls))

    def test_water_validation_and_push_failures_block_swim(self):
        day = dt.date(2026, 10, 3)
        for fault in ("water.validate", "water.push"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temp:
                claim = job.claim_day(day, pathlib.Path(temp))
                seen = []

                def fake_push(repo, date):
                    if fault == "water.push":
                        raise RuntimeError("injected_push_failure")

                def fake_validate():
                    if fault == "water.validate":
                        raise RuntimeError("injected_validation_failure")

                with mock.patch.object(job, "check_paths"), \
                     mock.patch.object(job, "sync_repos"), \
                     mock.patch.object(job, "already_collected", return_value=None), \
                     mock.patch.object(job, "claim_day", return_value=claim), \
                     mock.patch.object(job, "run_command",
                                       side_effect=lambda step: seen.append(step.name)), \
                     mock.patch.object(job, "validate_bundle", side_effect=fake_validate), \
                     mock.patch.object(job, "commit_and_push", side_effect=fake_push):
                    with mock.patch("builtins.print"):
                        self.assertEqual(1, job.execute(day))
                self.assertTrue(seen)
                self.assertTrue(all(name.startswith("water.") for name in seen))
                self.assertEqual(fault, json.loads(claim.read_text())["last_step"])


if __name__ == "__main__":
    unittest.main()
