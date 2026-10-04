import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from tools import regional_normalize as n, regional_analytics as a
from tools.creek_normalize import resolve


def row(value=1, **kw):
    args=dict(operator='USGS',feed='USGS',site='1',series='s',parameter='p',quantity='discharge',unit='cfs',value=value,when='2026-09-30',statistic='daily_mean',source='capture',locator='row',approval='Approved')
    args.update(kw);return n.measurement(**args)


class RegionalTests(unittest.TestCase):
    def test_missing_zero_nonfinite(self):
        for q,u in [('rain','in'),('storage','acre-ft'),('groundwater_depth','ft')]:
            self.assertEqual(row(0,quantity=q,unit=u)['state'],'measured')
            for x in [None,'nan','bad']:
                r=row(x,quantity=q,unit=u);self.assertIsNone(r['value']);self.assertEqual(r['state'],'unavailable')
    def test_depth_direction_and_elevation_datum(self):
        x=row(90,quantity='groundwater_depth',unit='ft',datum='land surface');y=row(91,quantity='groundwater_depth',unit='ft',datum='land surface')
        self.assertEqual(a.change(x,y)['water_level_change'],-1)
        x=row(900,quantity='groundwater_elevation',unit='ft');self.assertFalse(a.change(x,x)['available'])
    def test_unit_and_datum_mismatch(self):
        x=row(10,quantity='stage',unit='ft',datum='NAVD88');y=row(10,quantity='stage',unit='ft',datum='NGVD29')
        self.assertFalse(a.change(x,y)['available'])
        self.assertEqual(row(quantity='storage',unit='ft')['state'],'unavailable')
        self.assertAlmostEqual(row(25.4,quantity='rain',unit='mm')['value'],1)
    def test_storage_is_not_elevation_or_inflow(self):
        x=row(100,quantity='storage',unit='acre-ft');y=row(105,quantity='storage',unit='acre-ft')
        self.assertEqual(a.change(x,y)['difference'],5)
        self.assertFalse(a.change(x,row(10,quantity='reservoir_elevation',unit='ft'))['available'])
        self.assertNotIn('inflow',a.change(x,y))
    def test_date_only_and_daily_high(self):
        r=row(statistic='daily_high',quantity='groundwater_depth',unit='ft')
        self.assertIsNone(r['time']['instant']);self.assertEqual(r['time']['date'],'2026-09-30')
        self.assertFalse(a.change(r,dict(r,time=dict(r['time'],statistic='daily_mean')))['available'])
        self.assertIsNone(a.exact_day([r],'2026-09-29'))
    def test_ambiguous_point_time(self):
        r=row(when='2026-09-30 12:00:00',statistic='reported_point');self.assertIn('ambiguous_time',r['issues'])
    def test_revisions_and_alternative_sensors(self):
        x=dict(row(1,source='old'),retrieved_at='2026-10-01T00:00:00Z');y=dict(row(None,source='new'),retrieved_at='2026-10-02T00:00:00Z')
        self.assertEqual(resolve([x,y])[0][0]['state'],'unavailable')
        self.assertEqual(len(resolve([x,row(2,series='other')])[0]),2)
    def history(self,month=9,day=30):
        rows=[]
        for year in range(2006,2026):
            start=dt.date(year,month,day)-dt.timedelta(days=16)
            for i in range(34):rows.append(row(0,when=str(start+dt.timedelta(days=i)),locator=f'{year}/{i}'))
        return rows
    def test_zero_ties_and_no_instant_rank(self):
        ref=a.seasonal_reference(self.history(),'2026-09-30');self.assertTrue(ref['available'])
        result=a.rank(row(0),ref);self.assertEqual(result['percentile'],50);self.assertIsNone(result['ratio_to_daily_median'])
        self.assertFalse(a.rank(row(2,when='2026-09-30T00:00:00Z',statistic='instantaneous'),ref)['available'])
    def test_rank_requires_same_sensor(self):
        ref=a.seasonal_reference(self.history(),'2026-09-30')
        self.assertFalse(a.rank(row(series='another'),ref)['available'])
    def test_changed_capacity_withholds_percent_change(self):
        x=row(50,quantity='percent_full',unit='%',extra={'capacity':{'conservation_capacity_af':100}})
        y=row(50,quantity='percent_full',unit='%',extra={'capacity':{'conservation_capacity_af':200}})
        self.assertFalse(a.change(x,y)['available'])
    def test_partial_years_stay_in_denominator(self):
        ref=a.seasonal_reference(self.history()[:170],'2026-09-30');self.assertFalse(ref['available']);self.assertEqual(ref['expected_days'],620)
    def test_leap_calendar_and_year_wrap(self):
        ref=a.seasonal_reference(self.history(2,28),'2026-02-28');self.assertTrue(ref['available']);self.assertEqual(ref['expected_by_year']['2024'],31);self.assertEqual(ref['expected_by_year']['2023'],30)
        self.assertTrue(a.seasonal_reference(self.history(1,1),'2026-01-01')['available'])
    def test_reference_never_pools_sensors(self):
        rows=self.history();rows.append(row(series='different'));self.assertFalse(a.seasonal_reference(rows,'2026-09-30')['available'])
    def interval(self,start,end,value=1):
        r=row(value,quantity='rain',unit='in',when=end,statistic='incremental');r['time'].update(interval_start=start,interval_end=end);return r
    def test_rain_contiguous_totals(self):
        x=self.interval('2026-10-01T00:00:00Z','2026-10-01T01:00:00Z');y=self.interval('2026-10-01T01:00:00Z','2026-10-01T02:00:00Z')
        self.assertEqual(a.rain_total([x,y],x['time']['interval_start'],y['time']['interval_end'])['total'],2)
    def test_rain_overlap_gap_reset(self):
        for start,value in [('2026-10-01T00:30:00Z',1),('2026-10-01T01:30:00Z',1),('2026-10-01T01:00:00Z',-1)]:
            x=self.interval('2026-10-01T00:00:00Z','2026-10-01T01:00:00Z');y=self.interval(start,'2026-10-01T02:00:00Z',value)
            self.assertFalse(a.rain_total([x,y],'2026-10-01T00:00:00Z','2026-10-01T02:00:00Z')['available'])
    def test_rain_rolling_and_unknown_increment_withheld(self):
        for stat in ['rolling_24h','cumulative_counter','reported_increment','daily_total_boundary_unverified']:
            self.assertFalse(a.rain_total([row(quantity='rain',unit='in',statistic=stat)],'2026-10-01T00:00:00Z','2026-10-02T00:00:00Z')['available'])
    def test_source_hash_and_missing_fetch_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'raw').write_bytes(b'[]');b=n.Builder(root,root/'out','2026-09-01','2026-10-03T12:15:00Z')
            _,s=b.source('raw');self.assertEqual(b.sources[s]['provenance_status'],'original_fetch_metadata_missing')
            with self.assertRaisesRegex(ValueError,'checksum'):b.source('raw',{'sha256':'wrong'})
            b.db.close();self.assertEqual((root/'raw').read_bytes(),b'[]')
    def test_temporal_no_future_or_gap(self):
        r=row(when='2026-10-01T12:00:00Z',statistic='instantaneous')
        self.assertIsNone(a.at_or_before([r],'2026-10-01T11:59:00Z'));self.assertIsNone(a.at_or_before([r],'2026-10-01T12:31:00Z'))

if __name__=='__main__':unittest.main()
