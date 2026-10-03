import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from tools import creek_normalize as n, creek_analytics as a


def row(value=1, **kw):
    args=dict(operator='USGS',feed='USGS',site='1',series='s',parameter='00060',quantity='discharge',unit='cfs',value=value,
        when='2026-10-01T12:00:00Z',statistic='instantaneous',source='capture',locator='features/0',approval='Approved')
    args.update(kw);return n.record(**args)


class NormalizationTests(unittest.TestCase):
    def test_equivalent_units(self):
        self.assertAlmostEqual(row(1,unit='m3/s')['value'],row(35.31466672148859)['value'])
        self.assertAlmostEqual(row(1,unit='m',quantity='stage')['value'],3.280839895013123)
    def test_unknown_unit_and_datum(self):
        self.assertIn('unknown_unit',row(unit='furlongs')['issues'])
        r=row(unit='ft',quantity='stage');self.assertIsNone(r['vertical_datum']);self.assertEqual(r['datum_status'],'unknown')
    def test_missing_zero_invalid_and_negative(self):
        self.assertEqual(row(0)['state'],'measured');self.assertIsNone(row(None)['value'])
        for v in [float('nan'),float('inf'),'ice',-1]: self.assertEqual(row(v)['state'],'unavailable')
    def test_times(self):
        self.assertEqual(row(when='2026-10-01T07:00:00-05:00')['time']['instant'],row()['time']['instant'])
        self.assertEqual(row(when='2026-10-01')['state'],'unavailable')
        self.assertIsNone(row(when='2026-10-01T12:00:00')['time']['instant'])
        r=row(when='2026-10-01',statistic='daily_mean');self.assertEqual(r['time']['precision'],'date');self.assertIsNone(r['time']['interval_start'])
    def test_rejected_provisional_and_stale(self):
        self.assertIn('rejected',row(approval='Rejected')['issues'])
        self.assertEqual(row(approval='Provisional')['approval'],'Provisional')
        self.assertIn('provider_stale',row(stale=True)['issues'])
    def test_capture_conflict_retained(self):
        rows=[dict(row(1,source='a'),retrieved_at='2026-10-01'),dict(row(2,source='b'),retrieved_at='2026-10-02')]
        resolved,conflicts=n.resolve(rows);self.assertEqual(len(rows),2);self.assertEqual(resolved[0]['value'],2)
        self.assertEqual(conflicts[0]['values'],[1,2]);self.assertTrue(resolved[0]['conflicting_captures'])
    def test_later_rejected_revision_does_not_resurrect(self):
        rows=[dict(row(1,source='a'),retrieved_at='2026-10-01'),dict(row(None,source='b'),retrieved_at='2026-10-02')]
        resolved,_=n.resolve(rows);self.assertEqual(resolved[0]['state'],'unavailable')
    def test_multiple_sensors_are_not_stitched(self):
        self.assertIsNone(n.select_series([{'id':'a'},{'id':'b'}])[0])
        self.assertEqual(n.select_series([{'id':'a','primary':True},{'id':'b'}])[0],'a')
        self.assertIsNone(n.select_series([{'id':'a','primary':True},{'id':'b','primary':True}])[0])
        rows,_=n.resolve([row(series='a'),row(series='b')]);self.assertEqual(len(rows),2)
    def test_verified_alias_requires_agency_and_id(self):
        native=row();mirror=row(operator='USGS',feed='Hydromet');nearby=row(operator='LCRA',feed='Hydromet',site='99')
        self.assertEqual(native['physical_gauge_id'],mirror['physical_gauge_id']);self.assertNotEqual(native['series_id'],mirror['series_id'])
        self.assertNotEqual(native['physical_gauge_id'],nearby['physical_gauge_id'])
    def test_raw_checksum_fail_closed_and_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);data=b'{"features":[]}';p=root/'x.json.gz';p.write_bytes(gzip.compress(data));before=p.read_bytes()
            b=n.Builder(root);meta=dict(sha256=hashlib.sha256(data).hexdigest(),status=200)
            b.source('raw.json',meta,'x.json.gz');self.assertEqual(p.read_bytes(),before)
            with self.assertRaisesRegex(ValueError,'checksum'):b.source('raw.json',dict(meta,sha256='bad'),'x.json.gz')


class ComparisonTests(unittest.TestCase):
    def history(self,value=0):
        return [row(value,when=str(dt.date(y,9,16)+dt.timedelta(days=d)),statistic='daily_mean',locator=f'{y}/{d}') for y in range(2006,2026) for d in range(31)]
    def test_zero_baseline_no_invented_denominator(self):
        ref=a.seasonal_reference(self.history());self.assertTrue(ref['available'])
        c=a.contrast(row(7),ref);self.assertEqual(c['difference_cfs'],7);self.assertIsNone(c['ratio_to_daily_median']);self.assertIsNone(c['instantaneous_percentile'])
        self.assertFalse(c['sampling_match'])
    def test_insufficient_history_and_gappy_years(self):
        self.assertFalse(a.seasonal_reference(self.history()[:31])['available'])
        self.assertFalse(a.seasonal_reference([r for i,r in enumerate(self.history()) if i%2])['available'])
    def test_aggregation_mismatch_and_stage(self):
        ref=a.seasonal_reference(self.history(2))
        self.assertFalse(a.contrast(row(3,statistic='hourly_unspecified'),ref)['available'])
        self.assertFalse(a.contrast(row(3,quantity='stage',unit='ft'),ref)['available'])
    def test_gap_rejected_latest_and_no_future(self):
        r=row();self.assertIsNone(a.at_or_before([r],'2026-10-01T11:59:59Z'))
        self.assertEqual(a.at_or_before([r],'2026-10-01T12:30:00Z')['id'],r['id'])
        self.assertIsNone(a.at_or_before([r],'2026-10-01T12:30:01Z'))
        bad=row(None,when='2026-10-01T12:15:00Z');self.assertIsNone(a.at_or_before([r,bad],'2026-10-01T12:20:00Z'))
    def test_no_cross_sensor_baseline(self):
        rows=self.history();rows[-1]=dict(rows[-1],series_id='different');self.assertFalse(a.seasonal_reference(rows)['available'])
    def test_replay_stable_ids(self):
        self.assertEqual(row()['id'],row()['id']);self.assertNotEqual(row()['id'],row(source='other')['id'])

if __name__=='__main__':unittest.main()
