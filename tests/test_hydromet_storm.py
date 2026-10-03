import unittest
from tools import hydromet as h
class StormRainTests(unittest.TestCase):
    def test_box_edges_missing_and_other_agency(self):
        rows=[dict(site='a',agency='LCRA',site_type='rain',lat=29.9,lon=-100.2),dict(site='b',agency='LCRA',site_type='rain',lat=30.9,lon=-97.9)]
        rows += [{**rows[0],'site':'c','lat':None},{**rows[0],'site':'d','agency':'COA'},{**rows[0],'site':'e','lat':29.89}]
        self.assertEqual(h.hill_country_rain_sites(rows),['a','b'])
    def test_river_with_rain_sensor_is_included(self):
        rows=[dict(site='river',agency='LCRA',site_type='river',lat=30,lon=-99,rain_in={'1Day':0})]
        self.assertEqual(h.hill_country_rain_sites(rows),['river'])

    def test_rain_refusal_preserved_without_retry(self):
        import datetime as dt, gzip, json, tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(h,'ROOT',root),patch.object(h,'RAW',root/'raw'),patch.object(h,'CAP',root/'captures'),patch.object(h,'fetch',return_value=(b'refused',403,'Forbidden')) as fetch,patch.object(h.time,'sleep') as pause:
                h.rain_window(['fixture'],dt.date(2026,1,1),dt.date(2026,1,2),pause=.5)
                self.assertEqual(fetch.call_count,1); pause.assert_called_once_with(.5)
                entry=next(iter(h.load_manifest('LCRA','fixture')['windows'].values()))
                raw=root/entry['raw_path']; self.assertEqual(raw.read_bytes(),b'refused')
                self.assertTrue(raw.with_suffix('.meta.json').exists())
                self.assertEqual(gzip.decompress((h.CAP/entry['file']).read_bytes()),b'refused')
                self.assertEqual(entry['status'],403)
