import datetime as dt, json, sqlite3, tempfile, unittest
from pathlib import Path
from tools import reservoirs as rv, eaa, regional_inventory as ri
RES_CSV = """# ---- Disclaimer ----
# provider text kept verbatim
date,water_level,surface_area,reservoir_storage,conservation_storage,percent_full,conservation_capacity,dead_pool_capacity
2026-09-29,674.90,17600.0,1000000,983000,89.5,1098044,17032
2026-09-30,674.59,17559.65,997736,980704,89.3,1098044,17032
2026-10-01,NA,,,,,1098044,17032
"""
EAA_CSV = """# Data Provided by the Edwards Aquifer Authority (EAA)
# ALL DATA ARE PROVISIONAL UNLESS OTHERWISE STATED
J17,2026-09-29,638.10,P,2026-09-30
J17,2026-09-30,638.33,P,2026-10-01
J17,2026-10-01,,P,2026-10-01
"""
class ReservoirTests(unittest.TestCase):
    def test_disclaimer_lines_and_blank_values_never_become_numbers(self):
        rows = rv.parse_rows(RES_CSV); self.assertEqual(len(rows), 3); self.assertEqual(rows[0]['elevation_ft'], 674.9); self.assertEqual(rows[1]['percent_full'], 89.3); self.assertIsNone(rows[2]['elevation_ft']); self.assertIsNone(rows[2]['percent_full'])
    def test_lake_list_is_the_region(self):
        self.assertIn('travis', rv.LAKES); self.assertIn('austin', rv.LAKES); self.assertIn('canyon', rv.LAKES); self.assertEqual(len(rv.LAKES), 10)
class EaaTests(unittest.TestCase):
    def test_site_tables_parse_from_the_page_script_and_csv_rows_keep_flags(self):
        html = '<script>var allWellsLocationsJSON = [{"siteInfoId": 1, "siteId": "J17", "siteName": "Bexar Index Well J-17", "siteStatus": "Active"}];</script>'
        self.assertEqual(eaa.parse_sites(html, 'allWellsLocationsJSON')[0]['siteId'], 'J17'); self.assertEqual(eaa.parse_sites(html, 'rainGaugesLocationsJSON'), [])
        rows = list(eaa.rows_of(EAA_CSV)); self.assertEqual(rows, [('J17', '2026-09-29', 638.1, 'P'), ('J17', '2026-09-30', 638.33, 'P')], 'the blank value row is dropped, never zero')
    def test_assess_is_context_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); keep = (eaa.ROOT, eaa.RAW, eaa.CAP, eaa.DB, eaa.APP, eaa.SITES)
            eaa.ROOT, eaa.RAW, eaa.CAP, eaa.DB, eaa.APP, eaa.SITES = root, root / 'raw', root / 'cap', root / 'db.sqlite', root / 'app', root / 'sites.json'; eaa.APP.mkdir()
            try:
                eaa.SITES.write_text(json.dumps({'sites': {'wells': [{'siteInfoId': 1, 'siteId': 'J17', 'siteName': 'J-17', 'siteStatus': 'Active', 'county': 'Bexar'}], 'rain': [{'siteInfoId': 2, 'siteId': 'BAN061RG', 'siteName': 'Bandera 061', 'siteStatus': 'Active'}], 'streams': []}}))
                d = eaa.RAW / 'wells' / 'J17'; d.mkdir(parents=True); (d / '20261001T000000000000Z-J17-DHE.csv').write_text(EAA_CSV); (d / '20261001T000000000000Z-J17-DHE.meta.json').write_text(json.dumps({'status': 200, 'retrieved_at': '2026-10-01T00:00:00+00:00'}))
                r = eaa.RAW / 'rain' / 'BAN061RG'; r.mkdir(parents=True); (r / '20261001T000000000000Z-BAN061RG-DLRAIN.csv').write_text('BAN061RG,2026-09-30,0.50,P,x\nBAN061RG,2026-10-01,1.25,P,x\n'); (r / '20261001T000000000000Z-BAN061RG-DLRAIN.meta.json').write_text(json.dumps({'status': 200, 'retrieved_at': '2026-10-01T00:00:00+00:00'}))
                eaa.normalize(); eaa.assess(dt.datetime(2026, 10, 2, tzinfo=dt.timezone.utc)); out = json.loads((eaa.APP / 'eaa.json').read_text())
                self.assertEqual(out['wells']['J17']['latest'], {'date': '2026-09-30', 'elevation_ft_amsl': 638.33}); self.assertIsNone(out['wells']['J17']['percentile_13mo']); self.assertNotIn('status', out['wells']['J17'])
                self.assertEqual(out['rain_gauges']['BAN061RG']['last_3d'], {'inches': 1.75, 'days_reported': 2}); self.assertIn('never zero', out['rain_gauges']['BAN061RG']['meaning'])
            finally: eaa.ROOT, eaa.RAW, eaa.CAP, eaa.DB, eaa.APP, eaa.SITES = keep
class InventoryTests(unittest.TestCase):
    def test_locations_file_covers_every_discharge_station_and_marks_kinds(self):
        locs = json.loads((ri.ROOT / 'data/usgs-locations-regional.json').read_text()); st = json.loads((ri.ROOT / 'data/stations-regional.json').read_text())
        ids = {r['id'] for r in locs['locations']}; self.assertTrue({s['id'] for s in st['stations']} <= ids)
        self.assertTrue(all(r['tier'] in ('austin', 'regional-key', 'regional-other', 'usgs-other') for r in locs['locations']))
        plan = json.loads((ri.ROOT / 'data/usgs-history-plan.json').read_text()); self.assertTrue(all(s['label'] in ri.DAILY_WANTED.values() for p in plan['plan'] for s in p['series']))
if __name__ == '__main__': unittest.main()
