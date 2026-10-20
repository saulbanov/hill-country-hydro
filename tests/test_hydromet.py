import datetime as dt, json, unittest
from pathlib import Path
from tools import hydromet as hm
FIX = Path(__file__).resolve().parent / 'fixtures'

class HydrometTests(unittest.TestCase):
    def test_windows_never_reach_the_180_day_limit_and_tile_the_year(self):
        for year in (2015, 2024, 2026):
            w = hm.windows_for_year(year)
            self.assertEqual([x[2] for x in w], [1, 2, 3])
            for start, end, n in w: self.assertLess((end - start).days + 1, 180, (year, n))
            self.assertEqual(w[0][0], dt.date(year, 1, 1)); self.assertEqual(w[-1][1], dt.date(year, 12, 31))
            for (s1, e1, _), (s2, e2, _) in zip(w, w[1:]): self.assertEqual(e1 + dt.timedelta(days=1), s2)

    def test_history_urls_follow_the_site_javascript(self):
        s, e = dt.date(2026, 1, 1), dt.date(2026, 4, 30)
        self.assertEqual(hm.history_url('COA', '950', 'flow', s, e), 'https://hydromet.lcra.org/api/CoaHistoricalData/GetDataBySite/950/flow/1-1-2026/4-30-2026')
        self.assertEqual(hm.history_url('LCRA', '4595', 'flow', s, e, hourly=True), 'https://hydromet.lcra.org/api/HistoricData/GetDataBySite/4595/flow/1-1-2026/4-30-2026/hourly')
        self.assertEqual(hm.history_url('COA', '950', 'flow', s, e, hourly=True), 'https://hydromet.lcra.org/api/CoaHistoricalData/GetDataBySite/950/flow/1-1-2026/4-30-2026', 'COA has no hourly variant')

    def test_parse_sites_types_numbers_and_tags_creeks_without_inventing_values(self):
        sites = {s['site']: s for s in hm.parse_sites((FIX / 'hydromet-all-sites-sample.json').read_bytes())}
        w = sites['950']; self.assertEqual(w['agency'], 'COA'); self.assertEqual(w['creek'], 'williamson-creek'); self.assertIsNone(w['flow_cfs']); self.assertIsInstance(w['stage_ft'], float)
        self.assertEqual(sites['3992']['creek'], 'bull-creek'); self.assertEqual(sites['3650']['creek'], 'bull-creek'); self.assertEqual(sites['3650']['site_type'], 'rain')
        dam = sites['3963']; self.assertEqual(dam['creek'], 'lake-travis'); self.assertNotIn('<br', dam['name']); self.assertIsInstance(dam['head_ft'], float)
        self.assertEqual(sites['08154700']['agency'], 'USGS'); self.assertEqual(sites['08154700']['creek'], 'bull-creek')
        for s in sites.values():
            for k, v in s['rain_in'].items(): self.assertIsNotNone(v)

    def test_parse_history_keeps_records_and_header_and_tolerates_bad_bodies(self):
        recs, hdr = hm.parse_history((FIX / 'hydromet-history-sample.json').read_bytes())
        self.assertEqual(len(recs), 3); self.assertEqual(hdr['value1Type'], 'Stage'); self.assertEqual(hdr['value2Type'], 'Flow'); self.assertEqual(hdr['siteNumber'], 950)
        self.assertNotIn('value2', recs[0], 'a missing flow stays missing in the raw record')
        self.assertEqual(hm.parse_history(b'Start and End date must be within 180 days of each other.'), ([], {}))
        self.assertEqual(hm.parse_history(b'[]'), ([], {}))

    def test_coverage_summarises_manifest_windows_without_counting_failures(self):
        windows = {'coa/950-flow-2026-1.json.gz': {'agency': 'COA', 'site': '950', 'param': 'flow', 'status': 200, 'records': 10, 'first': '2026-01-01T06:00:00Z', 'last': '2026-04-30T23:45:00Z', 'value1Type': 'Stage', 'value2Type': 'Flow'},
                   'coa/950-flow-2026-2.json.gz': {'agency': 'COA', 'site': '950', 'param': 'flow', 'status': 200, 'records': 5, 'first': '2026-05-01T06:00:00Z', 'last': '2026-06-01T00:00:00Z'},
                   'coa/950-flow-2014-1.json.gz': {'agency': 'COA', 'site': '950', 'param': 'flow', 'status': 500, 'records': 0}}
        c = hm.coverage(windows)['COA:950:flow']
        self.assertEqual((c['windows_ok'], c['windows_failed'], c['records']), (2, 1, 15)); self.assertEqual(c['first'], '2026-01-01T06:00:00Z'); self.assertEqual(c['last'], '2026-06-01T00:00:00Z')

    def test_priority_sites_name_the_creeks_saul_asked_for(self):
        self.assertTrue({'950', '1130'} <= set(hm.PRIORITY['COA']['flow']), 'Williamson Creek stage sites')
        self.assertTrue({'3650', '2730'} <= set(hm.PRIORITY['COA']['rain']), 'Bull Creek Dam and Barton Creek Boulevard rain')
        self.assertTrue({'3992', '4519', '4520', '4595', '4598'} <= set(hm.PRIORITY['LCRA']['flow']), 'Bull, Barton and Onion')

    def test_an_empty_window_is_asked_again_at_finer_resolution_for_lcra_and_once_more_otherwise(self):
        self.assertEqual(hm.attempt_plan('LCRA', True), [True, False]); self.assertEqual(hm.attempt_plan('LCRA', False), [False, False]); self.assertEqual(hm.attempt_plan('COA', False), [False, False])
        self.assertEqual(hm.capture_name('4595', 'flow', 2018, 1, True), '4595-flow-hourly-2018-1.json.gz'); self.assertEqual(hm.capture_name('4595', 'flow', 2018, 1, False), '4595-flow-2018-1.json.gz')

if __name__ == '__main__': unittest.main()
