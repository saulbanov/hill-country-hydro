"""Validation must retain current coverage and comparable trigger identities."""
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import storm_validation as validation


class StormValidationTests(unittest.TestCase):
    def test_coverage_advances_with_new_usgs_readings(self):
        with sqlite3.connect(':memory:') as db:
            db.execute('create table observations(station_id, observed_at)')
            db.executemany('insert into observations values (?, ?)', [
                ('USGS-fixture', '2026-10-02T12:10:00+00:00'),
                ('USGS-fixture', '2026-10-03T12:00:00+00:00'),
                ('OTHER-fixture', '2026-10-04T12:00:00+00:00'),
            ])
            days, latest = validation.observation_coverage(db)
        self.assertEqual(latest, '2026-10-03T12:00:00+00:00')
        self.assertEqual([d['day'] for d in days], ['2026-10-02'])
        self.assertEqual(days[0]['rows'], 1)

    def test_empty_coverage_is_unknown(self):
        with sqlite3.connect(':memory:') as db:
            db.execute('create table observations(station_id, observed_at)')
            self.assertEqual(validation.observation_coverage(db), ([], None))

    def test_trigger_evidence_does_not_make_matching_identity_differ(self):
        trigger = dict(station='fixture', at='2026-10-01T12:30:00-05:00',
                       threshold_cfs=21, reading={'value': 22})
        self.assertEqual(validation.crossing_identity(trigger),
                         dict(station='fixture', at='2026-10-01T17:30:00Z'))
        self.assertEqual(trigger['reading'], {'value': 22})
