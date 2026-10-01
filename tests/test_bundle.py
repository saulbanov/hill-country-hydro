import json, unittest
from pathlib import Path
from tools import publish_bundle as pb
ROOT = Path(__file__).resolve().parents[1]
AUSTIN_TEN = ['08154700', '08155240', '08155300', '08155400', '08155500', '08156800', '08158827', '08158930', '08158970', '08159000']
class BundleTests(unittest.TestCase):
    def test_bundle_carries_every_station_a_lens_cites_and_no_verdict(self):
        b = pb.build()
        self.assertEqual(b['schema_version'], pb.SCHEMA_VERSION)
        for sid in AUSTIN_TEN: self.assertIn(sid, b['stations'], sid)
        s = b['stations']['08154700']; self.assertEqual(s['thresholds']['high'], 45.0); self.assertIn('source', s)
        self.assertNotIn('status', s); self.assertNotIn('verdict', json.dumps(b['stations'])[:200000].lower().replace('no verdict', '').replace('verdict about', ''))
        for sid, st in b['stations'].items():
            for p, v in st['latest'].items(): self.assertIn('observed_at', v); self.assertIn('fresh_within_1h', v)
        self.assertIsInstance(b['missing_inputs'], list)
if __name__ == '__main__': unittest.main()
