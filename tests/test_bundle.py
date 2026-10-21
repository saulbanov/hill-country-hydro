import datetime as dt
import json, tempfile, unittest
from pathlib import Path
from unittest import mock
from tools import publish_bundle as pb
ROOT = Path(__file__).resolve().parents[1]
AUSTIN_TEN = ['08154700', '08155240', '08155300', '08155400', '08155500', '08156800', '08158827', '08158930', '08158970', '08159000']
class BundleTests(unittest.TestCase):
    def test_bundle_carries_every_station_a_lens_cites_and_no_verdict(self):
        b = pb.build()
        self.assertEqual(b['schema_version'], pb.SCHEMA_VERSION)
        for sid in AUSTIN_TEN: self.assertIn(sid, b['stations'], sid)
        s = b['stations']['08154700']; self.assertIn('source', s)
        for sid, station in b['stations'].items():
            ledger = pb.load(pb.MODEL / f'{sid}-event-ledger.json')
            definition = (ledger or {}).get('event_definition')
            expected = ({'high': definition['high_threshold'], 'low': definition['low_threshold'],
                         'unit': definition['unit']} if definition else None)
            self.assertEqual(station['thresholds'], expected, sid)
        self.assertNotIn('status', s); self.assertNotIn('verdict', json.dumps(b['stations'])[:200000].lower().replace('no verdict', '').replace('verdict about', ''))
        for sid, st in b['stations'].items():
            for p, v in st['latest'].items(): self.assertIn('observed_at', v); self.assertIn('fresh_within_1h', v)
        self.assertIsInstance(b['missing_inputs'], list)
        if (ROOT / 'app/hydromet.json').exists():
            h = b['hydromet']; self.assertIn('COA:950', h['sites']); self.assertEqual(h['sites']['COA:950']['creek'], 'williamson-creek'); self.assertIn('LCRA:3992', h['sites'])
            for s in h['sites'].values(): self.assertNotIn('status', s); self.assertIn('fresh_within_1h', s)
            self.assertEqual(b['counts']['hydromet_sites'], len(h['sites']))

    def test_thresholds_project_the_source_ledger_without_recomputing_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); app = root / 'app'; model = root / 'data/model'
            app.mkdir(); model.mkdir(parents=True)
            (root / 'data/usgs-locations-regional.json').write_text(json.dumps({
                'locations': [{'id': 'fixture', 'lat': 30, 'lon': -98}]}))
            (model / 'fixture-event-ledger.json').write_text(json.dumps({
                'event_definition': {'high_threshold': 123.5, 'low_threshold': 6.25, 'unit': 'cfs'}}))
            with mock.patch.multiple(pb, ROOT=root, APP=app, MODEL=model):
                bundle = pb.build(at=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))
            self.assertEqual(bundle['stations']['fixture']['thresholds'],
                             {'high': 123.5, 'low': 6.25, 'unit': 'cfs'})
if __name__ == '__main__': unittest.main()
